"""Data shapes shared by every checker and returned by the API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, model_validator

Reliability = Literal["high", "medium", "low"]

# available    -> the name looks free            (available=True)
# taken        -> an account already uses it     (available=False)
# uncertain    -> blocked, timeout, ambiguous... (available=None)
# invalid      -> the platform would refuse it   (available=None)
# unverifiable -> no legitimate way to check     (available=None)
Status = Literal["available", "taken", "uncertain", "invalid", "unverifiable"]

_EXPECTED_AVAILABLE = {"available": True, "taken": False}


class Result(BaseModel):
    platform: str
    label: str
    username: str
    status: Status
    available: Optional[bool]
    method: str
    reliability: Reliability
    reason: Optional[str] = None  # machine-readable cause, e.g. "timeout"
    detail: Optional[str] = None  # human-readable explanation (French)
    url: Optional[str] = None  # profile URL, to verify by hand
    elapsed_ms: Optional[int] = None

    @model_validator(mode="after")
    def _status_matches_available(self) -> "Result":
        expected = _EXPECTED_AVAILABLE.get(self.status)
        if self.available is not expected:
            raise ValueError(
                f"status={self.status!r} requires available={expected!r}, got {self.available!r}"
            )
        return self


class Summary(BaseModel):
    total: int  # cards shown
    checkable: int  # platforms we can actually verify (the "/N" in "X/N")
    available: int
    taken: int
    uncertain: int
    invalid: int


class CheckResponse(BaseModel):
    username: str
    elapsed_ms: int
    summary: Summary
    results: list[Result]


class PlatformInfo(BaseModel):
    id: str
    label: str
    method: str
    reliability: Reliability
    verifiable: bool
    configured: bool
    rules: Optional[str] = None
    profile_url: Optional[str] = None  # template containing "{username}"
