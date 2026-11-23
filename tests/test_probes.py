"""YouTube, Instagram, TikTok and Gmail checkers, with HTTP fully mocked."""

from __future__ import annotations

import json

import httpx
import pytest

from claimd.checkers import gmail, instagram, tiktok, youtube
from claimd.http import USER_AGENT

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------- YouTube


@pytest.mark.parametrize("name", ["ab", "_yexo", "yexo_", "-yexo", "yexo.", "ye xo", "a" * 31, "ye/xo"])
async def test_youtube_invalid_handles(name, respx_mock):
    result = await youtube.check(name)
    assert result.status == "invalid"
    assert not respx_mock.calls


@pytest.mark.parametrize("name", ["yexo", "ye.xo", "ye-x_o", "émile", "ye·xo", "abc"])
async def test_youtube_accepts_valid_handles(name, respx_mock):
    respx_mock.head(url__startswith="https://www.youtube.com/@").mock(return_value=httpx.Response(404))
    assert (await youtube.check(name)).status == "available"


async def test_youtube_taken(respx_mock):
    route = respx_mock.head("https://www.youtube.com/@yexo").mock(return_value=httpx.Response(200))

    result = await youtube.check("yexo")

    assert result.status == "taken"
    assert result.available is False
    assert result.reliability == "medium"
    assert result.url == "https://www.youtube.com/@yexo"
    request = route.calls.last.request
    assert request.method == "HEAD"  # no 2 MB page download
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["Cookie"] == "SOCS=CAI"


async def test_youtube_available(respx_mock):
    respx_mock.head("https://www.youtube.com/@yexo").mock(return_value=httpx.Response(404))
    result = await youtube.check("yexo")
    assert result.status == "available"
    assert result.available is True
    assert result.reliability == "medium"


async def test_youtube_follows_redirects_that_stay_on_youtube(respx_mock):
    respx_mock.head("https://www.youtube.com/@yexo").mock(
        return_value=httpx.Response(301, headers={"location": "https://www.youtube.com/@Yexo"})
    )
    respx_mock.head("https://www.youtube.com/@Yexo").mock(return_value=httpx.Response(200))
    assert (await youtube.check("yexo")).status == "taken"


async def test_youtube_consent_redirect_is_uncertain(respx_mock):
    respx_mock.head("https://www.youtube.com/@yexo").mock(
        return_value=httpx.Response(302, headers={"location": "https://consent.youtube.com/m?continue=x"})
    )
    respx_mock.head(url__startswith="https://consent.youtube.com/").mock(return_value=httpx.Response(200))

    result = await youtube.check("yexo")

    assert result.status == "uncertain"
    assert result.reason == "blocked"
    assert result.available is None


async def test_youtube_200_on_non_channel_page_is_not_a_guess(respx_mock):
    respx_mock.head("https://www.youtube.com/@yexo").mock(
        return_value=httpx.Response(302, headers={"location": "https://www.youtube.com/"})
    )
    respx_mock.head("https://www.youtube.com/").mock(return_value=httpx.Response(200))
    result = await youtube.check("yexo")
    assert result.status == "uncertain"
    assert result.reason == "ambiguous"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(500), "unexpected_response"),
        (httpx.ConnectTimeout("slow"), "timeout"),
        (httpx.ConnectError("down"), "network_error"),
    ],
)
async def test_youtube_failures(respx_mock, response, reason):
    route = respx_mock.head("https://www.youtube.com/@yexo")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    result = await youtube.check("yexo")
    assert result.status == "uncertain"
    assert result.reason == reason
    assert result.reliability == "low"


# ---------------------------------------------------------------- Instagram

IG_URL = "https://www.instagram.com/yexo/"

IG_PROFILE = """<html><head>
<title>Yexo (@yexo) &#x2022; Instagram photos and videos</title>
<meta property="al:ios:url" content="instagram://user?username=yexo" />
</head><body></body></html>"""


@pytest.mark.parametrize("name", [".yexo", "yexo.", "ye..xo", "ye-xo", "ye xo", "a" * 31])
async def test_instagram_invalid_usernames(name, respx_mock):
    assert (await instagram.check(name)).status == "invalid"
    assert not respx_mock.calls


async def test_instagram_login_wall_is_uncertain(respx_mock):
    respx_mock.get(IG_URL).mock(
        return_value=httpx.Response(
            302, headers={"location": "https://www.instagram.com/accounts/login/?next=%2Fyexo%2F"}
        )
    )
    result = await instagram.check("yexo")
    assert result.status == "uncertain"
    assert result.reason == "login_wall"
    assert result.available is None
    assert result.reliability == "low"
    assert result.url == IG_URL  # the user can still check by hand


async def test_instagram_challenge_is_uncertain(respx_mock):
    respx_mock.get(IG_URL).mock(
        return_value=httpx.Response(302, headers={"location": "https://www.instagram.com/challenge/?next=/yexo/"})
    )
    assert (await instagram.check("yexo")).reason == "blocked"


async def test_instagram_profile_page_naming_the_user_is_taken(respx_mock):
    respx_mock.get(IG_URL).mock(return_value=httpx.Response(200, text=IG_PROFILE))
    result = await instagram.check("Yexo")  # case-insensitive
    assert result.status == "taken"
    assert result.reliability == "medium"


