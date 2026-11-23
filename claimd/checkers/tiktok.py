"""TikTok — best-effort read of the profile page's public data. Reliability: low.

TikTok answers HTTP 200 for every handle. The verdict lives in the JSON the page
embeds (`__UNIVERSAL_DATA_FOR_REHYDRATION__` -> `webapp.user-detail`):
- statusCode 0 and the same uniqueId -> taken
- statusCode 10222 (private account)  -> taken
- statusCode 10221                    -> no visible account. TikTok uses this code
  for unknown *and* banned/deleted handles, so "available" is low reliability.
No JSON (captcha, verification page) or anything unexpected -> uncertain.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from claimd.checkers.base import Platform
from claimd.http import PAGE_HEADERS, get_client
from claimd.models import Result

PLATFORM = Platform(
    id="tiktok",
    label="TikTok",
    method="http_probe",
    reliability="low",
    profile_url="https://www.tiktok.com/@{username}",
    rules="2 à 24 caractères : lettres, chiffres, _ et . (pas de point à la fin).",
    note=(
        "Lecture des données publiques intégrées à la page profil. Un compte banni ou supprimé "
        "y apparaît comme inexistant : un nom « libre » peut donc rester bloqué."
    ),
)

USERNAME_RE = re.compile(r"[A-Za-z0-9_.]{1,23}[A-Za-z0-9_]")
DATA_RE = re.compile(r'<script[^>]*\bid="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)

STATUS_OK = 0
STATUS_NOT_FOUND = 10221  # unknown, banned or deleted handle
STATUS_PRIVATE = 10222


def _user_detail(html: str) -> Optional[dict]:
    match = DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    detail = (data.get("__DEFAULT_SCOPE__") or {}).get("webapp.user-detail") if isinstance(data, dict) else None
    return detail if isinstance(detail, dict) else None


async def check(username: str) -> Result:
    if not USERNAME_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    try:
        # Handles are case-insensitive and stored lowercase: query the canonical form.
        resp = await get_client().get(
            PLATFORM.url_for(username.lower()), headers=PAGE_HEADERS, follow_redirects=False
        )
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="TikTok n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre TikTok.")

    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="TikTok limite les requêtes, réessaie plus tard.")
    if resp.is_redirect:
        return PLATFORM.uncertain(username, reason="blocked", detail="TikTok a redirigé la requête (vérification anti-robot ?).")
    if resp.status_code != 200:
        return PLATFORM.uncertain(
            username, reason="unexpected_response", detail=f"Réponse inattendue de TikTok (HTTP {resp.status_code})."
        )

    detail = _user_detail(resp.text)
    if detail is None:
        return PLATFORM.uncertain(
            username, reason="blocked", detail="Page TikTok sans données exploitables (captcha ou vérification probable)."
        )

    code = detail.get("statusCode")
    user = (detail.get("userInfo") or {}).get("user") or {}
    unique_id = user.get("uniqueId") if isinstance(user, dict) else None
    same_user = isinstance(unique_id, str) and unique_id.lower() == username.lower()

    if code == STATUS_OK and same_user:
        nickname = user.get("nickname") or unique_id
        return PLATFORM.taken(username, reliability="medium", detail=f"Compte « {nickname} ».")
    if code == STATUS_PRIVATE and (unique_id is None or same_user):
        return PLATFORM.taken(username, reliability="medium", detail="Compte privé.")
    if code == STATUS_NOT_FOUND and not unique_id:
        return PLATFORM.available(
            username, detail="Aucun compte visible. Un compte banni ou supprimé peut encore bloquer ce nom."
        )
    return PLATFORM.uncertain(username, reason="ambiguous", detail="Réponse TikTok ambiguë.")
