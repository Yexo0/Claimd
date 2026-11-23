"""Runs every checker in parallel. A single platform failing never breaks the response."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Collection, Optional, Sequence

from claimd import checkers as registry
from claimd import config
from claimd.checkers.base import Checker
from claimd.models import Result, Summary

logger = logging.getLogger("claimd")

MAX_USERNAME_LENGTH = 64


def normalize_username(raw: str) -> str:
    """Trim whitespace and one leading '@' (people paste handles like '@yexo')."""
    name = raw.strip()
    if name.startswith("@"):
        name = name[1:].strip()
    return name


def global_input_error(username: str) -> Optional[str]:
    """Reject inputs no platform could accept. Per-platform rules live in each checker."""
    if not username:
        return "Saisis un pseudo."
    if len(username) > MAX_USERNAME_LENGTH:
        return f"Pseudo trop long ({MAX_USERNAME_LENGTH} caractères maximum)."
    if any(not ch.isprintable() for ch in username):
        return "Le pseudo contient des caractères invisibles."
    return None


async def run_checker(checker: Checker, username: str, timeout: float) -> Result:
    platform = checker.PLATFORM
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(checker.check(username), timeout=timeout)
        if not isinstance(result, Result):
            raise TypeError(f"{platform.id}.check() returned {type(result).__name__}, not Result")
    except (asyncio.TimeoutError, TimeoutError):
        result = platform.uncertain(username, reason="timeout", detail=f"Pas de réponse en {timeout:g} s.")
    except Exception:
        logger.exception("Checker %r crashed for username %r", platform.id, username)
        result = platform.uncertain(username, reason="internal_error", detail="Erreur inattendue pendant la vérification.")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return result.model_copy(update={"elapsed_ms": elapsed_ms})


def _selection(checkers: Optional[Sequence[Checker]], timeout: Optional[float]) -> tuple[Sequence[Checker], float]:
    selected = registry.CHECKERS if checkers is None else checkers
    limit = timeout if timeout is not None else config.get_settings().check_timeout
    return selected, limit


async def check_all(
    username: str,
    checkers: Optional[Sequence[Checker]] = None,
    timeout: Optional[float] = None,
) -> list[Result]:
    """Every result, in registry (display) order, once the slowest checker is done."""
    selected, limit = _selection(checkers, timeout)
    return list(await asyncio.gather(*(run_checker(c, username, limit) for c in selected)))


async def iter_results(
    username: str,
    checkers: Optional[Sequence[Checker]] = None,
    timeout: Optional[float] = None,
) -> AsyncIterator[Result]:
    """Yield each result as soon as its checker finishes (fastest first)."""
    selected, limit = _selection(checkers, timeout)
    tasks = [asyncio.ensure_future(run_checker(c, username, limit)) for c in selected]
    try:
        for next_done in asyncio.as_completed(tasks):
            yield await next_done
    finally:
        # Client gone or consumer stopped early: don't leave probes running.
        for task in tasks:
            if not task.done():
                task.cancel()


def summarize(results: Sequence[Result], unverifiable_ids: Collection[str] = ()) -> Summary:
    def count(status: str) -> int:
        return sum(1 for r in results if r.status == status)

    return Summary(
        total=len(results),
        checkable=sum(1 for r in results if r.status != "unverifiable" and r.platform not in unverifiable_ids),
        available=count("available"),
        taken=count("taken"),
        uncertain=count("uncertain"),
        invalid=count("invalid"),
    )
