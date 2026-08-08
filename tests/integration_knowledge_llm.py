#!/usr/bin/env python3
"""Ollama-dependent tests for llm.py. Requires a local Ollama daemon at
OLLAMA_URL with LLM_MODEL and EMBEDDING_MODEL already pulled.

Run: uv run --directory . python tests/integration_knowledge_llm.py
"""
import os
import shutil
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

SAMPLE_TRANSCRIPTION = (
    "Hoje vou mostrar como instalar o Docker no Ubuntu. Primeiro, atualize os "
    "pacotes com apt update. Depois, instale com apt install docker.io. Por fim, "
    "adicione seu usuário ao grupo docker para não precisar de sudo."
)

print("== integration_knowledge_llm: generate_structured ==")
result = llm.generate_structured(SAMPLE_TRANSCRIPTION)
if result.get("ok"):
    ok("generate_structured returned ok=True")
else:
    bad(f"generate_structured failed: {result.get('error')}")

for key in ("resumo", "tutorial", "objetivos", "tags"):
    if result.get(key):
        ok(f"generate_structured result has non-empty '{key}'")
    else:
        bad(f"generate_structured result missing/empty '{key}': {result}")

print("== integration_knowledge_llm: embed ==")
vector = llm.embed("docker install ubuntu")
if isinstance(vector, list) and len(vector) > 0:
    ok(f"embed returned a {len(vector)}-dim vector")
else:
    bad(f"embed returned unexpected value: {vector!r}")

print("== integration_knowledge_llm: chat ==")
answer = llm.chat("Responda em uma frase curta: qual comando instala o Docker no Ubuntu?")
if isinstance(answer, str) and len(answer.strip()) > 0:
    ok(f"chat returned non-empty answer: {answer[:80]!r}...")
else:
    bad(f"chat returned unexpected value: {answer!r}")

print("== integration_knowledge_llm: vision describe (skippable) ==")
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
have = os.popen(f"ollama list 2>/dev/null | awk '{{print $1}}'").read()
if VISION_MODEL.split(":")[0] not in have:
    print("  [SKIP] vision model not pulled; run: ollama pull qwen2.5vl:7b")
else:
    img = Path(tempfile.mkdtemp()) / "pixel.png"
    # 4x4 solid-color PNG (a real file the vision model can read)
    def _png(path):
        raw = b""
        for y in range(4):
            raw += b"\x00" + b"\x60\x40\xc0" * 4
        def chunk(typ, data):
            c = struct.pack(">I", len(data)) + typ + data
            return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        path.write_bytes(png)

    _png(img)
    res = llm.describe_image(str(img), model=VISION_MODEL)
    if res.get("ok") and res["text"]:
        ok(f"describe_image returned text ({len(res['text'])} chars)")
    else:
        bad(f"describe_image = {res!r}")
    shutil.rmtree(img.parent)

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
