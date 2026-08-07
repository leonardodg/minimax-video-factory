#!/usr/bin/env python3
"""Pure-logic unit tests for the knowledge base modules — no Postgres, no Ollama.

Run: uv run --directory . python tests/unit_knowledge.py
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


print("== unit_knowledge: db.chunk_text ==")
from minimax_mcp import db

if db.chunk_text("") != []:
    bad("chunk_text('') should return []")
else:
    ok("chunk_text('') == []")

short = "hello world"
if db.chunk_text(short, max_chars=1000) == [short]:
    ok("chunk_text(short text) returns single chunk unchanged")
else:
    bad(f"chunk_text(short) = {db.chunk_text(short, max_chars=1000)!r}")

long_text = "a" * 2500
chunks = db.chunk_text(long_text, max_chars=1000, overlap=100)
if len(chunks) == 3 and all(len(c) <= 1000 for c in chunks):
    ok(f"chunk_text(2500 chars, max=1000) -> {len(chunks)} chunks, all <= 1000 chars")
else:
    bad(f"chunk_text(2500 chars) -> {[len(c) for c in chunks]}")

reconstructed_overlap_ok = chunks[0][-100:] == chunks[1][:100]
if reconstructed_overlap_ok:
    ok("consecutive chunks overlap by `overlap` chars")
else:
    bad("chunk overlap does not match the requested overlap size")

print("== unit_knowledge: llm.build_summary_prompt / parse_llm_json ==")
from minimax_mcp import llm

prompt = llm.build_summary_prompt("conteudo de teste")
if "conteudo de teste" in prompt and "resumo" in prompt.lower() and "tutorial" in prompt.lower():
    ok("build_summary_prompt embeds the transcription and asks for resumo+tutorial")
else:
    bad(f"build_summary_prompt missing expected content: {prompt[:200]!r}")

clean_json = '{"resumo": "r", "tutorial": "t", "objetivos": ["a"], "tags": ["x"]}'
parsed = llm.parse_llm_json(clean_json)
if parsed == {"resumo": "r", "tutorial": "t", "objetivos": ["a"], "tags": ["x"]}:
    ok("parse_llm_json parses a clean JSON string")
else:
    bad(f"parse_llm_json(clean) = {parsed!r}")

fenced_json = "```json\n" + clean_json + "\n```"
parsed_fenced = llm.parse_llm_json(fenced_json)
if parsed_fenced == parsed:
    ok("parse_llm_json strips ```json fences")
else:
    bad(f"parse_llm_json(fenced) = {parsed_fenced!r}")

print("== unit_knowledge: vault.write_markdown_copy ==")
import tempfile

from minimax_mcp import vault

skip_result = vault.write_markdown_copy({"title": "x"}, None)
if skip_result == {"ok": True, "skipped": True, "reason": "VAULT_PATH not configured"}:
    ok("write_markdown_copy skips cleanly when vault_path is None")
else:
    bad(f"write_markdown_copy(None) = {skip_result!r}")

with tempfile.TemporaryDirectory() as tmp:
    doc = {
        "id": 1, "title": "Como instalar Docker", "type": "video", "platform": "instagram",
        "source_url": "https://instagram.com/p/xyz", "summary": "Resumo de teste.",
        "tutorial": "## Passo 1\nFaça isso.", "transcription_text": "texto completo",
        "tags": ["docker", "linux"],
    }
    result = vault.write_markdown_copy(doc, tmp)
    if result.get("ok") and not result.get("skipped") and Path(result["path"]).exists():
        ok(f"write_markdown_copy wrote a file: {result['path']}")
    else:
        bad(f"write_markdown_copy did not write a file: {result!r}")

    content = Path(result["path"]).read_text(encoding="utf-8") if result.get("path") else ""
    if "## Resumo" in content and "## Tutorial" in content and "docker" in content.lower():
        ok("written markdown contains Resumo/Tutorial sections and tags")
    else:
        bad(f"written markdown missing expected sections: {content[:200]!r}")

bad_path_result = vault.write_markdown_copy({"title": "x"}, "/root/no-permission-should-not-raise")
if bad_path_result.get("ok") and bad_path_result.get("skipped"):
    ok("write_markdown_copy fails soft (ok=True, skipped=True) on an unwritable path")
else:
    bad(f"write_markdown_copy raised or returned ok=False on bad path: {bad_path_result!r}")

print("== unit_knowledge: knowledge._parse_frontmatter / _extract_section ==")
from minimax_mcp import knowledge

md_with_fm = """---
title: Git
tags:
  - git
  - versionamento
