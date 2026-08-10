#!/usr/bin/env python3
"""Pure-logic unit tests for vault.write_markdown_copy — no Postgres, no Ollama.

Run: uv run --directory . python tests/unit_vault.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
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


print("== unit_vault: write_markdown_copy ==")
import tempfile

from minimax_mcp import vault

doc = {
    "id": 118, "title": "JWT no front", "summary": "resumo", "tutorial": "tut",
    "objectives": ["obj1", "obj2"], "tags": ["seguranca", "jwt"],
    "source_url": "https://x", "platform": "instagram", "type": "video",
    "ig_pk": "123", "llm_model": "lfm2:24b",
    "transcription_text": "transcrição",
}
with tempfile.TemporaryDirectory() as tmp:
    res = vault.write_markdown_copy(doc, tmp)
    out = Path(res["path"])
    text = out.read_text(encoding="utf-8")
    if res.get("ok") and not res.get("skipped") and out.exists():
        ok("write_markdown_copy writes the file")
    else:
        bad(f"write_markdown_copy = {res}")
    if "## Objetivos" in text and "obj1" in text:
        ok("export includes the Objectives section")
    else:
        bad("missing ## Objetivos section")
    if "## Prompt de geração de vídeo" in text:
        ok("export includes the video-generation prompt placeholder")
    else:
        bad("missing video-generation prompt placeholder section")
    if "ig_pk: 123" in text and "llm_model: lfm2:24b" in text:
        ok("frontmatter includes ig_pk and llm_model")
    else:
        bad("frontmatter missing ig_pk/llm_model")

# Missing keys still render (backward compatible) and never raise.
with tempfile.TemporaryDirectory() as tmp:
    res = vault.write_markdown_copy({"id": 1, "title": "só titulo"}, tmp)
    if res.get("ok"):
        ok("write_markdown_copy tolerates a sparse document dict")
    else:
        bad(f"sparse dict failed: {res}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
