"""FastAPI app: the JSON API and the static frontend, on a single port."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from claimd import __version__
from claimd import checkers as registry
from claimd.config import FRONTEND_DIR
from claimd.http import close_client
from claimd.models import CheckResponse, PlatformInfo
from claimd.runner import check_all, global_input_error, normalize_username, summarize


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_client()


app = FastAPI(
    title="Claimd",
    version=__version__,
    summary="Vérifie la disponibilité d'un pseudo sur plusieurs plateformes.",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/platforms", response_model=list[PlatformInfo], tags=["check"])
async def platforms() -> list[PlatformInfo]:
    """Platforms in display order, so the UI can lay out its cards before any check."""
    return [c.PLATFORM.info(configured=registry.is_configured(c)) for c in registry.CHECKERS]


@app.get("/check/{username}", response_model=CheckResponse, tags=["check"])
async def check(username: str) -> CheckResponse:
    """Run every checker in parallel and return one result per platform."""
    name = normalize_username(username)
    error = global_input_error(name)
    if error:
        raise HTTPException(status_code=422, detail=error)

    started = time.perf_counter()
    results = await check_all(name)
    return CheckResponse(
        username=name,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        summary=summarize(results),
        results=results,
    )


# Mounted last so the API routes above take precedence over static files.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
