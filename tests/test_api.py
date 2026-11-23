from __future__ import annotations

import asyncio

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
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/css/style.css").status_code == 200


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


def test_real_registry_without_twitch_keys_still_answers(client):
    res = client.get("/check/yexo")
    assert res.status_code == 200
    twitch = next(r for r in res.json()["results"] if r["platform"] == "twitch")
    assert twitch["status"] == "uncertain"
    assert twitch["reason"] == "not_configured"
