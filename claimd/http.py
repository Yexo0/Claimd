"""One shared async HTTP client for every checker (connection pooling, sane timeouts)."""

from __future__ import annotations

from typing import Optional

import httpx

from claimd import __version__

# Kept below the per-checker hard limit (CHECK_TIMEOUT, 5 s by default) so httpx
# usually reports a clean timeout before the runner has to cancel the checker.
HTTP_TIMEOUT = httpx.Timeout(4.5, connect=3.0)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": f"Claimd/{__version__}"},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
