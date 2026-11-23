"""Twitch — official Helix API. Reliability: high.

Flow: an app access token (client-credentials grant, cached until it expires),
then `GET /helix/users?login=<name>`. A returned user means the name is taken;
an empty list means no *active* account uses it.

Caveat, surfaced in the result detail: Helix doesn't return suspended or
deactivated accounts, and Twitch keeps recently released names on hold for a
while, so "available" means "no active account", not "guaranteed claimable".
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from claimd import config
from claimd.checkers.base import Platform
from claimd.http import get_client
from claimd.models import Result

PLATFORM = Platform(
    id="twitch",
    label="Twitch",
    method="helix_api",
    reliability="high",
    profile_url="https://www.twitch.tv/{username}",
    rules="4 à 25 caractères : lettres, chiffres et _ (pas en première position).",
)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
USERS_URL = "https://api.twitch.tv/helix/users"

LOGIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_]{3,24}")

# Refresh the token a minute before Twitch says it expires.
TOKEN_EXPIRY_MARGIN = 60.0


@dataclass
class _Token:
    value: str
    expires_at: float  # time.monotonic() deadline


_token: Optional[_Token] = None


class _AuthError(Exception):
    """Twitch rejected the client id / secret."""


def is_configured() -> bool:
    return config.get_settings().twitch_configured


def reset_token_cache() -> None:
    global _token
    _token = None


async def _app_token(client: httpx.AsyncClient, settings: config.Settings, *, force: bool = False) -> str:
    global _token
    now = time.monotonic()
    if not force and _token is not None and _token.expires_at > now:
        return _token.value

    resp = await client.post(
        TOKEN_URL,
        data={
            "client_id": settings.twitch_client_id,
            "client_secret": settings.twitch_client_secret,
            "grant_type": "client_credentials",
        },
    )
    if resp.status_code in (400, 401, 403):
        raise _AuthError(resp.status_code)
    resp.raise_for_status()

    payload = resp.json()
    value = payload["access_token"]
    if not isinstance(value, str) or not value:
        raise ValueError("empty access_token")
    expires_in = float(payload.get("expires_in") or 3600)
    _token = _Token(value=value, expires_at=now + max(expires_in - TOKEN_EXPIRY_MARGIN, 30.0))
    return value


async def _get_users(client: httpx.AsyncClient, settings: config.Settings, login: str, token: str) -> httpx.Response:
    return await client.get(
        USERS_URL,
        params={"login": login},
        headers={"Client-Id": settings.twitch_client_id, "Authorization": f"Bearer {token}"},
    )


def _taken_detail(user: dict) -> str:
    name = user.get("display_name") or user.get("login")
    created = str(user.get("created_at") or "")[:4]
    if created.isdigit():
        return f"Compte « {name} », créé en {created}."
    return f"Compte « {name} » actif."


async def check(username: str) -> Result:
    if not LOGIN_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    settings = config.get_settings()
    if not settings.twitch_configured:
        return PLATFORM.uncertain(
            username,
            reason="not_configured",
            detail="Clés Twitch manquantes : ajoute-les dans .env (voir README).",
        )

    client = get_client()
    login = username.lower()
    try:
        token = await _app_token(client, settings)
        resp = await _get_users(client, settings, login, token)
        if resp.status_code == 401:
            # Token revoked or expired early: get a fresh one and retry once.
            token = await _app_token(client, settings, force=True)
            resp = await _get_users(client, settings, login, token)
    except _AuthError:
        return PLATFORM.uncertain(
            username,
            reason="auth_failed",
            detail="Clés Twitch refusées : vérifie TWITCH_CLIENT_ID et TWITCH_CLIENT_SECRET.",
        )
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="Twitch n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre Twitch.")
    except (ValueError, KeyError, TypeError):
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail="Réponse inattendue du serveur d'authentification Twitch."
        )

    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="Limite de requêtes Twitch atteinte, réessaie.")
    if resp.status_code == 401:
        return PLATFORM.uncertain(username, reason="auth_failed", detail="Twitch refuse le jeton d'accès.")
    if resp.status_code != 200:
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail=f"Réponse inattendue de Twitch (HTTP {resp.status_code})."
        )

    try:
        users = resp.json()["data"]
    except (ValueError, KeyError, TypeError):
        users = None
    if not isinstance(users, list):
        return PLATFORM.uncertain(username, reason="unexpected_response", detail="Réponse Twitch illisible.")

    for user in users:
        if isinstance(user, dict) and str(user.get("login", "")).lower() == login:
            return PLATFORM.taken(username, detail=_taken_detail(user))
    if users:
        # Users came back but none matches the login we asked for: don't guess.
        return PLATFORM.uncertain(username, reason="ambiguous", detail="Réponse Twitch ambiguë.")

    return PLATFORM.available(
        username,
        detail="Aucun compte actif. Un compte suspendu ou un nom libéré récemment peut encore le bloquer.",
    )
