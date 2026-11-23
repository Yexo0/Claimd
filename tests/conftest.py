from __future__ import annotations

import types
from typing import Awaitable, Callable

import pytest

from claimd import config, http
from claimd.checkers import twitch
from claimd.checkers.base import Platform
from claimd.models import Result


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    """Isolate every test from the developer's real .env and from shared state."""
    current = config.Settings()
    monkeypatch.setattr(config, "get_settings", lambda: current)
    twitch.reset_token_cache()
    http._client = None
    yield
    twitch.reset_token_cache()
    http._client = None


@pytest.fixture
def use_settings(monkeypatch) -> Callable[..., config.Settings]:
    def apply(**overrides) -> config.Settings:
        settings = config.Settings(**overrides)
        monkeypatch.setattr(config, "get_settings", lambda: settings)
        return settings

    return apply


def fake_checker(
    platform_id: str,
    behaviour: Callable[[Platform, str], Awaitable[Result]],
    *,
    label: str | None = None,
    verifiable: bool = True,
) -> types.SimpleNamespace:
    """A stand-in checker module: PLATFORM + async check(username)."""
    platform = Platform(
        id=platform_id,
        label=label or platform_id.title(),
        method="fake",
        reliability="high",
        profile_url=f"https://example.test/{platform_id}/{{username}}",
        verifiable=verifiable,
    )

    async def check(username: str) -> Result:
        return await behaviour(platform, username)

    return types.SimpleNamespace(PLATFORM=platform, check=check)
