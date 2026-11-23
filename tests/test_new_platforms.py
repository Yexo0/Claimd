"""Kick, Steam, Bluesky, the Instagram session option and the result cache."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from claimd.checkers import bluesky, instagram, kick, steam
from claimd.runner import run_checker

from .conftest import fake_checker

pytestmark = pytest.mark.anyio

KICK_TOKEN = httpx.Response(200, json={"access_token": "kick-tok", "expires_in": 3600, "token_type": "Bearer"})


# ---------------------------------------------------------------- Kick


@pytest.fixture
def kick_keys(use_settings):
    return use_settings(kick_client_id="kid", kick_client_secret="ksecret")


def kick_channels(*slugs: str) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"slug": s, "broadcaster_user_id": 1} for s in slugs], "message": "OK"})


async def test_kick_without_keys_is_uncertain(respx_mock):
    result = await kick.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == "not_configured"
    assert not respx_mock.calls


@pytest.mark.parametrize("name", ["ye xo", "yexo.fps", "a" * 26, "yéxo"])
async def test_kick_invalid(name, kick_keys, respx_mock):
    assert (await kick.check(name)).status == "invalid"
    assert not respx_mock.calls


async def test_kick_taken_queries_both_slug_spellings(kick_keys, respx_mock):
    token = respx_mock.post(kick.TOKEN_URL).mock(return_value=KICK_TOKEN)
    channels = respx_mock.get(kick.CHANNELS_URL).mock(return_value=kick_channels("yexo-fps"))

    result = await kick.check("Yexo_FPS")

    assert result.status == "taken"
    assert result.reliability == "high"
    assert result.url == "https://kick.com/yexo-fps"
    request = channels.calls.last.request
    assert request.url.params.get_list("slug") == ["yexo-fps", "yexo_fps"]
    assert request.headers["Authorization"] == "Bearer kick-tok"
    assert b"client_secret=ksecret" in token.calls.last.request.content


async def test_kick_available(kick_keys, respx_mock):
    respx_mock.post(kick.TOKEN_URL).mock(return_value=KICK_TOKEN)
    respx_mock.get(kick.CHANNELS_URL).mock(return_value=kick_channels())
    result = await kick.check("yexofps")
    assert result.status == "available"
    assert "banni" in result.detail


async def test_kick_refreshes_a_rejected_token_once(kick_keys, respx_mock):
    token = respx_mock.post(kick.TOKEN_URL).mock(return_value=KICK_TOKEN)
    respx_mock.get(kick.CHANNELS_URL).mock(side_effect=[httpx.Response(401, json={"data": {}}), kick_channels("yexofps")])
    assert (await kick.check("yexofps")).status == "taken"
    assert token.call_count == 2


@pytest.mark.parametrize(
    ("token_response", "channels_response", "reason"),
    [
        (httpx.Response(401, json={"error": "invalid_client"}), None, "auth_failed"),
        (KICK_TOKEN, httpx.Response(403, json={"data": {}}), "auth_failed"),
        (KICK_TOKEN, httpx.Response(429), "rate_limited"),
        (KICK_TOKEN, httpx.Response(500), "unexpected_response"),
        (KICK_TOKEN, httpx.Response(200, json={"data": {}, "message": "?"}), "unexpected_response"),
        (KICK_TOKEN, kick_channels("someone-else"), "ambiguous"),
    ],
)
async def test_kick_never_guesses(kick_keys, respx_mock, token_response, channels_response, reason):
    respx_mock.post(kick.TOKEN_URL).mock(return_value=token_response)
    if channels_response is not None:
        respx_mock.get(kick.CHANNELS_URL).mock(return_value=channels_response)
    result = await kick.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == reason


# ---------------------------------------------------------------- Steam

STEAM_URL = "https://steamcommunity.com/id/yexofps/"

STEAM_PROFILE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><profile>
\t<steamID64>76561197960287930</steamID64>\t<steamID><![CDATA[Yexo]]></steamID>\t<onlineState>offline</onlineState>
</profile>"""
STEAM_MISSING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<response><error><![CDATA[The specified profile could not be found.]]></error></response>"
)


@pytest.mark.parametrize("name", ["ab", "a" * 33, "ye xo", "ye.xo", "yéxo"])
async def test_steam_invalid(name, respx_mock):
    assert (await steam.check(name)).status == "invalid"
    assert not respx_mock.calls


async def test_steam_taken(respx_mock):
    route = respx_mock.get(STEAM_URL, params={"xml": "1"}).mock(return_value=httpx.Response(200, text=STEAM_PROFILE))
    result = await steam.check("YexoFPS")
    assert result.status == "taken"
    assert result.reliability == "high"
    assert result.detail == "Profil « Yexo »."
    assert route.called


async def test_steam_available(respx_mock):
    respx_mock.get(STEAM_URL).mock(return_value=httpx.Response(200, text=STEAM_MISSING))
    result = await steam.check("yexofps")
    assert result.status == "available"
    assert result.url == "https://steamcommunity.com/id/yexofps"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(200, text="<html>Steam Community :: Error</html>"), "ambiguous"),
        (httpx.Response(302, headers={"location": "https://steamcommunity.com/"}), "unexpected_response"),
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(503), "unexpected_response"),
    ],
)
async def test_steam_never_guesses(respx_mock, response, reason):
    respx_mock.get(STEAM_URL).mock(return_value=response)
    result = await steam.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == reason


# ---------------------------------------------------------------- Bluesky


