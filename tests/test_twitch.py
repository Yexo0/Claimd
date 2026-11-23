from __future__ import annotations

import httpx
import pytest

from claimd.checkers import twitch

pytestmark = pytest.mark.anyio

TOKEN_OK = httpx.Response(200, json={"access_token": "tok-1", "expires_in": 5000000, "token_type": "bearer"})


@pytest.fixture
def configured(use_settings):
    return use_settings(twitch_client_id="cid", twitch_client_secret="secret")


def users(*logins: str, created_at: str = "2016-05-01T12:00:00Z") -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"login": lg, "display_name": lg.title(), "created_at": created_at} for lg in logins]},
    )


@pytest.mark.parametrize("name", ["abc", "_yexo", "ye xo", "yé", "yexo.tv", "a" * 26])
async def test_invalid_usernames_never_hit_the_network(name, configured, respx_mock):
    result = await twitch.check(name)
    assert result.status == "invalid"
    assert result.available is None
    assert result.reliability == "high"
    assert result.method == "validation"
    assert result.url is None
    assert "4 à 25" in result.detail
    assert not respx_mock.calls


async def test_missing_credentials_is_uncertain_not_a_guess(respx_mock):
    result = await twitch.check("yexo")
    assert result.status == "uncertain"
    assert result.available is None
    assert result.reliability == "low"
    assert result.reason == "not_configured"
    assert ".env" in result.detail
    assert not respx_mock.calls


async def test_taken(configured, respx_mock):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    route = respx_mock.get(twitch.USERS_URL, params={"login": "yexo"}).mock(return_value=users("yexo"))

    result = await twitch.check("yexo")

    assert result.status == "taken"
    assert result.available is False
    assert result.reliability == "high"
    assert result.method == "helix_api"
    assert result.url == "https://www.twitch.tv/yexo"
    assert "2016" in result.detail
    request = route.calls.last.request
    assert request.headers["Client-Id"] == "cid"
    assert request.headers["Authorization"] == "Bearer tok-1"


async def test_available(configured, respx_mock):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    respx_mock.get(twitch.USERS_URL).mock(return_value=httpx.Response(200, json={"data": []}))

    result = await twitch.check("yexo_free_42")

    assert result.status == "available"
    assert result.available is True
    assert result.reliability == "high"
    assert "suspendu" in result.detail  # the Helix caveat is surfaced, not hidden


async def test_lookup_is_case_insensitive(configured, respx_mock):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    route = respx_mock.get(twitch.USERS_URL, params={"login": "yexo"}).mock(return_value=users("yexo"))

    result = await twitch.check("YeXo")

    assert result.status == "taken"
    assert result.username == "YeXo"
    assert route.called


async def test_secret_travels_in_the_body_not_the_url(configured, respx_mock):
    token = respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    respx_mock.get(twitch.USERS_URL).mock(return_value=users("yexo"))

    await twitch.check("yexo")

    request = token.calls.last.request
    assert "secret" not in str(request.url)
    assert b"client_secret=secret" in request.content
    assert b"grant_type=client_credentials" in request.content


async def test_token_is_cached_between_checks(configured, respx_mock):
    token = respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    respx_mock.get(twitch.USERS_URL).mock(return_value=httpx.Response(200, json={"data": []}))

    await twitch.check("first_name")
    await twitch.check("second_name")

    assert token.call_count == 1


async def test_rejected_token_is_refreshed_once(configured, respx_mock):
    token = respx_mock.post(twitch.TOKEN_URL).mock(
        side_effect=[TOKEN_OK, httpx.Response(200, json={"access_token": "tok-2", "expires_in": 3600})]
    )
    lookup = respx_mock.get(twitch.USERS_URL).mock(side_effect=[httpx.Response(401), users("yexo")])

    result = await twitch.check("yexo")

    assert result.status == "taken"
    assert token.call_count == 2
    assert lookup.calls.last.request.headers["Authorization"] == "Bearer tok-2"


@pytest.mark.parametrize("status_code", [400, 403])
async def test_bad_credentials(configured, respx_mock, status_code):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=httpx.Response(status_code))

    result = await twitch.check("yexo")

    assert result.status == "uncertain"
    assert result.reason == "auth_failed"
    assert result.available is None


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(500), "unexpected_response"),
        (httpx.Response(200, text="<html>oops</html>"), "unexpected_response"),
        (httpx.Response(200, json={"data": "nope"}), "unexpected_response"),
        (httpx.Response(200, json={"data": [{"login": "someone_else"}]}), "ambiguous"),
    ],
)
async def test_odd_responses_are_never_guessed(configured, respx_mock, response, reason):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    respx_mock.get(twitch.USERS_URL).mock(return_value=response)

    result = await twitch.check("yexo")

    assert result.status == "uncertain"
    assert result.available is None
    assert result.reliability == "low"
    assert result.reason == reason


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx.ConnectTimeout("slow"), "timeout"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("down"), "network_error"),
    ],
)
async def test_network_failures(configured, respx_mock, error, reason):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=TOKEN_OK)
    respx_mock.get(twitch.USERS_URL).mock(side_effect=error)

    result = await twitch.check("yexo")

    assert result.status == "uncertain"
    assert result.reason == reason


async def test_malformed_token_response(configured, respx_mock):
    respx_mock.post(twitch.TOKEN_URL).mock(return_value=httpx.Response(200, json={"nope": True}))

    result = await twitch.check("yexo")

    assert result.status == "uncertain"
    assert result.reason == "unexpected_response"
