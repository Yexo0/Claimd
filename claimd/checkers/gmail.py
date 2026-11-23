"""Gmail — deliberately not verified.

There is no legitimate, reliable way to know whether a Gmail address exists:
no public API, SMTP probing is blocked by Gmail, and the sign-up form is
captcha-protected and off-limits to automation under Google's terms. Claimd
therefore never sends anything to Google.

The only definite answer is local: if the name breaks Gmail's public username
rules, it can't be registered, and we say so.
"""

from __future__ import annotations

import re

from claimd.checkers.base import Platform
from claimd.models import Result

PLATFORM = Platform(
    id="gmail",
    label="Gmail",
    method="none",
    reliability="low",
    rules="6 à 30 caractères : lettres, chiffres et points (pas au début, à la fin, ni deux à la suite).",
    note=(
        "Google ne fournit aucune API pour savoir si une adresse existe. Le sondage SMTP est bloqué "
        "par Gmail, et le formulaire d'inscription est protégé par captcha et interdit à "
        "l'automatisation. Claimd préfère ne rien affirmer."
    ),
    verifiable=False,
)

GMAIL_RE = re.compile(r"[a-z0-9](?:[a-z0-9]|\.(?!\.)){4,28}[a-z0-9]", re.IGNORECASE | re.ASCII)


async def check(username: str) -> Result:
    if not GMAIL_RE.fullmatch(username):
        return PLATFORM.invalid(username, detail="Impossible sur Gmail : 6 à 30 caractères, lettres, chiffres et points.")
    return PLATFORM.unverifiable(username, detail="Aucun moyen fiable et légitime de le vérifier.")
