#!/usr/bin/env python3
"""Pure-logic unit tests for minimax_mcp.gpu_lock — no GPU, no ComfyUI, no container.

Run:  uv run --project . python tests/unit_gpu_lock.py
Covers: acquire/release/status/held() over fcntl.flock, pointed at a temp
dir via GPU_LOCK_DIR so these tests never touch the real shared lock
(~/.gpu-lock, also used by insta_kb's ig-worker -- see gpu_lock.py's
docstring for why this module is duplicated, not shared, between repos).
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


with tempfile.TemporaryDirectory() as tmp:
    import os

    os.environ["GPU_LOCK_DIR"] = tmp

    from minimax_mcp.gpu_lock import GpuLockTimeout, acquire, held, release, status

    # status() free when nobody holds it
    result = status()
    if result == {"free": True, "holder": None}:
        ok("status() free when nobody holds it")
    else:
        bad(f"status() should be free: {result}")

    # acquire() then status() reports held
    token = acquire("test-holder", timeout=1)
    if token is not None:
        ok("acquire() returned a token")
    else:
        bad("acquire() returned None on a free lock")

    result = status()
    holder = result.get("holder")
    if result.get("free") is False and holder and "test-holder" in holder:
        ok("status() reports held with holder name")
    else:
        bad(f"status() after acquire: {result}")

    # release() frees it again
    assert token is not None
    release(token)
    if status() == {"free": True, "holder": None}:
        ok("release() frees the lock")
    else:
        bad(f"status() after release: {status()}")

    # second acquire times out while held
    first = acquire("first", timeout=1)
    start = time.monotonic()
    second = acquire("second", timeout=0.3)
    elapsed = time.monotonic() - start
    if second is None and elapsed < 2:
        ok("second acquire() times out while held (without hanging)")
    else:
        bad(f"second acquire should time out: second={second} elapsed={elapsed}")
    assert first is not None
    release(first)

    # second acquire succeeds after release
    second = acquire("second", timeout=1)
    if second is not None:
        ok("acquire() succeeds after release")
    else:
        bad("acquire() should succeed once the lock is free again")
    release(second)

    # release() with an unknown token is a no-op, not a raise
    try:
        release("does-not-exist")
        ok("release() with unknown token is a no-op")
    except Exception as exc:  # pragma: no cover
        bad(f"release() with unknown token raised: {exc}")

    # held() releases automatically on exit
    with held("ctx-holder", timeout=1):
        if status()["free"] is False:
            ok("held() holds the lock inside the block")
        else:
            bad("held() should hold the lock inside the block")
    if status() == {"free": True, "holder": None}:
        ok("held() releases automatically on exit")
    else:
        bad(f"status() after held() exit: {status()}")

    # held() releases on exception too
    try:
        with held("ctx-holder-2", timeout=1):
            raise ValueError("boom")
    except ValueError:
        pass
    if status() == {"free": True, "holder": None}:
        ok("held() releases even when the block raises")
    else:
        bad(f"status() after held() exception: {status()}")

    # held() raises GpuLockTimeout when busy
    with held("first", timeout=1):
        try:
            with held("second", timeout=0.2):
                pass
            bad("held() should have raised GpuLockTimeout")
        except GpuLockTimeout as exc:
            if exc.holder == "second" and exc.held_by and "first" in exc.held_by:
                ok("held() raises GpuLockTimeout with holder/held_by set")
            else:
                bad(f"GpuLockTimeout fields wrong: holder={exc.holder} held_by={exc.held_by}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
