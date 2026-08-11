# CTA Cleanup + Markdown Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Instagram call-to-action phrases ("segue pra não perder", "salva esse vídeo", "link na bio", "comenta X que eu te mando") from the knowledge-base pipeline — both in the LLM-generated fields and in the raw stored transcription — and add two MCP tools to search and export documents as readable `.md` files.

**Architecture:** Two layers. (1) A pure `strip_cta()` regex helper in `ig_worker.py` cleans the transcription before `ingest_text`; the `SUMMARY_PROMPT_TEMPLATE` in `llm.py` instructs the LLM to omit CTA from generated fields. A one-off `scripts/backfill_cta.py` reapplies this to the 12 already-ingested docs with a disk snapshot for rollback. (2) Two new domain functions in `knowledge.py` (`export_search`, `export_documents`) wired as MCP tools `kb-export-search` and `kb-export`, reusing the existing `vault.write_markdown_copy` markdown renderer.

**Tech Stack:** Python 3.14 (uv), FastMCP, SQLAlchemy/Postgres (kb), Ollama (LLM), regex. Worktree: `.worktrees/cta-export` on branch `feat/cta-export-markdown`.

## Global Constraints

- Worktree `.worktrees/cta-export` (branch `feat/cta-export-markdown`) — all work happens there; never touch `.worktrees/igsync` or `.claude/worktrees/last-frame`.
- No `git push` (CI on self-hosted runner steals GPU). Commits are local only unless the user authorizes a push.
- Adding an MCP tool touches **nine** places (extending.md table) — six are test-enforced; `unit_registry.py` and `unit_commands.py` go red if any is missed.
- Tool count goes 24 → 26. `unit_commands.py` asserts `len(SPECS) == 24` → must become 26.
- New tools follow the thin-wrapper pattern: domain function in `knowledge.py`, `@mcp.tool()` in `server.py` with `Field(description=...)` per param, lazy import, plain dict with `ok` returned.
- `vault.write_markdown_copy()` never raises and never returns `ok=False`.
- Tests follow the repo pattern: `tests/unit_*.py` scripts with `ok()`/`bad()` + exit code, wrapped by `tests/test_scripts.py` pytest entrypoints. `pytest -m unit` must pass.
- `ruff check src tests` must pass (HANDOFF notes it was zeroed on `main`).
- `output/` is gitignored — exported `.md` files live under `output/kb-export/` and snapshots under `output/kb-backup/` without being committed.
- Do not regenerate LLM fields for the 12 existing docs inside unit tests (costs GPU, slow). Backfill runs manually.

---

### Task 1: `strip_cta()` pure helper in `ig_worker.py`

**Files:**
- Modify: `src/minimax_mcp/ig_worker.py` (add `strip_cta`, a `_CTA_SENTENCE_RE`, and a `_CTA_PATTERNS` list near the top, after imports)
- Test: `tests/unit_ig_worker.py` (append a section before the final `if FAIL:` block)

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `strip_cta(text: str) -> str` — removes sentences containing Instagram CTA phrases; input without CTA returns intact; never raises. Task 3 wires it into `process_message`; Task 6 (backfill script) imports it.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_ig_worker.py` before the `print()` / `if FAIL:` ending:

```python
print("== unit_ig_worker: strip_cta ==")
from minimax_mcp.ig_worker import strip_cta

# A sentence containing a CTA is removed entirely.
cleaned = strip_cta(
    "Misture a batata doce amassada com o azeite. "
    "Já me segue aqui para não perder uma receita. "
    "Asse na Air Fryer a 170°C por 15 minutos."
)
if "Já me segue aqui" not in cleaned and "Asse na Air Fryer" in cleaned and "Misture a batata" in cleaned:
    ok("strip_cta removes the CTA sentence, keeps surrounding content")
else:
    bad(f"strip_cta = {cleaned!r}")

# No CTA -> text unchanged.
plain = "Asse na Air Fryer a 170°C por 15 minutos e sirva."
if strip_cta(plain) == plain:
    ok("strip_cta leaves CTA-free text intact")
else:
    bad(f"strip_cta(plain) = {strip_cta(plain)!r}")

# Empty / whitespace input never raises.
try:
    if strip_cta("") == "" and strip_cta("   ").strip() == "":
        ok("strip_cta handles empty/whitespace input")
    else:
        bad("strip_cta empty input result wrong")
