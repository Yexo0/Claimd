"""Bluesky — official public AT Protocol API. Reliability: high.

`com.atproto.identity.resolveHandle` tells whether <name>.bsky.social is bound
to an account (it returns the account's DID) or not. Custom-domain handles
(e.g. yexo.com) are out of scope.
"""

from __future__ import annotations

import re

import httpx

from claimd.checkers.base import Platform
from claimd.http import get_client
from claimd.models import Result

PLATFORM = Platform(
    id="bluesky",
    label="Bluesky",
    method="official_api",
    reliability="high",
    profile_url="https://bsky.app/profile/{username}.bsky.social",
    rules="3 à 18 caractères : lettres, chiffres et - (pas au début ni à la fin).",
    note=(
        "API publique officielle de Bluesky : on vérifie si pseudo.bsky.social est attribué. "
        "Bluesky réserve certains noms, et les domaines personnalisés ne sont pas couverts."
    ),
)

RESOLVE_URL = "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"
HANDLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{1,16}[A-Za-z0-9]")


async def check(username: str) -> Result:
    if not HANDLE_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    handle = f"{username.lower()}.bsky.social"
    try:
        resp = await get_client().get(RESOLVE_URL, params={"handle": handle}, headers={"Accept": "application/json"})
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="Bluesky n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre Bluesky.")

    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = {}

    if resp.status_code == 200 and str(payload.get("did", "")).startswith("did:"):
        return PLATFORM.taken(username, detail=f"{handle} est attribué.")
    if resp.status_code == 400 and "unable to resolve handle" in str(payload.get("message", "")).lower():
        return PLATFORM.available(
            username,
            reliability="medium",
            detail=f"{handle} n'est attribué à personne. Bluesky réserve toutefois certains noms.",
        )
    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="Bluesky limite les requêtes, réessaie plus tard.")
    return PLATFORM.uncertain(
        username, reason="unexpected_response", detail=f"Réponse inattendue de Bluesky (HTTP {resp.status_code})."
    )
