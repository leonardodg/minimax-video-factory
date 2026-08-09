#!/usr/bin/env python3
"""Ollama vision integration: describe a tiny image (skips if model not pulled).

Requires: Ollama up. Run: uv run --project . python tests/integration_ig_llm.py
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import llm


def _png_bytes() -> bytes:
    raw = b""
    for _ in range(4):
        raw += b"\x00" + b"\x60\x40\xc0" * 4

    def chunk(typ: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


print("== integration_ig_llm: vision describe ==")
model = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
listed = os.popen("ollama list 2>/dev/null").read()
if "qwen2.5vl" not in listed:
    print("  [SKIP] qwen2.5vl not pulled; run: ollama pull qwen2.5vl:7b")
    print("PASS")
    sys.exit(0)

tmp = Path(tempfile.mkdtemp())
try:
    img = tmp / "pixel.png"
    img.write_bytes(_png_bytes())
    res = llm.describe_image(str(img), model=model)
    if res.get("ok") and res.get("text"):
        ok(f"describe_image returned text ({len(res['text'])} chars)")
    else:
        bad(f"describe_image = {res!r}")
finally:
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