except Exception as e:
    bad(f"strip_cta('') raised {e!r}")

# 'link na bio' as its own sentence.
if "link na bio" not in strip_cta("Curte e compartilha. Link na bio. O conteúdo principal.").lower():
    ok("strip_cta removes 'link na bio' sentence")
else:
    bad("strip_cta did not remove 'link na bio'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m unit -q -k ig_worker` (from `.worktrees/cta-export`)
Expected: FAIL — `AttributeError: module 'minimax_mcp.ig_worker' has no attribute 'strip_cta'` (the `bad()` paths print and exit 1).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/ig_worker.py`, after the imports, add:

```python
_CTA_PATTERNS = (
    r"segue(?:-me| me)?(?: aqui)? para(?: não| nao)? perder",
    r"já|ja me segue",
    r"siga para mais",
    r"salva(?: esse| este| o) vídeo|video",
    r"salv(e|a) para fazer depois",
    r"compartilh(a|e) com (?:seus|teus|os) amigos",
    r"link na bio",
    r"curte e compartilha",
    r"ativa o sininho",
    r"coment(?:a|e).*que eu te mando",
    r"já me segue aqui",
)
_CTA_SENTENCE_RE = re.compile(
    r"[^.!?]*(?:" + "|".join(_CTA_PATTERNS) + r")[^.!?]*[.!?]",
    re.IGNORECASE | re.DOTALL,
)


def strip_cta(text: str) -> str:
    """Remove sentences containing Instagram call-to-action phrases.

    A sentence is delimited by `.`, `!` or `?`. Only the sentence that contains
    the CTA is removed; surrounding content is preserved. Never raises and
    returns input unchanged when no CTA pattern matches.
    """
    if not text:
        return text
    return _CTA_SENTENCE_RE.sub("", text).strip()
```

Ensure `re` is imported at the top of `ig_worker.py` (add `import re` if absent).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m unit -q -k ig_worker`
Expected: PASS (existing ig_worker tests + new strip_cta cases).

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/ig_worker.py tests/unit_ig_worker.py
git commit -m "feat: strip_cta() removes Instagram CTA sentences from transcription"
```

---

### Task 2: Instruct the LLM to omit CTA from generated fields

**Files:**
- Modify: `src/minimax_mcp/llm.py` (`SUMMARY_PROMPT_TEMPLATE`)
- Test: `tests/unit_knowledge.py` (append a check on the built prompt)

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_summary_prompt()` output now contains the CTA-omission instruction (same signature — no caller change).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_knowledge.py` before the final exit block:

```python
print("== unit_knowledge: CTA omission instruction in summary prompt ==")
if "call-to-action" in llm.SUMMARY_PROMPT_TEMPLATE or "CTA" in llm.SUMMARY_PROMPT_TEMPLATE:
    ok("summary prompt instructs the LLM to omit call-to-action phrases")
else:
    bad("summary prompt has no CTA omission instruction")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m unit -q -k knowledge`
Expected: FAIL — "summary prompt has no CTA omission instruction".

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/llm.py`, inside `SUMMARY_PROMPT_TEMPLATE`, after the existing "IMPORTANTE" instruction line, add:

```
Não inclua no resumo, tutorial, objetivos ou tags frases de call-to-action \
(CTA) — pedidos para seguir, curtir, compartilhar, salvar o vídeo, comentar \
para receber algo, "link na bio", ativar sininho, etc. Documente apenas o \
conteúdo ensinado/demonstrado, ignorando esses apelos.
```

The template already has an "IMPORTANTE" paragraph; add this as a separate paragraph in the same template string. Preserve the existing JSON format block and the `{image_note}` / `{transcription}` placeholders.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m unit -q -k knowledge`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/llm.py tests/unit_knowledge.py
git commit -m "feat: summary prompt omits call-to-action phrases from generated fields"
```

---

### Task 3: Wire `strip_cta` into `process_message`

**Files:**
- Modify: `src/minimax_mcp/ig_worker.py` (`process_message`)
- Test: `tests/unit_ig_worker.py` (extend the video ingest check)

**Interfaces:**
- Consumes: `strip_cta(text)` from Task 1.
- Produces: `process_message()` now passes `strip_cta(text)` to `ingest` for both video and image paths — callers (the daemon `run()`, tests) unchanged.

- [ ] **Step 1: Write the failing test**

In `tests/unit_ig_worker.py`, the existing video test uses `tr()` returning `"transcrito"`. Add a new block that feeds CTA-laden text and asserts the ingested text is cleaned. Append before the final exit block:

```python
print("== unit_ig_worker: process_message strips CTA before ingest ==")
def dl_vid(msg):
    return {"ok": True, "filepath": "/tmp/y.mp4"}

def tr_cta(path):
    return {"ok": True, "text": "A dica é boa. Segue pra não perder. Asse por 15 min.", "language": "pt"}

def ingest_seen(text, **kw):
    seen_text = text
    return {"ok": True, "document_id": 44}

seen_text = {}
def ingest_record(text, **kw):
    seen_text["text"] = text
    return {"ok": True, "document_id": 45}

ig_worker.process_message(
    MESSAGE, download=dl_vid, transcribe=tr_cta, describe=None, ingest=ingest_record
)
if "Segue pra não perder" not in seen_text.get("text", "") and "A dica é boa" in seen_text.get("text", ""):
    ok("process_message passes CTA-stripped text to ingest")
else:
    bad(f"ingest received uncleaned text: {seen_text.get('text')!r}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m unit -q -k ig_worker`
Expected: FAIL — ingest received uncleaned text (`"A dica é boa. Segue pra não perder. Asse por 15 min."`).

- [ ] **Step 3: Write minimal implementation**

In `process_message()`, immediately before the `ing = ingest(...)` call, apply `strip_cta` to `text`:

```python
    text = strip_cta(text)
```

This single line covers both branches (video `text` from `tr["text"]`, image `text` from the `"\n\n".join(...)`), because both are reduced to the local `text` variable before the ingest block.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m unit -q -k ig_worker`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/ig_worker.py tests/unit_ig_worker.py
git commit -m "feat: ig-worker strips CTA sentences before ingesting posts"
```

---

### Task 4: Extend `vault.write_markdown_copy` with objectives + video-prompt section

**Files:**
- Modify: `src/minimax_mcp/vault.py` (`write_markdown_copy`)
- Test: `tests/unit_knowledge.py` (or a new `tests/unit_vault.py`) — pure, writes to a temp dir

**Interfaces:**
- Consumes: nothing (existing dict contract).
- Produces: `write_markdown_copy(document, vault_path)` — same signature; `.md` now includes `## Objetivos` and `## Prompt de geração de vídeo` (empty placeholder) sections when the dict has `objectives`; frontmatter gains `ig_pk`, `llm_model` when present. Backward compatible (absent keys render empty).

- [ ] **Step 1: Write the failing test**

Create `tests/unit_vault.py` following the ok/bad pattern (copy the header style of `tests/unit_knowledge.py`), then append to `tests/test_scripts.py` an entrypoint:

```python
# --- in tests/test_scripts.py, with the other unit tests ---
@pytest.mark.unit
def test_unit_vault():
    result = _run_script("unit_vault.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

And in `tests/unit_vault.py`:

```python
print("== unit_vault: write_markdown_copy ==")
import tempfile
from pathlib import Path
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m unit -q -k vault`
Expected: FAIL — missing sections / frontmatter keys.

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/vault.py`, rewrite `write_markdown_copy` to build the frontmatter and body from the dict with safe `.get()` for every key:

```python
def write_markdown_copy(document: dict[str, Any], vault_path: str | Path | None) -> dict[str, Any]:
    if not vault_path:
        return {"ok": True, "skipped": True, "reason": "VAULT_PATH not configured"}
    try:
        folder = Path(vault_path) / "Knowledge"
        folder.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = _slugify(document.get("title") or f"documento-{document.get('id')}")
        filepath = folder / f"{date_str}-{slug}.md"

        tags = document.get("tags") or []
        tags_line = " ".join(f"#{t}" for t in tags)

        objectives = document.get("objectives") or []
        if isinstance(objectives, (list, tuple)):
            objectives_md = "\n".join(f"- {o}" for o in objectives)
        else:
            objectives_md = str(objectives or "")

        content = (
            "---\n"
            f"source_url: {document.get('source_url') or ''}\n"
            f"platform: {document.get('platform') or ''}\n"
            f"type: {document.get('type') or ''}\n"
            f"ig_pk: {document.get('ig_pk') or ''}\n"
            f"llm_model: {document.get('llm_model') or ''}\n"
            f"created_at: {date_str}\n"
            "---\n\n"
            f"# {document.get('title') or slug}\n\n"
            f"{tags_line}\n\n"
            f"## Resumo\n\n{document.get('summary') or ''}\n\n"
            f"## Tutorial\n\n{document.get('tutorial') or ''}\n\n"
            f"## Objetivos\n\n{objectives_md}\n\n"
            f"## Transcrição completa\n\n{document.get('transcription_text') or ''}\n\n"
            "## Prompt de geração de vídeo\n\n(gerado quando o schema de prompts existir)\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return {"ok": True, "skipped": False, "path": str(filepath)}
    except Exception as e:
        logger.warning("Vault markdown copy failed (non-blocking): %s", e)
        return {"ok": True, "skipped": True, "reason": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m unit -q -k vault`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/vault.py tests/unit_vault.py tests/test_scripts.py
git commit -m "feat: markdown export adds objectives + video-prompt placeholder sections"
```

---

### Task 5: `export_search` and `export_documents` in `knowledge.py`

**Files:**
- Modify: `src/minimax_mcp/knowledge.py` (add two functions)
- Test: `tests/unit_knowledge.py` (pure — these functions touch DB/Ollama; unit test only asserts they exist and guard against unavailable KB). Integration coverage lives in Task 7.

**Interfaces:**
- Consumes: `db.get_session`, `db.Document` model, `vault.write_markdown_copy`.
- Produces:
  - `export_search(query: str | None = None, ids: list[int] | None = None, limit: int = 20) -> dict` → `{"ok": True, "total": N, "documents": [{id, type, title, tags, ig_pk, summary_len, tutorial_len, transcription_len, created_at}]}` (or `{"ok": False, "error": ...}` when KB unavailable).
  - `export_documents(ids: list[int], output_dir: str = "output/kb-export/") -> dict` → `{"ok": True, "output_dir": "...", "files": [{id, ok, path | error}]}`.
  - `_document_to_dict(doc) -> dict` — helper mapping a `Document` row to the vault dict keys (id, title, summary, tutorial, objectives, tags, source_url, platform, type, transcription_text, ig_pk, llm_model).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_knowledge.py` before the final exit block:

```python
print("== unit_knowledge: export functions ==")
from minimax_mcp import knowledge as _k

for fname in ("export_search", "export_documents", "_document_to_dict"):
    if callable(getattr(_k, fname, None)):
        ok(f"knowledge.{fname} exists")
    else:
        bad(f"knowledge.{fname} missing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m unit -q -k knowledge`
Expected: FAIL — `knowledge.export_search missing` etc.

- [ ] **Step 3: Write minimal implementation**

Append to `src/minimax_mcp/knowledge.py`:

```python
def _document_to_dict(doc: Any) -> dict[str, Any]:
    """Map a Document ORM row to the dict shape vault.write_markdown_copy expects."""
    return {
        "id": doc.id,
        "title": doc.title,
        "summary": doc.summary,
        "tutorial": doc.tutorial,
        "objectives": doc.objectives,
        "tags": doc.tags or [],
        "source_url": doc.source_url,
        "platform": doc.platform,
        "type": doc.type,
        "transcription_text": doc.transcription_text,
        "ig_pk": doc.ig_pk,
        "llm_model": doc.llm_model,
    }


def export_search(
    query: str | None = None,
    ids: list[int] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List documents for export — by ids, or by keyword query, or latest first.

    Never writes anything. Returns the table the user validates before
    calling export_documents.
    """
    if (unavailable := _kb_unavailable()):
        return unavailable
    session = db.get_session()
    try:
        stmt = select(db.Document)
        if ids:
            stmt = stmt.where(db.Document.id.in_(ids))
        elif query and query.strip():
            ranked = db.search_documents(
                session, query, embed_fn=llm.embed, top_k=limit
            )
            hit_ids = [r["document_id"] for r in ranked]
            if not hit_ids:
                return {"ok": True, "total": 0, "documents": []}
            stmt = (
                select(db.Document)
                .where(db.Document.id.in_(hit_ids))
                .order_by(db.Document.id.desc())
            )
        else:
            stmt = stmt.order_by(db.Document.id.desc())
        stmt = stmt.limit(limit)
        docs = session.execute(stmt).scalars().all()
        documents = [
            {
                "id": d.id, "type": d.type, "title": d.title, "tags": d.tags,
                "ig_pk": d.ig_pk,
                "summary_len": len(d.summary or ""),
                "tutorial_len": len(d.tutorial or ""),
                "transcription_len": len(d.transcription_text or ""),
                "created_at": str(d.created_at),
            }
            for d in docs
        ]
    finally:
        session.close()
    return {"ok": True, "total": len(documents), "documents": documents}


def export_documents(
    ids: list[int],
    output_dir: str = "output/kb-export/",
) -> dict[str, Any]:
    """Write the selected documents as readable .md files.

    Uses vault.write_markdown_copy (which appends /Knowledge to the path and
    never raises). Missing ids are reported per-file without aborting the rest.
    """
    if (unavailable := _kb_unavailable()):
        return unavailable
    if not ids:
        return {"ok": False, "error": "ids required"}
    session = db.get_session()
    try:
        rows = session.execute(
            select(db.Document).where(db.Document.id.in_(ids))
        ).scalars().all()
        by_id = {d.id: d for d in rows}
    finally:
        session.close()

    files: list[dict[str, Any]] = []
    for doc_id in ids:
        doc = by_id.get(doc_id)
        if doc is None:
            files.append({"id": doc_id, "ok": False, "error": "not found"})
            continue
        result = vault.write_markdown_copy(_document_to_dict(doc), output_dir)
        files.append(
            {"id": doc_id, "ok": result.get("ok", False),
             "skipped": result.get("skipped", False), "path": result.get("path"),
             "error": result.get("reason")}
        )
    return {"ok": True, "output_dir": output_dir, "files": files}
```

Ensure `from sqlalchemy import select` is imported in `knowledge.py` (check the header; add if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m unit -q -k knowledge`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/knowledge.py tests/unit_knowledge.py
git commit -m "feat: knowledge.export_search/export_documents list and write markdown"
```

---

### Task 6: MCP tools `kb_export_search` and `kb_export`

**Files:**
- Modify: `src/minimax_mcp/server.py` (add two `@mcp.tool()` functions)
- Modify: `scripts/command_docs/catalog.py` (two command names)
- Modify: `scripts/command_docs/overrides.py` (optional — add override entries with PT resumo)
- Test: `tests/unit_registry.py` (add to `EXPECTED_TOOLS` and `REQUIRED_DESCRIBED`), `tests/unit_commands.py` (bump 24 → 26)

**Interfaces:**
- Consumes: `knowledge.export_search`, `knowledge.export_documents` (Task 5).
- Produces: MCP tools `kb_export_search(query, ids, limit)` and `kb_export(ids, output_dir)`; slash commands `kb-export-search`, `kb-export`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit_registry.py`, add to `EXPECTED_TOOLS` (after the IG group):

```python
    # markdown export
    "kb_export_search",
    "kb_export",
```

and to `REQUIRED_DESCRIBED`:

```python
    "kb_export": ["ids"],
```

In `tests/unit_commands.py`, change the two `== 24` assertions to `== 26` (the block that prints "found all 24 @mcp.tool() functions" and the later `len(SPECS)` check — search the file for `24`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -m unit -q -k 'registry or commands'`
Expected: FAIL — registry reports kb_export_search missing; commands reports "found 24 tools, expected 26".

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/server.py`, after `knowledge_reindex` (before the IG section), add:

```python
@mcp.tool()
def kb_export_search(
    query: str | None = Field(default=None, description="Texto para buscar em título/resumo/conteúdo (opcional)"),
    ids: list[int] | None = Field(default=None, description="IDs diretos dos documentos (opcional)"),
    limit: int = Field(default=20, description="Número máximo de resultados"),
) -> dict[str, Any]:
    """Lista documentos para export — por IDs, por busca, ou os mais recentes. Nao grava nada."""
    from minimax_mcp import knowledge
    return knowledge.export_search(query=query, ids=ids, limit=limit)


@mcp.tool()
def kb_export(
    ids: list[int] = Field(description="IDs dos documentos a exportar (confirme antes com kb-export-search)"),
    output_dir: str = Field(default="output/kb-export/", description="Diretório de destino dos .md"),
) -> dict[str, Any]:
    """Exporta documentos selecionados como arquivos .md legíveis."""
    from minimax_mcp import knowledge
    return knowledge.export_documents(ids=ids, output_dir=output_dir)
```

In `scripts/command_docs/catalog.py`, add to `COMMAND_NAMES` (KB group):

```python
    "kb_export_search": "kb-export-search",
    "kb_export": "kb-export",
```

In `scripts/command_docs/overrides.py`, add to `OVERRIDES`:

```python
    "kb_export_search": Override(
        resumo=(
            "Lista documentos para exportar — por IDs, por busca ou os mais "
            "recentes. Nao grava nada; use a lista para confirmar e depois "
            "chamar kb-export"
        ),
        param_notas={
            "query": "texto para buscar em título/resumo/conteúdo",
            "ids": "IDs diretos (ex.: 118,121,125)",
        },
    ),
    "kb_export": Override(
        resumo="Exporta os documentos selecionados como .md em output/kb-export/",
        param_notas={
            "ids": "IDs confirmados na busca (kb-export-search)",
            "output_dir": "diretório de destino (default output/kb-export/)",
        },
    ),
```

- [ ] **Step 4: Regenerate command docs and run tests**

Run:
```bash
uv run python scripts/generate_commands.py
uv run python scripts/generate_mcp_docs.py
uv run pytest -m unit -q
```
Expected: PASS — registry 26 tools, commands 26, generated files fresh.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/server.py scripts/command_docs/ tests/ docs/MCP_TOOLS.md .opencode/command/ docs/COMMANDS.md
git commit -m "feat: kb-export-search and kb-export MCP tools (24 -> 26 tools)"
```

---

### Task 7: Integration test for export (Postgres-backed)

**Files:**
- Modify: `tests/integration_knowledge_db.py` (add an export round-trip test, idempotent — cleans up its own docs)
- Test: `tests/test_scripts.py` already covers `integration_knowledge_db` via pytest marker `integration_db`.

**Interfaces:**
- Consumes: `knowledge.export_search`, `knowledge.export_documents`, `knowledge.ingest_text`.
- Produces: proof that a real ingested doc round-trips through export to a `.md` file.

- [ ] **Step 1: Write the test**

Append to `tests/integration_knowledge_db.py` (match its existing structure — create a doc, exercise the function, delete the doc in a finally):

```python
def test_export_roundtrip(cleanup):
    import tempfile
    from minimax_mcp import knowledge

    res = knowledge.ingest_text(
        "Receita: bata 2 ovos com açúcar. Finalize com canela.",
        source_url="https://example.com/export-test",
        title="Export test doc",
        doc_type="text",
        extra_tags=["test"],
    )
    assert res["ok"], res
    doc_id = res["document_id"]

    try:
        listed = knowledge.export_search(ids=[doc_id])
        assert listed["ok"] and listed["total"] == 1, listed
        assert listed["documents"][0]["id"] == doc_id

        with tempfile.TemporaryDirectory() as tmp:
            exported = knowledge.export_documents([doc_id], output_dir=tmp)
            assert exported["ok"] and exported["files"][0]["ok"], exported
            from pathlib import Path
            assert Path(exported["files"][0]["path"]).exists()

        missing = knowledge.export_documents([99999999])
        assert missing["ok"] and missing["files"][0]["ok"] is False
    finally:
        from minimax_mcp import db
        session = db.get_session()
        try:
            db.delete_documents(session, source_url="https://example.com/export-test")
        finally:
            session.close()
```

Follow the existing file's fixture/import style — read `tests/integration_knowledge_db.py` first and mirror its conventions (it may already define `cleanup` or use a different pattern; adapt the test to match).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m integration_db -q -k export`
Expected: FAIL — `AttributeError: module 'minimax_mcp.knowledge' has no attribute 'export_search'` only if run before Task 5; since Task 5 is done, expected outcome here is actually PASS. If already passing, that is fine — the point is the test now exists and passes against the implemented functions.

- [ ] **Step 3: Verify it passes**

Run: `uv run pytest -m integration_db -q -k export`
Expected: PASS (Postgres up; `docker compose $COMPOSE_ARGS up -d postgres` if needed).

- [ ] **Step 4: Commit**

```bash
git add tests/integration_knowledge_db.py
git commit -m "test: export_search/export_documents round-trip against Postgres"
```

---

### Task 8: Backfill script with snapshot/rollback

**Files:**
- Create: `scripts/backfill_cta.py`
- Test: none automated (requires GPU/LLM + live DB; manual run documented). Keep pure helpers testable by inspection.

**Interfaces:**
- Consumes: `minimax_mcp.ig_worker.strip_cta`, `minimax_mcp.llm.generate_structured`, `minimax_mcp.db`, `minimax_mcp.vault`.
- Produces: executable `scripts/backfill_cta.py` with `--dry-run`, `--restore <id>`, and default (regenerate) modes.

- [ ] **Step 1: Write the script**

Create `scripts/backfill_cta.py`:

```python
#!/usr/bin/env python3
"""Backfill: re-apply CTA cleanup to already-ingested Instagram documents.

For each document with an ig_pk, it:
  1. snapshots the current state as .md in output/kb-backup/<id>-<ig_pk>.md
  2. strips CTA from transcription_text
  3. regenerates summary/tutorial/objectives/tags via the LLM (new prompt)
  4. writes the UPDATE, preserving id/ig_pk/source_url/platform/created_at

Modes:
  --dry-run            show what would change, write nothing
  --restore <id>       restore <id> from its snapshot (rollback)

Run from the worktree: uv run --directory . python scripts/backfill_cta.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from minimax_mcp import db, llm, vault  # noqa: E402
from minimax_mcp.ig_worker import strip_cta  # noqa: E402

BACKUP_DIR = Path("output/kb-backup")


def _snapshot_path(doc_id: int, ig_pk: str) -> Path:
    return BACKUP_DIR / f"{doc_id}-{ig_pk}.md"


def snapshot_doc(doc) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    d = {
        "id": doc.id, "title": doc.title, "summary": doc.summary,
        "tutorial": doc.tutorial, "objectives": doc.objectives,
        "tags": doc.tags or [], "source_url": doc.source_url,
        "platform": doc.platform, "type": doc.type,
        "transcription_text": doc.transcription_text,
        "ig_pk": doc.ig_pk, "llm_model": doc.llm_model,
    }
    res = vault.write_markdown_copy(d, str(BACKUP_DIR))
    return Path(res["path"])


def restore_doc(doc_id: int, ig_pk: str) -> dict:
    """Read a snapshot back into a document dict (best-effort parse)."""
    p = _snapshot_path(doc_id, ig_pk)
    if not p.exists():
        return {"ok": False, "error": f"no snapshot at {p}"}
    text = p.read_text(encoding="utf-8")
    return {"ok": True, "path": str(p), "text": text}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", type=int, metavar="ID")
    args = ap.parse_args()

    session = db.get_session()
    try:
        from sqlalchemy import select
        from minimax_mcp.models import Document
        docs = session.execute(
            select(Document).where(Document.ig_pk.isnot(None)).order_by(Document.id)
        ).scalars().all()
    finally:
        session.close()

    if not docs:
        print("no documents with ig_pk found")
        return 0

    if args.restore is not None:
        doc = next((d for d in docs if d.id == args.restore), None)
        if not doc:
            print(f"document {args.restore} not found")
            return 1
        res = restore_doc(doc.id, doc.ig_pk)
        print(res)
        print("restore is best-effort: open the .md and re-ingest its contents if needed")
        return 0

    for doc in docs:
        snap = snapshot_doc(doc)
        cleaned = strip_cta(doc.transcription_text or "")
        changed = cleaned != doc.transcription_text
        print(f"[{doc.id}] snapshot={snap} cta_changed={changed}")
        if args.dry_run:
            print(f"    transcription {len(doc.transcription_text or '')} -> {len(cleaned)} chars")
            continue
        # Regenerate LLM fields with the new prompt (video docs keep type).
        gen = llm.generate_structured(
            cleaned, is_image=(doc.type == "image")
        )
        if not gen.get("ok") and not isinstance(gen, dict):
            print(f"    LLM failed for {doc.id}: {gen}")
            continue
        # generate_structured returns the parsed JSON or raises — inspect llm.py
        # for the actual return shape and adapt (some code paths return the dict
        # directly, others raise). Guard here so a failure does not kill the run.
        try:
            fields = gen if isinstance(gen, dict) and "resumo" in gen else {
                "resumo": "", "tutorial": "", "objetivos": [], "tags": []
            }
            s2 = db.get_session()
            try:
                doc = s2.get(Document, doc.id)
                doc.transcription_text = cleaned
                doc.summary = fields.get("resumo")
                doc.tutorial = fields.get("tutorial")
                doc.objectives = fields.get("objetivos")
                doc.tags = fields.get("tags")
                s2.commit()
            finally:
                s2.close()
            print(f"    updated summary len={len(fields.get('resumo') or '')}")
        except Exception as e:
            print(f"    update failed for {doc.id}: {e!r}")

    print("done. snapshots in", BACKUP_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Note for the implementer:** before running, read `llm.generate_structured()` in `src/minimax_mcp/llm.py` and confirm its exact return shape (dict with `resumo`/`tutorial`/`objetivos`/`tags`, or it may raise). Adapt the `gen` handling accordingly — the code above is a defensive scaffold, not a guarantee of the exact API. Do NOT run the full backfill in CI/tests (costs ~10 min of GPU on the live DB).

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run --directory . python scripts/backfill_cta.py --dry-run`
Expected: prints the 12 docs with `cta_changed=` and `transcription X -> Y chars`, writes snapshots under `output/kb-backup/`, exits 0. If the LLM regeneration path is exercised only in non-dry-run, this verifies the snapshot + strip half.

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_cta.py
git commit -m "feat: backfill script re-applies CTA cleanup to ingested IG docs with snapshot/rollback"
```

---

### Task 9: Documentation + final validation

**Files:**
- Modify: `docs/KNOWLEDGE_BASE.md` (document the two new tools in the tools reference)
- Modify: `README.md` (two rows in the Knowledge base tool table)
- Modify: `AGENTS.md` (note the CTA cleanup + export tools in the pipeline description)
- Modify: `docs/MCP_TOOLS.md` (regenerated by `generate_mcp_docs.py` — Task 6 already ran it; re-run to be safe)

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: fully documented feature; green suite.

- [ ] **Step 1: Update README tool table**

Add two rows to the Knowledge base table in `README.md` (after `knowledge_reindex`):

```markdown
| `kb_export_search` | `/kb-export-search` | List documents for export — by ids, keyword, or latest |
| `kb_export` | `/kb-export` | Write selected documents as readable `.md` files |
```

- [ ] **Step 2: Update KNOWLEDGE_BASE.md**

In the tools reference section (the 18-tool auto-generated reference is `docs/MCP_TOOLS.md`; the hand-written guide is `docs/KNOWLEDGE_BASE.md`), add a short subsection describing the export flow:

- `kb-export-search` lists docs (by ids / query / latest) without writing.
- `kb-export` writes `.md` per selected doc to `output/kb-export/`, format: frontmatter + resumo + tutorial + objetivos + transcrição + placeholder "Prompt de geração de vídeo".
- Mention CTA cleanup: `strip_cta()` + summary prompt now omit Instagram CTAs; backfill script `scripts/backfill_cta.py` re-applies to ingested docs with snapshots in `output/kb-backup/`.

- [ ] **Step 3: Update AGENTS.md**

In the repo layout / tools summary, note the two new tools and the CTA cleanup. Keep it to a few lines (AGENTS.md is the operating manual).

- [ ] **Step 4: Regenerate docs and run the full unit suite + lint**

Run:
```bash
uv run python scripts/generate_commands.py
uv run python scripts/generate_mcp_docs.py
uv run pytest -m unit -q
uv run ruff check src tests
```
Expected: all PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/ AGENTS.md
git commit -m "docs: document kb-export-search/kb-export tools and CTA cleanup"
```

---

## Self-Review Notes (resolved)

- **Spec coverage:** every spec section maps to a task — CTA prompt (T2), strip_cta (T1/T3), backfill + snapshot (T8), export tools (T5/T6), vault format incl. video-prompt placeholder (T4), 9-place registration (T6), tests (T1–T7), docs (T9).
- **Placeholders:** the backfill LLM-return-shape note in Task 8 is an explicit *investigate-then-adapt* instruction, not a "TBD" — the implementer must read `llm.generate_structured()` before running. All other steps carry real code.
- **Type consistency:** `strip_cta(text: str) -> str` consistent across T1/T3/T8. `export_search(query, ids, limit) -> dict` and `export_documents(ids, output_dir) -> dict` consistent across T5/T6/T7. `_document_to_dict` shared by T5 and T8's snapshot logic. Tool names `kb_export_search`/`kb_export` and commands `kb-export-search`/`kb-export` consistent in T6 and T9.
- **Tool count:** 24 → 26 touched in T6 (registry + commands) and implied in T9 README.
