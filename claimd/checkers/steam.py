"""Steam — public community profile, custom URL. Reliability: high.

On Steam, the only unique handle is the custom profile URL
(steamcommunity.com/id/<name>); display names are not unique. The community
site serves a public XML view of any profile URL (`?xml=1`): a profile with a
steamID64, or an explicit "profile could not be found" error.
"""

from __future__ import annotations

import re

import httpx

from claimd.checkers.base import Platform
from claimd.http import get_client
from claimd.models import Result

PLATFORM = Platform(
    id="steam",
    label="Steam",
    method="public_profile",
    reliability="high",
    profile_url="https://steamcommunity.com/id/{username}",
    rules="URL perso : 3 à 32 caractères, lettres, chiffres, _ et -.",
    note=(
        "Vue XML publique de steamcommunity.com/id/pseudo. On vérifie l'URL personnalisée, "
        "le seul identifiant Steam unique (le nom affiché, lui, peut être partagé)."
    ),
)

NAME_RE = re.compile(r"[A-Za-z0-9_-]{3,32}")
STEAMID_RE = re.compile(r"<steamID64>\s*(\d{17})\s*</steamID64>")
NAME_TAG_RE = re.compile(r"<steamID>\s*<!\[CDATA\[(.*?)\]\]>\s*</steamID>", re.S)
NOT_FOUND = "the specified profile could not be found"


async def check(username: str) -> Result:
    if not NAME_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    url = f"{PLATFORM.url_for(username.lower())}/?xml=1"
    try:
        resp = await get_client().get(url, headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.5"})
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="Steam n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre Steam.")

    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="Steam limite les requêtes, réessaie plus tard.")
    if resp.status_code != 200:
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail=f"Réponse inattendue de Steam (HTTP {resp.status_code})."
        )

    body = resp.text
    if STEAMID_RE.search(body):
        match = NAME_TAG_RE.search(body)
        name = match.group(1).strip() if match else ""
        return PLATFORM.taken(username, detail=f"Profil « {name} »." if name else "Un profil utilise cette URL.")
    if NOT_FOUND in body.lower():
        return PLATFORM.available(username, detail="Aucun profil à cette URL personnalisée.")
    return PLATFORM.uncertain(username, reason="ambiguous", detail="Réponse Steam ambiguë.")
