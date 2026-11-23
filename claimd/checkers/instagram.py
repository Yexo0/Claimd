"""Instagram — profile page, best effort. Reliability: low (high with a session).

Logged out, Instagram often answers automated requests with a redirect to its
login page (almost always from datacenter IPs). That is an access control:
Claimd never tries to get around it and reports "uncertain" instead.

Optional: INSTAGRAM_SESSIONID in .env makes Claimd look at the profile the
normal way, logged in with *your own* session, like your browser does. Off by
default: Instagram's terms forbid automated access, so any restriction would
hit the account that session belongs to. The cookie is only ever sent to
www.instagram.com (fixed URL, redirects not followed).

Conclusions are only drawn from unambiguous signals:
- HTTP 404                                   -> available
- a profile page that names the exact handle -> taken
- anything else (login wall, challenge, rate limit, page without markers) -> uncertain

Results are cached for 10 minutes (see runner): re-running a search does not
hit Instagram again, which keeps its rate limiting at bay.
"""

from __future__ import annotations

import re

import httpx

from claimd import config
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
        "les requêtes automatiques : Claimd affiche alors « incertain » au lieu de deviner. "
        "Option : ta propre session dans .env (voir README)."
    ),
    cache_ttl=600,
)

SESSION_METHOD = "session_probe"

USERNAME_RE = re.compile(r"(?!\.)(?!.*\.\.)[A-Za-z0-9._]{1,30}(?<!\.)")
# Cookie value characters (RFC 6265 cookie-octet): no spaces, quotes, commas,
# semicolons or backslashes, so the value can't inject anything into the header.
COOKIE_VALUE_RE = re.compile(r"[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]+")


def session_id() -> str:
    raw = config.get_settings().instagram_sessionid.strip()
    if raw.lower().startswith("sessionid="):  # people paste "sessionid=…"
        raw = raw.split("=", 1)[1].strip()
    return raw


def current_method() -> str:
    return SESSION_METHOD if session_id() else PLATFORM.method


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

    session = session_id()
    method = SESSION_METHOD if session else PLATFORM.method
    if session and not COOKIE_VALUE_RE.fullmatch(session):
        return PLATFORM.uncertain(
            username,
            method=method,
            reason="not_configured",
            detail="INSTAGRAM_SESSIONID est mal formé dans .env : recopie la valeur du cookie sessionid.",
        )

    headers = dict(PAGE_HEADERS)
    if session:
        headers["Cookie"] = f"sessionid={session}"

    try:
        # Handles are case-insensitive and stored lowercase: query the canonical form.
        resp = await get_client().get(PLATFORM.url_for(username.lower()), headers=headers, follow_redirects=False)
    except httpx.TimeoutException:
        return PLATFORM.uncertain(username, method=method, reason="timeout", detail="Instagram n'a pas répondu à temps.")
    except httpx.HTTPError:
        return PLATFORM.uncertain(username, method=method, reason="network_error", detail="Impossible de joindre Instagram.")

    status = resp.status_code
    if status == 404:
        return PLATFORM.available(
            username,
            method=method,
            reliability="medium" if session else "low",
            detail="Page de profil introuvable. Un compte désactivé peut encore bloquer ce nom.",
        )
    if status == 429:
        return PLATFORM.uncertain(
            username, method=method, reason="rate_limited", detail="Instagram limite les requêtes, réessaie plus tard."
        )
    if resp.is_redirect:
        location = resp.headers.get("location", "")
        if "/accounts/login" in location:
            if session:
                return PLATFORM.uncertain(
                    username,
                    method=method,
                    reason="session_expired",
                    detail="Ta session Instagram a expiré : mets à jour INSTAGRAM_SESSIONID dans .env.",
                )
            return PLATFORM.uncertain(
                username,
                method=method,
                reason="login_wall",
                detail="Instagram exige une connexion pour afficher ce profil : impossible de conclure.",
            )
        if "challenge" in location or "/accounts/suspended" in location:
            detail = (
                "Instagram demande une vérification de ton compte : ouvre l'app pour la valider."
                if session
                else "Instagram demande une vérification anti-robot."
            )
            return PLATFORM.uncertain(username, method=method, reason="blocked", detail=detail)
        return PLATFORM.uncertain(
            username, method=method, reason="ambiguous", detail="Instagram a redirigé la requête : impossible de conclure."
        )
    if status == 200:
        if _names_profile(resp.text, username):
            return PLATFORM.taken(
                username,
                method=method,
                reliability="high" if session else "medium",
                detail="Un profil utilise ce nom.",
            )
        return PLATFORM.uncertain(
            username,
            method=method,
            reason="ambiguous",
            detail="Page Instagram sans indice fiable (connexion requise ou page en JS).",
        )
    return PLATFORM.uncertain(
        username, method=method, reason="unexpected_response", detail=f"Réponse inattendue d'Instagram (HTTP {status})."
    )
