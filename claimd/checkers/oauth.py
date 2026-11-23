"""OAuth client-credentials ("app access token") shared by API-based checkers.

The token is cached until shortly before it expires; `force=True` fetches a
new one (after the API rejected the cached token).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx

# Refresh a minute before the provider says the token expires.
EXPIRY_MARGIN = 60.0


class AuthError(Exception):
    """The provider rejected the client id / secret."""


@dataclass
class _Token:
    value: str
    expires_at: float  # time.monotonic() deadline


class AppToken:
    def __init__(self, token_url: str) -> None:
        self.token_url = token_url
        self._token: Optional[_Token] = None

    def reset(self) -> None:
        self._token = None

    async def get(
        self,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        *,
        force: bool = False,
    ) -> str:
        now = time.monotonic()
        if not force and self._token is not None and self._token.expires_at > now:
            return self._token.value

        # Secrets travel in the form body, never in the URL.
        resp = await client.post(
            self.token_url,
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        )
        if resp.status_code in (400, 401, 403):
            raise AuthError(resp.status_code)
        resp.raise_for_status()

        payload = resp.json()
        value = payload["access_token"]
        if not isinstance(value, str) or not value:
            raise ValueError("empty access_token")
        expires_in = float(payload.get("expires_in") or 3600)
        self._token = _Token(value=value, expires_at=now + max(expires_in - EXPIRY_MARGIN, 30.0))
        return value
