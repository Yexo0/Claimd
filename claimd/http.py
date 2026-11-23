"""One shared async HTTP client for every checker (connection pooling, sane timeouts)."""

from __future__ import annotations

from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Optional

import httpx

from claimd import __version__

# Kept below the per-checker hard limit (CHECK_TIMEOUT, 5 s by default) so httpx
# usually reports a clean timeout before the runner has to cancel the checker.
HTTP_TIMEOUT = httpx.Timeout(4.5, connect=3.0)

# Claimd says who it is. YouTube and TikTok answer it exactly like a browser;
# we never pretend to be one.
USER_AGENT = f"Claimd/{__version__} (+https://github.com/Yexo0/Claimd)"

# Content negotiation for profile pages: HTML, in English (stable markers).
PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_client: Optional[httpx.AsyncClient] = None


def _cookieless_jar() -> CookieJar:
    # Probes are stateless: refuse every cookie a site tries to set, so one
    # check never influences the next (no session, no tracking build-up).
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
            max_redirects=5,
            headers={"User-Agent": USER_AGENT},
            cookies=_cookieless_jar(),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