url: https://example.com/git
---

# Git

Conteúdo do tutorial.
"""
meta, body = knowledge._parse_frontmatter(md_with_fm)
if meta.get("title") == "Git" and meta.get("url") == "https://example.com/git":
    ok("_parse_frontmatter extracts title/url/tags from YAML frontmatter")
else:
    bad(f"_parse_frontmatter(meta) = {meta!r}")

if body.startswith("# Git") and "Conteúdo" in body:
    ok("_parse_frontmatter returns the body after the closing ---")
else:
    bad(f"_parse_frontmatter(body) = {body[:60]!r}")

no_fm = "# Só título\n\nsem frontmatter"
meta2, body2 = knowledge._parse_frontmatter(no_fm)
if meta2 == {} and body2 == no_fm:
    ok("_parse_frontmatter leaves files without frontmatter untouched")
else:
    bad(f"_parse_frontmatter(no frontmatter) = {meta2!r}, {body2[:40]!r}")

broken_fm = "---\nnot: valid: yaml: [[[\n---\n# corpo\n"
meta3, body3 = knowledge._parse_frontmatter(broken_fm)
if meta3 == {} and "# corpo" in body3:
    ok("_parse_frontmatter tolerates broken YAML (returns empty meta)")
else:
    bad(f"_parse_frontmatter(broken yaml) = {meta3!r}")

with_summary = """# Docker

## Summary
Instala o Docker no Ubuntu em três passos.

## Passos
1. apt update
2. apt install docker.io
"""
summary = knowledge._extract_section(with_summary, "Summary")
if summary and summary.startswith("Instala o Docker") and "apt install" not in summary:
    ok("_extract_section grabs text under ## Summary until the next heading")
else:
    bad(f"_extract_section(summary) = {summary!r}")

if knowledge._extract_section("# sem seção de summary\napenas texto", "Summary") is None:
    ok("_extract_section returns None when the heading is absent")
else:
    bad("_extract_section should return None when no ## Summary heading")

print("== unit_knowledge: llm system messages ==")
from minimax_mcp import llm

ingest_sys = llm._system_message(force_json=True)
answer_sys = llm._system_message(force_json=False)

if "JSON" in ingest_sys:
    ok("ingest system message demands JSON")
else:
    bad(f"ingest system message does not mention JSON: {ingest_sys[:80]!r}")

# The bug this guards: `ask` shares _ollama_generate with the ingest path, and
# the single system message ordered "responda estritamente no formato JSON".
# RAG answers came back as ```json {"resposta": "..."} instead of prose.
if "JSON" not in answer_sys:
    ok("answer system message does NOT demand JSON")
else:
    bad(f"answer system message still demands JSON: {answer_sys[:120]!r}")

# Both paths carry the injection guard: ingested transcriptions and retrieved
# context are both untrusted text from the internet.
for label, msg in (("ingest", ingest_sys), ("answer", answer_sys)):
    if "ignore qualquer" in msg.lower():
        ok(f"{label} system message keeps the prompt-injection guard")
    else:
        bad(f"{label} system message lost the injection guard: {msg[:90]!r}")

if "fonte" in answer_sys.lower():
    ok("answer system message asks for sources")
else:
    bad(f"answer system message does not mention sources: {answer_sys[:90]!r}")

# Both providers must send a system message. The OpenAI-compatible path used to
# send none at all, so switching provider silently dropped the guard.
for force_json in (True, False):
    ollama_msgs = llm._build_messages("texto do usuário", force_json=force_json)
    roles = [m["role"] for m in ollama_msgs]
    if roles == ["system", "user"]:
        ok(f"_build_messages(force_json={force_json}) yields system + user")
    else:
        bad(f"_build_messages(force_json={force_json}) roles = {roles}")
    if ollama_msgs[-1]["content"] == "texto do usuário":
        ok(f"_build_messages(force_json={force_json}) keeps the prompt verbatim")
    else:
        bad(f"prompt was altered: {ollama_msgs[-1]['content']!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
