from __future__ import annotations

import types
from typing import Awaitable, Callable

import httpcore
import pytest
from httpcore._backends.auto import AutoBackend

from claimd import config, http
from claimd.checkers import twitch
from claimd.checkers.base import Platform
from claimd.models import Result


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _network_disabled(self, *args, **kwargs):
    raise httpcore.ConnectError("real network is disabled in tests")


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    """Isolate every test from the real network, the developer's .env and shared state.

    Sockets are refused at the lowest level (httpcore's network backend), which
    respx never reaches when it mocks a route: mocked routes keep working and
    any real request fails like an unreachable host.
    """
    monkeypatch.setattr(AutoBackend, "connect_tcp", _network_disabled)
    monkeypatch.setattr(AutoBackend, "connect_unix_socket", _network_disabled)
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
