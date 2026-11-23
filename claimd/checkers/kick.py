"""Kick — official public API. Reliability: high.

Same model as Twitch: an app access token (client credentials, cached), then
`GET api.kick.com/public/v1/channels?slug=…`. Kick's OpenAPI spec accepts an
app token for this endpoint.

Kick usernames may contain "_" while channel slugs use "-" (Yexo_FPS ->
yexo-fps), so both spellings are queried in one request.
"""

from __future__ import annotations

import re

import httpx

from claimd import config
from claimd.checkers.base import Platform
from claimd.checkers.oauth import AppToken, AuthError
from claimd.http import get_client
from claimd.models import Result

PLATFORM = Platform(
    id="kick",
    label="Kick",
    method="official_api",
    reliability="high",
    profile_url="https://kick.com/{username}",
    rules="Jusqu'à 25 caractères : lettres, chiffres, _ et -.",
    note=(
        "API officielle Kick (jeton d'application, comme Twitch). « Libre » veut dire "
        "« aucune chaîne active » : un compte banni peut encore bloquer le nom."
    ),
)

TOKEN_URL = "https://id.kick.com/oauth/token"
CHANNELS_URL = "https://api.kick.com/public/v1/channels"

SLUG_RE = re.compile(r"[A-Za-z0-9_-]{1,25}")

_token = AppToken(TOKEN_URL)


def is_configured() -> bool:
    return config.get_settings().kick_configured


def reset_token_cache() -> None:
    _token.reset()


def slugs_for(username: str) -> list[str]:
    base = username.lower()
    return sorted({base, base.replace("_", "-")})


async def _channels(client: httpx.AsyncClient, slugs: list[str], token: str) -> httpx.Response:
    return await client.get(
        CHANNELS_URL,
        params=[("slug", s) for s in slugs],
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )


async def check(username: str) -> Result:
    if not SLUG_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    settings = config.get_settings()
    if not settings.kick_configured:
        return PLATFORM.uncertain(
            username,
            reason="not_configured",
            detail="Clés Kick manquantes : ajoute-les dans .env (voir README).",
        )

    client = get_client()
    slugs = slugs_for(username)
    try:
        token = await _token.get(client, settings.kick_client_id, settings.kick_client_secret)
        resp = await _channels(client, slugs, token)
        if resp.status_code == 401:
            token = await _token.get(client, settings.kick_client_id, settings.kick_client_secret, force=True)
            resp = await _channels(client, slugs, token)
    except AuthError:
        return PLATFORM.uncertain(
            username,
            reason="auth_failed",
            detail="Clés Kick refusées : vérifie KICK_CLIENT_ID et KICK_CLIENT_SECRET.",
        )
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="Kick n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre Kick.")
    except (ValueError, KeyError, TypeError):
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail="Réponse inattendue du serveur d'authentification Kick."
        )

    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="Kick limite les requêtes, réessaie plus tard.")
    if resp.status_code in (401, 403):
        return PLATFORM.uncertain(username, reason="auth_failed", detail="Kick refuse le jeton d'accès.")
    if resp.status_code != 200:
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail=f"Réponse inattendue de Kick (HTTP {resp.status_code})."
        )

    try:
        channels = resp.json()["data"]
    except (ValueError, KeyError, TypeError):
        channels = None
    if not isinstance(channels, list):
        return PLATFORM.uncertain(username, reason="unexpected_response", detail="Réponse Kick illisible.")

    for channel in channels:
        slug = str(channel.get("slug", "")).lower() if isinstance(channel, dict) else ""
        if slug in slugs:
            return PLATFORM.taken(
                username, detail=f"Chaîne « {slug} ».", url=PLATFORM.url_for(slug)
            )
    if channels:
        return PLATFORM.uncertain(username, reason="ambiguous", detail="Réponse Kick ambiguë.")
    return PLATFORM.available(
        username,
        detail="Aucune chaîne active à ce nom. Un compte banni peut encore le bloquer.",
        url=PLATFORM.url_for(slugs[-1] if "_" in username else slugs[0]),
    )
