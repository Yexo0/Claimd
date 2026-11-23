from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from claimd import checkers as registry
from claimd.main import app

from .conftest import fake_checker


async def free(platform, username):
    return platform.available(username, detail="ok")


async def taken(platform, username):
    return platform.taken(username)


async def boom(platform, username):
    raise RuntimeError("bug")


async def slow(platform, username):
    await asyncio.sleep(10)
    return platform.available(username)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_registry(monkeypatch):
    def apply(*checkers):
        monkeypatch.setattr(registry, "CHECKERS", tuple(checkers))

    return apply


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_frontend_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Claimd" in res.text
    for asset in (
        "/js/app.js", "/js/api.js", "/js/motion.js", "/js/icons.js", "/js/tooltip.js",
        "/css/style.css", "/vendor/gsap/gsap.min.js", "/fonts/geist-latin-wght.woff2", "/favicon.svg",
    ):
        assert client.get(asset).status_code == 200, asset


def test_platforms_lists_twitch_and_its_config_state(client, use_settings):
    platforms = client.get("/platforms").json()
    twitch = next(p for p in platforms if p["id"] == "twitch")
    assert twitch["reliability"] == "high"
    assert twitch["configured"] is False

    use_settings(twitch_client_id="cid", twitch_client_secret="secret")
    twitch = next(p for p in client.get("/platforms").json() if p["id"] == "twitch")
    assert twitch["configured"] is True


def test_check_aggregates_every_platform(client, fake_registry):
    fake_registry(fake_checker("alpha", free), fake_checker("beta", taken))

    res = client.get("/check/yexo")

    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "yexo"
    assert [r["platform"] for r in body["results"]] == ["alpha", "beta"]
    alpha, beta = body["results"]
    assert alpha["available"] is True and alpha["status"] == "available"
    assert beta["available"] is False and beta["status"] == "taken"
    assert alpha["url"] == "https://example.test/alpha/yexo"
    assert body["summary"]["available"] == 1
    assert body["summary"]["checkable"] == 2
    assert isinstance(body["elapsed_ms"], int)
    for result in body["results"]:
        assert {"available", "method", "reliability", "status", "detail"} <= result.keys()


def test_one_failing_platform_never_breaks_the_response(client, fake_registry, use_settings):
    use_settings(check_timeout=0.2)
    fake_registry(fake_checker("crash", boom), fake_checker("hang", slow), fake_checker("fine", free))

    res = client.get("/check/yexo")

    assert res.status_code == 200
    crash, hang, fine = res.json()["results"]
    assert crash["status"] == "uncertain" and crash["reason"] == "internal_error"
    assert hang["status"] == "uncertain" and hang["reason"] == "timeout"
    assert fine["status"] == "available"


def test_handle_prefix_and_spaces_are_normalized(client, fake_registry):
    fake_registry(fake_checker("alpha", free))
    assert client.get("/check/%40yexo").json()["username"] == "yexo"
    assert client.get("/check/%20yexo%20").json()["username"] == "yexo"


@pytest.mark.parametrize("path", ["/check/%20%20", "/check/%40", "/check/" + "a" * 65])
def test_unusable_input_is_a_clean_422(client, path):
    res = client.get(path)
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], str)


def test_real_registry_offline_still_answers(client):
    """No network (blocked in tests) and no Twitch keys: still a clean 200."""
    res = client.get("/check/yexo")
    assert res.status_code == 200
    body = res.json()
    by_id = {r["platform"]: r for r in body["results"]}
    assert list(by_id) == ["twitch", "youtube", "instagram", "tiktok", "gmail"]
    assert by_id["twitch"]["reason"] == "not_configured"
    for pid in ("youtube", "instagram", "tiktok"):
        assert by_id[pid]["status"] == "uncertain"
        assert by_id[pid]["reason"] == "network_error"
    assert by_id["gmail"]["status"] == "invalid"  # "yexo" is shorter than Gmail's 6 characters
    assert body["summary"]["checkable"] == 4  # Gmail never counts in "free on X/N"


def test_stream_emits_start_results_and_done(client, fake_registry):
    async def nap_then_free(platform, username):
        await asyncio.sleep(0.15)
        return platform.available(username)

    fake_registry(fake_checker("slow", nap_then_free), fake_checker("fast", taken))

    with client.stream("GET", "/check/yexo/stream") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in res.iter_lines() if line]

    assert [e["type"] for e in events] == ["start", "result", "result", "done"]
    assert events[0]["platforms"] == ["slow", "fast"]
    # Fastest first, not registry order.
    assert [e["result"]["platform"] for e in events[1:3]] == ["fast", "slow"]
    assert events[-1]["summary"]["available"] == 1
    assert events[-1]["summary"]["taken"] == 1


def test_stream_validates_input_before_streaming(client):
    res = client.get("/check/%20/stream")
    assert res.status_code == 422
    assert res.json()["detail"] == "Saisis un pseudo."


def test_platforms_expose_notes_and_gmail_is_informational(client):
    platforms = {p["id"]: p for p in client.get("/platforms").json()}
    assert all(p["note"] for p in platforms.values())
    assert platforms["gmail"]["verifiable"] is False
    assert platforms["gmail"]["method"] == "none"
    assert [platforms[i]["reliability"] for i in ("twitch", "youtube", "instagram", "tiktok")] == [
        "high", "medium", "low", "low",
    ]
