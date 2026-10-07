#!/usr/bin/env python3
"""Unit tests for minimax_mcp.comfyui_client transport behavior — no live ComfyUI.

Run:  uv run --project . python tests/unit_client.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.

Covers the review fast-follow (2026-10-07): transport failures while
polling (httpx.ConnectError from GET /history, OSError from the /ws
handshake) must surface as ComfyUITimeout, never as a raw exception.
Upstream (core.wait_for_video_core) treats anything that is neither
ComfyUITimeout nor ComfyUIError as "the job never started" and releases
the GPU lock — while the render may still be running on the GPU.
"""

import asyncio
import sys
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


from minimax_mcp.comfyui_client import ComfyUIClient, ComfyUITimeout

DEAD_URL = "http://127.0.0.1:9"  # porta fechada: httpx e ws falham de imediato


async def _wait_with_dead_transport(prompt_id: str, timeout: float) -> str:
    """Returns 'timeout' (desired), 'raised:<Type>' or 'none' (no raise)."""
    client = ComfyUIClient(base_url=DEAD_URL)
    try:
        await client.wait_for_execution(prompt_id, timeout=timeout, poll_interval=0.05)
    except ComfyUITimeout:
        return "timeout"
    except BaseException as e:  # o teste É capturar tipos crus quaisquer
        return f"raised:{type(e).__name__}"
    return "none"


print("== unit_client: transport failure during poll ==")
res = asyncio.run(_wait_with_dead_transport("pid-t", timeout=0.4))
if res == "timeout":
    ok("httpx/ws transport failure surfaces as ComfyUITimeout")
else:
    bad(f"expected ComfyUITimeout, got {res!r}")

print("== unit_client: ComfyUITimeout payload mentions the prompt ==")
client = ComfyUIClient(base_url=DEAD_URL)


async def _timeout_message() -> str:
    try:
        await client.wait_for_execution("pid-msg", timeout=0.3, poll_interval=0.05)
    except ComfyUITimeout as e:
        return str(e)
    return ""


msg = asyncio.run(_timeout_message())
if "pid-msg" in msg:
    ok("timeout message carries the prompt_id")
else:
    bad(f"timeout message should mention pid-msg: {msg!r}")

sys.exit(1 if FAIL else 0)
