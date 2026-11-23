"""YouTube — probe of youtube.com/@handle. Reliability: medium.

A HEAD request is enough: YouTube answers 200 for an existing handle and 404
for an unknown one, without sending the ~2 MB channel page.

Limits: a handle can be unavailable without a public channel behind it
(reserved handles, recently deleted channels), so a 404 is a strong hint, not
a guarantee. Any redirect that leaves YouTube (consent page, "unusual traffic"
check) is reported as uncertain.
"""

from __future__ import annotations

import re

import httpx

from claimd.checkers.base import Platform
from claimd.http import PAGE_HEADERS, get_client
from claimd.models import Result

PLATFORM = Platform(
    id="youtube",
    label="YouTube",
    method="http_probe",
    reliability="medium",
    profile_url="https://www.youtube.com/@{username}",
    rules="3 à 30 caractères : lettres, chiffres, _ - . · (pas au début ni à la fin).",
    note=(
        "Sonde de youtube.com/@pseudo : 200 = pris, 404 = libre. Un handle réservé, "
        "ou celui d'une chaîne supprimée, peut rester indisponible sans que ce soit visible."
    ),
)

# Letters and digits from any script, plus _ - . · in the middle only.
HANDLE_RE = re.compile(r"[^\W_][\w.\-·]{1,28}[^\W_]")

YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com"}
CHANNEL_PATHS = ("/@", "/channel/", "/c/", "/user/")

# "Reject all" consent cookie: skips the EU consent interstitial without
# accepting any tracking.
CONSENT_COOKIE = "SOCS=CAI"


async def check(username: str) -> Result:
    if not HANDLE_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    try:
        resp = await get_client().head(
            PLATFORM.url_for(username),
            headers={**PAGE_HEADERS, "Cookie": CONSENT_COOKIE},
            follow_redirects=True,
        )
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="YouTube n'a pas répondu à temps.")
    except httpx.TooManyRedirects:
        return PLATFORM.uncertain(username, reason="ambiguous", detail="YouTube redirige en boucle.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre YouTube.")

    if resp.url.host not in YOUTUBE_HOSTS:
        return PLATFORM.uncertain(
            username, reason="blocked", detail="YouTube a redirigé vers une page de consentement ou de vérification."
        )
    if resp.status_code == 404:
        return PLATFORM.available(
            username, detail="Aucune chaîne à ce handle. Un handle réservé peut quand même être refusé."
        )
    if resp.status_code == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="YouTube limite les requêtes, réessaie plus tard.")
    if resp.status_code == 200:
        if resp.url.path.startswith(CHANNEL_PATHS):
            return PLATFORM.taken(username, detail="Une chaîne utilise déjà ce handle.")
        return PLATFORM.uncertain(username, reason="ambiguous", detail="YouTube a renvoyé une page inattendue.")
    return PLATFORM.uncertain(
        username, reason="unexpected_response", detail=f"Réponse inattendue de YouTube (HTTP {resp.status_code})."
    )
