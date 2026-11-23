"""Building blocks for checkers.

A checker is a module in this package that exposes:

    PLATFORM: Platform
    async def check(username: str) -> Result

`Platform` carries the static metadata and builds consistent `Result` objects,
so a checker only has to decide *which* outcome applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.parse import quote

from claimd.models import PlatformInfo, Reliability, Result, Status


@dataclass(frozen=True)
class Platform:
    id: str
    label: str
    method: str
    reliability: Reliability  # nominal reliability of a definite answer
    profile_url: Optional[str] = None  # template containing "{username}"
    rules: Optional[str] = None  # username rules, shown when the input is invalid
    note: Optional[str] = None  # how the check works and its limits (UI tooltip)
    verifiable: bool = True

    def url_for(self, username: str) -> Optional[str]:
        if not self.profile_url:
            return None
        return self.profile_url.format(username=quote(username, safe=""))

    def _result(
        self,
        username: str,
        status: Status,
        available: Optional[bool],
        *,
        reliability: Optional[Reliability] = None,
        method: Optional[str] = None,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
        link: bool = True,
    ) -> Result:
        return Result(
            platform=self.id,
            label=self.label,
            username=username,
            status=status,
            available=available,
            method=method or self.method,
            reliability=reliability or self.reliability,
            reason=reason,
            detail=detail,
            url=self.url_for(username) if link else None,
        )

    def available(self, username: str, **kwargs) -> Result:
        return self._result(username, "available", True, **kwargs)

    def taken(self, username: str, **kwargs) -> Result:
        return self._result(username, "taken", False, **kwargs)

    def uncertain(self, username: str, *, reason: str, detail: Optional[str] = None, **kwargs) -> Result:
        # Never a guess: an uncertain answer is always null + low reliability.
        kwargs.setdefault("reliability", "low")
        return self._result(username, "uncertain", None, reason=reason, detail=detail, **kwargs)

    def invalid(self, username: str, *, detail: Optional[str] = None) -> Result:
        # The platform's own rules reject the name: we are sure it can't be claimed.
        return self._result(
            username,
            "invalid",
            None,
            reliability="high",
            method="validation",
            reason="invalid_username",
            detail=detail or self.rules,
            link=False,
        )

    def unverifiable(self, username: str, *, detail: str) -> Result:
        return self._result(
            username,
            "unverifiable",
            None,
            reliability="low",
            method="none",
            reason="unverifiable",
            detail=detail,
            link=False,
        )

    def info(self, *, configured: bool = True) -> PlatformInfo:
        return PlatformInfo(
            id=self.id,
            label=self.label,
            method=self.method,
            reliability=self.reliability,
            verifiable=self.verifiable,
            configured=configured,
            rules=self.rules,
            note=self.note,
            profile_url=self.profile_url,
        )


class Checker(Protocol):
    """What the runner expects from a checker module."""

    PLATFORM: Platform

    async def check(self, username: str) -> Result: ...
