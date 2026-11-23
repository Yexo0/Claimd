"""Runtime configuration, read from environment variables and an optional `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

DEFAULT_TIMEOUT = 5.0


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    check_timeout: float = DEFAULT_TIMEOUT
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def twitch_configured(self) -> bool:
        return bool(self.twitch_client_id and self.twitch_client_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Real environment variables win over the .env file (override=False).
    load_dotenv(ROOT_DIR / ".env", override=False)
    return Settings(
        twitch_client_id=os.getenv("TWITCH_CLIENT_ID", "").strip(),
        twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", "").strip(),
        check_timeout=_float_env("CHECK_TIMEOUT", DEFAULT_TIMEOUT),
        host=os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int_env("PORT", 8000),
    )
