"""Checker registry.

To add a platform: create `checkers/<name>.py` exposing `PLATFORM` (a
`Platform`) and `async def check(username: str) -> Result`, then list the
module below. Optionally expose `is_configured() -> bool` if the checker needs
credentials. To remove a platform, drop it from the tuple.

The order of CHECKERS is the display order in the UI.
"""

from __future__ import annotations

from claimd.checkers import bluesky, gmail, instagram, kick, steam, tiktok, twitch, youtube
from claimd.checkers.base import Checker, Platform

CHECKERS: tuple[Checker, ...] = (  # type: ignore[assignment]
    twitch,
    youtube,
    instagram,
    tiktok,
    kick,
    bluesky,
    steam,
    gmail,
)

__all__ = ["CHECKERS", "Checker", "Platform", "current_method", "info", "is_configured", "unverifiable_ids"]


def is_configured(checker: Checker) -> bool:
    probe = getattr(checker, "is_configured", None)
    return bool(probe()) if callable(probe) else True


def current_method(checker: Checker) -> str:
    """A checker may switch method with its config (e.g. Instagram with a session)."""
    probe = getattr(checker, "current_method", None)
    return probe() if callable(probe) else checker.PLATFORM.method


def info(checker: Checker):
    return checker.PLATFORM.info(configured=is_configured(checker), method=current_method(checker))


def unverifiable_ids(checkers=None) -> frozenset[str]:
    """Platforms shown for information only; they don't count in "free on X/N"."""
    selected = CHECKERS if checkers is None else checkers
    return frozenset(c.PLATFORM.id for c in selected if not c.PLATFORM.verifiable)
