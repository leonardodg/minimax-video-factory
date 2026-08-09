#!/usr/bin/env python3
"""Pure-logic unit tests for the knowledge base modules — no Postgres, no Ollama.

Run: uv run --directory . python tests/unit_knowledge.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import os
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

print("== unit_knowledge: ingest_markdown reports failure ==")
# These exercise the aggregation logic, not connectivity, so the availability
# guard has to see a configured database or it short-circuits first.
os.environ.setdefault("KB_DATABASE_URL", "postgresql+psycopg://t:t@127.0.0.1:1/t")
import tempfile
from unittest import mock

_md_dir = tempfile.mkdtemp()
for _n in ("a.md", "b.md"):
    Path(_md_dir, _n).write_text("---\ntitle: t\n---\n\n## Summary\nx\n", encoding="utf-8")

# Every file fails: the caller must not be told this succeeded. It used to
# return ok=True with imported=0, which reads as success and hides a database
# that is simply unreachable.
with mock.patch.object(knowledge, "_ingest_markdown_file",
                       return_value={"ok": False, "stage": "db", "error": "boom"}):
    r = knowledge.ingest_markdown(_md_dir)
if r.get("ok") is False:
    ok("all files failing yields ok=False, not a silent success")
else:
    bad(f"ingest_markdown returned ok={r.get('ok')} with imported={r.get('imported')}")
if r.get("failed") == 2:
    ok("the failure count is reported")
else:
    bad(f"failed = {r.get('failed')!r}")
if "boom" in str(r.get("error", "")):
    ok("the underlying error reaches the caller")
else:
    bad(f"error = {r.get('error')!r}")

# A partial import is still a success, but must say how many fell over.
_calls = {"n": 0}
def _half(f, **kw):
    _calls["n"] += 1
    return ({"ok": True, "document_id": 1} if _calls["n"] == 1
            else {"ok": False, "stage": "db", "error": "boom"})
with mock.patch.object(knowledge, "_ingest_markdown_file", _half):
    r = knowledge.ingest_markdown(_md_dir)
if r.get("ok") and r.get("imported") == 1 and r.get("failed") == 1:
    ok("a partial import is ok=True with the failures counted")
else:
    bad(f"partial: ok={r.get('ok')} imported={r.get('imported')} failed={r.get('failed')}")

print("== unit_knowledge: kb tools say why they cannot run ==")
_saved = os.environ.pop("KB_DATABASE_URL", None)
try:
    for _name, _call in (
        ("ingest_text", lambda: knowledge.ingest_text("algum texto")),
        ("ingest_markdown", lambda: knowledge.ingest_markdown("/tmp")),
        ("search", lambda: knowledge.search("consulta")),
        ("ask", lambda: knowledge.ask("pergunta")),
        ("reindex", lambda: knowledge.reindex()),
    ):
        _r = _call()
        # Silence here is what hid a broken container for a whole session: the
        # tools were listed, accepted calls, and returned nothing that said why.
        if _r.get("ok") is False and "KB_DATABASE_URL" in str(_r.get("error", "")):
            ok(f"{_name} explains the missing database instead of failing quietly")
        else:
            bad(f"{_name} returned {str(_r)[:110]}")
finally:
    if _saved is not None:
        os.environ["KB_DATABASE_URL"] = _saved

print("== unit_knowledge: VRAM contention is survivable ==")
from unittest import mock as _m2

from minimax_mcp import llm as _llm2
from minimax_mcp import transcriber as _tr

# Whisper on a busy card raised RuntimeError("CUDA failed with error out of
# memory") and gave up. The GPU being occupied is not a reason to refuse to
# transcribe -- the CPU can do it, slower.
_attempts = []
class _FakeWhisper:
    def __init__(self, size, **kw):
        _attempts.append(kw.get("device"))
        if kw.get("device") == "cuda":
            raise RuntimeError("CUDA failed with error out of memory")
    def transcribe(self, *a, **kw):
        class _S:
            start, end, text = 0.0, 1.0, "ok"
        return [_S()], type("I", (), {"language": "pt", "language_probability": 1.0})()

with _m2.patch.object(_tr, "WhisperModel", _FakeWhisper):
    _t = _tr.AudioTranscriber(model_size="tiny", device="cuda")
    _t._model_cache.clear()
    _model = _t._get_model()

if _attempts == ["cuda", "cpu"]:
    ok("a CUDA OOM falls back to the CPU instead of failing")
else:
    bad(f"devices tried: {_attempts}")

# Ollama held 10 GB after every knowledge-base call, which is what starved
# Whisper and the sampler in the first place.
_payload = _llm2._ollama_payload("prompt", "modelo", force_json=False)
if "keep_alive" in _payload:
    ok("ollama calls carry keep_alive so the model is released")
else:
    bad(f"payload keys: {sorted(_payload)}")

print("== unit_knowledge: llm.build_vision_prompt ==")
prompt = llm.build_vision_prompt()
if "portugu" in prompt and "imagem" in prompt:
    ok("build_vision_prompt asks for a PT-BR image description")
else:
    bad(f"build_vision_prompt = {prompt[:120]!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