async def test_instagram_page_about_someone_else_is_not_taken(respx_mock):
    other = IG_PROFILE.replace("yexo", "yexo2")
    respx_mock.get(IG_URL).mock(return_value=httpx.Response(200, text=other))
    result = await instagram.check("yexo")
    assert result.status == "uncertain"
    assert result.reason == "ambiguous"


async def test_instagram_js_shell_without_markers_is_uncertain(respx_mock):
    respx_mock.get(IG_URL).mock(return_value=httpx.Response(200, text="<html><title>Instagram</title></html>"))
    result = await instagram.check("yexo")
    assert result.status == "uncertain"
    assert result.reason == "ambiguous"


async def test_instagram_404_is_available_with_low_reliability(respx_mock):
    respx_mock.get(IG_URL).mock(return_value=httpx.Response(404))
    result = await instagram.check("yexo")
    assert result.status == "available"
    assert result.reliability == "low"


@pytest.mark.parametrize(
    ("response", "reason"),
    [(httpx.Response(429), "rate_limited"), (httpx.Response(503), "unexpected_response")],
)
async def test_instagram_failures(respx_mock, response, reason):
    respx_mock.get(IG_URL).mock(return_value=response)
    assert (await instagram.check("yexo")).reason == reason


# ---------------------------------------------------------------- TikTok

TT_URL = "https://www.tiktok.com/@yexo"


def tiktok_page(user_detail: dict | None) -> str:
    """Mimics the structure of a real profile page (shape observed on tiktok.com)."""
    scope = {"webapp.app-context": {}, "seo.abtest": {}}
    if user_detail is not None:
        scope["webapp.user-detail"] = user_detail
    blob = json.dumps({"__DEFAULT_SCOPE__": scope})
    return (
        "<!DOCTYPE html><html><head><title>TikTok - Make Your Day</title></head><body>"
        f'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">{blob}</script>'
        "</body></html>"
    )


@pytest.mark.parametrize("name", ["y", "yexo.", "ye-xo", "ye xo", "a" * 25])
async def test_tiktok_invalid_usernames(name, respx_mock):
    assert (await tiktok.check(name)).status == "invalid"
    assert not respx_mock.calls


async def test_tiktok_taken(respx_mock):
    page = tiktok_page({"statusCode": 0, "statusMsg": "", "userInfo": {"user": {"uniqueId": "yexo", "nickname": "Yexo ✨"}}})
    route = respx_mock.get(TT_URL).mock(return_value=httpx.Response(200, text=page))

    result = await tiktok.check("YEXO")

    assert result.status == "taken"
    assert result.reliability == "medium"
    assert "Yexo ✨" in result.detail
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT


async def test_tiktok_private_account_is_taken(respx_mock):
    respx_mock.get(TT_URL).mock(return_value=httpx.Response(200, text=tiktok_page({"statusCode": 10222})))
    result = await tiktok.check("yexo")
    assert result.status == "taken"
    assert result.detail == "Compte privé."


async def test_tiktok_not_found_is_available_but_low(respx_mock):
    respx_mock.get(TT_URL).mock(
        return_value=httpx.Response(200, text=tiktok_page({"statusCode": 10221, "statusMsg": "", "needFix": False}))
    )
    result = await tiktok.check("yexo")
    assert result.status == "available"
    assert result.reliability == "low"
    assert "banni" in result.detail  # 10221 also covers banned/deleted handles


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        ("<html><body>Please verify you are human</body></html>", "blocked"),  # captcha shell
        (tiktok_page(None), "blocked"),  # no user-detail scope
        ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">{not json</script>', "blocked"),
        (tiktok_page({"statusCode": 0, "userInfo": {"user": {"uniqueId": "someone_else"}}}), "ambiguous"),
        (tiktok_page({"statusCode": 10101}), "ambiguous"),
    ],
)
async def test_tiktok_never_guesses(respx_mock, page, reason):
    respx_mock.get(TT_URL).mock(return_value=httpx.Response(200, text=page))
    result = await tiktok.check("yexo")
    assert result.status == "uncertain"
    assert result.available is None
    assert result.reason == reason


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(302, headers={"location": "https://www.tiktok.com/login"}), "blocked"),
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(500), "unexpected_response"),
    ],
)
async def test_tiktok_http_failures(respx_mock, response, reason):
    respx_mock.get(TT_URL).mock(return_value=response)
    assert (await tiktok.check("yexo")).reason == reason


# ---------------------------------------------------------------- Gmail


@pytest.mark.parametrize("name", ["yexo.claimd", "yexo42", "Y.e.x.o.o.o", "a" * 30])
async def test_gmail_is_never_verified(name, respx_mock):
    result = await gmail.check(name)
    assert result.status == "unverifiable"
    assert result.available is None
    assert result.method == "none"
    assert result.url is None
    assert not respx_mock.calls  # nothing is ever sent to Google


@pytest.mark.parametrize("name", ["yexo", "a" * 31, ".yexo42", "yexo42.", "ye..xo42", "ye_xo42", "yéxo42", "yexoK42"])
async def test_gmail_rule_violations_are_definite(name, respx_mock):
    result = await gmail.check(name)
    assert result.status == "invalid"
    assert "6 à 30" in result.detail
    assert not respx_mock.calls
