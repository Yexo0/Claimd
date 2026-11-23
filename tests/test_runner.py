from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import ValidationError

from claimd.models import Result
from claimd.runner import check_all, global_input_error, normalize_username, summarize

from .conftest import fake_checker

pytestmark = pytest.mark.anyio


async def free(platform, username):
    return platform.available(username)


async def taken(platform, username):
    return platform.taken(username)


async def slow(platform, username):
    await asyncio.sleep(10)
    return platform.available(username)


async def boom(platform, username):
    raise RuntimeError("checker bug")


async def wrong_type(platform, username):
    return {"available": True}


async def test_results_keep_registry_order():
    checkers = [fake_checker("a", taken), fake_checker("b", free)]
    results = await check_all("yexo", checkers=checkers, timeout=1)
    assert [r.platform for r in results] == ["a", "b"]
    assert [r.status for r in results] == ["taken", "available"]
    assert all(r.elapsed_ms is not None for r in results)


async def test_checkers_run_in_parallel():
    async def nap(platform, username):
        await asyncio.sleep(0.3)
        return platform.available(username)

    checkers = [fake_checker(f"p{i}", nap) for i in range(4)]
    started = time.perf_counter()
    await check_all("yexo", checkers=checkers, timeout=2)
    assert time.perf_counter() - started < 0.6  # sequential would be >= 1.2 s


async def test_timeout_becomes_uncertain_without_affecting_others():
    checkers = [fake_checker("slow", slow), fake_checker("fast", free)]
    started = time.perf_counter()
    results = await check_all("yexo", checkers=checkers, timeout=0.2)
    assert time.perf_counter() - started < 1

    slow_result, fast_result = results
    assert slow_result.status == "uncertain"
    assert slow_result.available is None
    assert slow_result.reliability == "low"
    assert slow_result.reason == "timeout"
    assert fast_result.status == "available"


@pytest.mark.parametrize("behaviour", [boom, wrong_type])
async def test_broken_checker_is_contained(behaviour):
    results = await check_all("yexo", checkers=[fake_checker("bad", behaviour), fake_checker("ok", free)], timeout=1)
    assert results[0].status == "uncertain"
    assert results[0].reason == "internal_error"
    assert results[1].status == "available"


def test_summary_counts():
    checker = fake_checker("x", free).PLATFORM
    results = [
        checker.available("yexo"),
        checker.taken("yexo"),
        checker.uncertain("yexo", reason="blocked"),
        checker.invalid("yexo", detail="nope"),
        checker.unverifiable("yexo", detail="no API"),
    ]
    summary = summarize(results)
    assert summary.model_dump() == {
        "total": 5,
        "checkable": 4,
        "available": 1,
        "taken": 1,
        "uncertain": 1,
        "invalid": 1,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("yexo", "yexo"), ("  yexo  ", "yexo"), ("@yexo", "yexo"), (" @ yexo", "yexo"), ("@@yexo", "@yexo")],
)
def test_normalize_username(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize(("name", "ok"), [("yexo", True), ("", False), ("a" * 65, False), ("ye\u0000xo", False)])
def test_global_input_error(name, ok):
    assert (global_input_error(name) is None) is ok


@pytest.mark.parametrize(
    ("status", "available"),
    [("available", False), ("available", None), ("taken", True), ("uncertain", True), ("invalid", False)],
)
def test_result_rejects_inconsistent_status(status, available):
    with pytest.raises(ValidationError):
        Result(
            platform="x", label="X", username="y", status=status, available=available,
            method="m", reliability="high",
        )