@pytest.mark.parametrize("name", ["ab", "a" * 19, "-yexo", "yexo-", "yexo_fps", "ye.xo"])
async def test_bluesky_invalid(name, respx_mock):
    assert (await bluesky.check(name)).status == "invalid"
    assert not respx_mock.calls


async def test_bluesky_taken(respx_mock):
    route = respx_mock.get(bluesky.RESOLVE_URL, params={"handle": "yexofps.bsky.social"}).mock(
        return_value=httpx.Response(200, json={"did": "did:plc:abc123"})
    )
    result = await bluesky.check("YexoFPS")
    assert result.status == "taken"
    assert result.reliability == "high"
    assert result.url == "https://bsky.app/profile/YexoFPS.bsky.social"
    assert route.called


async def test_bluesky_available_is_medium(respx_mock):
    respx_mock.get(bluesky.RESOLVE_URL).mock(
        return_value=httpx.Response(400, json={"error": "InvalidRequest", "message": "Unable to resolve handle"})
    )
    result = await bluesky.check("yexofps")
    assert result.status == "available"
    assert result.reliability == "medium"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(400, json={"error": "InvalidRequest", "message": "Error: handle must be a valid handle"}), "unexpected_response"),
        (httpx.Response(200, json={}), "unexpected_response"),
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(502, text="bad gateway"), "unexpected_response"),
    ],
)
async def test_bluesky_never_guesses(respx_mock, response, reason):
    respx_mock.get(bluesky.RESOLVE_URL).mock(return_value=response)
    result = await bluesky.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == reason


# ---------------------------------------------------------------- Instagram session

IG_URL = "https://www.instagram.com/yexofps/"
IG_PROFILE = '<html><head><meta property="al:ios:url" content="instagram://user?username=yexofps" /></head></html>'


async def test_instagram_without_session_sends_no_cookie(respx_mock):
    route = respx_mock.get(IG_URL).mock(return_value=httpx.Response(200, text=IG_PROFILE))
    result = await instagram.check("yexofps")
    assert result.method == "http_probe"
    assert result.reliability == "medium"
    assert "cookie" not in route.calls.last.request.headers


@pytest.mark.parametrize("configured", ["abc%3A123%3Axyz", "sessionid=abc%3A123%3Axyz"])
async def test_instagram_session_is_sent_and_raises_reliability(configured, use_settings, respx_mock):
    use_settings(instagram_sessionid=configured)
    route = respx_mock.get(IG_URL).mock(return_value=httpx.Response(200, text=IG_PROFILE))

    result = await instagram.check("yexofps")

    assert result.status == "taken"
    assert result.method == "session_probe"
    assert result.reliability == "high"
    assert route.calls.last.request.headers["cookie"] == "sessionid=abc%3A123%3Axyz"


async def test_instagram_session_404_is_available_medium(use_settings, respx_mock):
    use_settings(instagram_sessionid="abc")
    respx_mock.get(IG_URL).mock(return_value=httpx.Response(404))
    result = await instagram.check("yexofps")
    assert result.status == "available"
    assert result.reliability == "medium"


async def test_instagram_expired_session_is_explained(use_settings, respx_mock):
    use_settings(instagram_sessionid="abc")
    respx_mock.get(IG_URL).mock(
        return_value=httpx.Response(302, headers={"location": "https://www.instagram.com/accounts/login/?next=/yexofps/"})
    )
    result = await instagram.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == "session_expired"
    assert "INSTAGRAM_SESSIONID" in result.detail


@pytest.mark.parametrize("bad", ["abc\r\nX-Evil: 1", "abc; other=1", 'abc"', "a b"])
async def test_instagram_malformed_session_is_never_sent(bad, use_settings, respx_mock):
    use_settings(instagram_sessionid=bad)
    result = await instagram.check("yexofps")
    assert result.status == "uncertain"
    assert result.reason == "not_configured"
    assert not respx_mock.calls


# ---------------------------------------------------------------- cache


async def test_cache_reuses_definite_answers_case_insensitively():
    calls = 0

    async def taken(platform, username):
        nonlocal calls
        calls += 1
        return platform.taken(username)

    checker = fake_checker("cached", taken)
    object.__setattr__(checker.PLATFORM, "cache_ttl", 600)

    first = await run_checker(checker, "Yexo", timeout=1)
    second = await run_checker(checker, "yexo", timeout=1)

    assert calls == 1
    assert first.cached is False and second.cached is True
    assert second.username == "yexo"
    assert second.elapsed_ms == 0


async def test_cache_is_off_by_default_and_skips_plain_uncertainty():
    calls = 0

    async def flaky(platform, username):
        nonlocal calls
        calls += 1
        return platform.uncertain(username, reason="network_error")

    plain = fake_checker("plain", flaky)
    cached = fake_checker("cached-flaky", flaky)
    object.__setattr__(cached.PLATFORM, "cache_ttl", 600)

    for checker in (plain, plain, cached, cached):
        await run_checker(checker, "yexo", timeout=1)
    assert calls == 4  # nothing cached: a network error is worth retrying


async def test_cache_backs_off_briefly_on_rate_limits():
    calls = 0

    async def walled(platform, username):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return platform.uncertain(username, reason="login_wall")

    checker = fake_checker("walled", walled)
    object.__setattr__(checker.PLATFORM, "cache_ttl", 600)
    await run_checker(checker, "yexo", timeout=1)
    again = await run_checker(checker, "yexo", timeout=1)
    assert calls == 1
    assert again.cached is True
