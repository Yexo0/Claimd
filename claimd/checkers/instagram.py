"""Instagram — best-effort probe of the profile page. Reliability: low.

Instagram frequently answers logged-out, automated requests with a redirect to
its login page (always, from datacenter IPs). That is an access control: Claimd
does not try to get around it and reports "uncertain" instead.

Conclusions are only drawn from unambiguous signals:
- HTTP 404                                   -> available (low)
- a profile page that names the exact handle -> taken (medium)
- anything else (login wall, challenge, rate limit, page without markers) -> uncertain
"""

from __future__ import annotations

import re

import httpx

from claimd.checkers.base import Platform
from claimd.http import PAGE_HEADERS, get_client
from claimd.models import Result

PLATFORM = Platform(
    id="instagram",
    label="Instagram",
    method="http_probe",
    reliability="low",
    profile_url="https://www.instagram.com/{username}/",
    rules="1 à 30 caractères : lettres, chiffres, _ et . (pas de point au début, à la fin, ni deux à la suite).",
    note=(
        "Sonde de la page profil, au mieux. Instagram exige souvent une connexion ou bloque "
        "les requêtes automatiques : Claimd affiche alors « incertain » au lieu de deviner."
    ),
)

USERNAME_RE = re.compile(r"(?!\.)(?!.*\.\.)[A-Za-z0-9._]{1,30}(?<!\.)")


def _names_profile(html: str, username: str) -> bool:
    """True if the page explicitly describes the profile of `username`."""
    handle = re.escape(username.lower())
    end = r"(?![a-z0-9._])"
    markers = (
        rf"instagram://user\?username={handle}{end}",  # app deep link meta tag
        rf"\(@{handle}\)",  # "Name (@handle) • Instagram photos and videos"
        rf'"username":"{handle}"',  # embedded profile JSON
    )
    text = html.lower()
    return any(re.search(marker, text) for marker in markers)


async def check(username: str) -> Result:
    if not USERNAME_RE.fullmatch(username):
        return PLATFORM.invalid(username)

    try:
        # Handles are case-insensitive and stored lowercase: query the canonical form.
        resp = await get_client().get(
            PLATFORM.url_for(username.lower()), headers=PAGE_HEADERS, follow_redirects=False
        )
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, reason="timeout", detail="Instagram n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, reason="network_error", detail="Impossible de joindre Instagram.")

    status = resp.status_code
    if status == 404:
        return PLATFORM.available(
            username,
            reliability="low",
            detail="Page de profil introuvable. Un compte désactivé peut encore bloquer ce nom.",
        )
    if status == 429:
        return PLATFORM.uncertain(username, reason="rate_limited", detail="Instagram limite les requêtes, réessaie plus tard.")
    if resp.is_redirect:
        location = resp.headers.get("location", "")
        if "/accounts/login" in location:
            return PLATFORM.uncertain(
                username,
                reason="login_wall",
                detail="Instagram exige une connexion pour afficher ce profil : impossible de conclure.",
            )
        if "challenge" in location:
            return PLATFORM.uncertain(username, reason="blocked", detail="Instagram demande une vérification anti-robot.")
        return PLATFORM.uncertain(username, reason="ambiguous", detail="Instagram a redirigé la requête : impossible de conclure.")
    if status == 200:
        if _names_profile(resp.text, username):
            return PLATFORM.taken(username, reliability="medium", detail="Un profil public utilise ce nom.")
        return PLATFORM.uncertain(
            username, reason="ambiguous", detail="Page Instagram sans indice fiable (connexion requise ou page en JS)."
        )
    return PLATFORM.uncertain(
        username, reason="unexpected_response", detail=f"Réponse inattendue d'Instagram (HTTP {status})."
    )
