"""Checker registry.

To add a platform: create `checkers/<name>.py` exposing `PLATFORM` (a
`Platform`) and `async def check(username: str) -> Result`, then list the
module below. Optionally expose `is_configured() -> bool` if the checker needs
credentials. To remove a platform, drop it from the tuple.

The order of CHECKERS is the display order in the UI.
"""

from __future__ import annotations

from claimd.checkers import twitch
from claimd.checkers.base import Checker, Platform

CHECKERS: tuple[Checker, ...] = (twitch,)  # type: ignore[assignment]

__all__ = ["CHECKERS", "Checker", "Platform", "is_configured"]


def is_configured(checker: Checker) -> bool:
    probe = getattr(checker, "is_configured", None)
    return bool(probe()) if callable(probe) else True
