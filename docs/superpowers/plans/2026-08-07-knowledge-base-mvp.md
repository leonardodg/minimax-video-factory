# Local Knowledge Base MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `minimax-video-factory` MCP server with a personal knowledge base — ingest transcriptions (video/audio/text) through a local LLM to produce a structured summary+tutorial, store them in Postgres with embeddings, and expose search/ask tools over MCP.

**Architecture:** Three new modules (`llm.py`, `db.py`, `vault.py`) plus an orchestration module (`knowledge.py`) that wires them together, following the same layering the codebase already uses for `orchestrator.py` (pipeline logic separate from the thin `@mcp.tool()` wrappers in `server.py`). Postgres runs as a new Docker Compose service (independent of the GPU `comfyui` service); the MCP server itself runs in host mode (`uv run`) so it can reach both Postgres (`127.0.0.1`) and the local Ollama daemon directly.

**Tech Stack:** SQLAlchemy 2.x (ORM) + Alembic (migrations) + psycopg3 + pgvector (Postgres extension + Python bindings), httpx (already a dependency) for Ollama/OpenAI-compatible HTTP calls, FastMCP (existing).

## Global Constraints

- Source of truth is Postgres (local, Docker), accessed only through the SQLAlchemy ORM — no raw SQL string-building in application code (migrations may use raw DDL via Alembic).
- Embeddings are always generated locally via Ollama (`mxbai-embed-large`, 1024 dimensions — verified via `curl http://localhost:11434/api/embeddings`), independent of which `LLM_PROVIDER` is used for text generation.
- Text generation LLM is pluggable via `LLM_PROVIDER` env var: `ollama` (default, `qwen2.5:32b-instruct-q4_K_M`, already pulled) or `openai-compatible` (URL + API key, e.g. OpenRouter/Groq free tier).
- The Obsidian markdown copy (`vault.py`) is best-effort only: a failure there must never fail an ingest call. `VAULT_PATH` unset ⇒ skipped entirely (the existing vault at `~/Documents/Obsidian Vault` is suspected unhealthy and is NOT the target by default).
- MCP server runs in host mode (`uv run --project . python src/minimax_mcp/server.py`), not inside the `comfyui` container.
- All new MCP tools return `{"ok": bool, ...}` on both success and failure, matching every existing tool in `server.py` — never raise an uncaught exception across the tool boundary.
- Follow existing test conventions: bash smoke tests live in `tests/0N_*.sh`, source `scripts/config.sh`, echo `[ok]`/`[BAD]`/`[MISS]`, exit non-zero on failure. Pure-Python unit tests follow the `ok()`/`bad()` pattern from `tests/unit_pure.py`. Task 0 additionally wires these scripts into real `pytest` markers (`unit`/`integration_db`/`integration_llm`) for selective/CI-friendly runs — write every new test script in this style AND make sure it's covered by (or added to) `tests/test_scripts.py`.
- MCP tool documentation is generated, not hand-written: after adding/changing a tool in `server.py`, re-run `uv run python scripts/generate_mcp_docs.py` to refresh `docs/MCP_TOOLS.md` — never hand-edit that file.
- Network/GPU-dependent flows (Instagram download) are manually verified only, matching how `download_video`/`transcribe_video`/`studio_pipeline` are already excluded from the automated `diagnose.sh` suite today.

---

## File Structure

| File | Responsibility |
|---|---|
| `docker/docker-compose.yml` (modify) | Add `postgres` service (`pgvector/pgvector:pg16`) |
| `.env.example` (modify) | New `KB_*`, `LLM_*`, `OLLAMA_URL`, `EMBEDDING_*`, `VAULT_PATH` vars |
| `pyproject.toml` (modify) | Add `sqlalchemy`, `psycopg[binary]`, `pgvector`, `alembic` |
| `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial.py` (create) | Schema migrations |
| `src/minimax_mcp/db.py` (create) | SQLAlchemy engine/session, ORM models, `chunk_text`, `save_document`, `search_documents`, `reindex_all` |
| `src/minimax_mcp/llm.py` (create) | Abstract LLM client: `generate_structured`, `embed`, `chat`, plus pure prompt/parsing helpers |
| `src/minimax_mcp/vault.py` (create) | Optional best-effort markdown export |
| `src/minimax_mcp/knowledge.py` (create) | Orchestration: `ingest_text`, `ingest_video`, `ingest_audio`, `search`, `ask`, `reindex` |
| `src/minimax_mcp/server.py` (modify) | 6 new `@mcp.tool()` wrappers |
| `tests/unit_knowledge.py` (create) | Pure-logic tests: chunking, prompt building, JSON parsing, vault markdown |
| `tests/integration_knowledge_db.py` (create) | Postgres-dependent tests (fake embedding function, no Ollama needed) |
| `tests/integration_knowledge_llm.py` (create) | Ollama-dependent tests (`generate_structured`, `embed`, `chat`) |
| `tests/08_knowledge.sh` (create) | End-to-end MCP smoke test: ingest_text → search → ask → reindex |
| `tests/conftest.py` (create) | Auto-skips `integration_db`/`integration_llm` marked tests when Postgres/Ollama aren't reachable |
| `tests/test_scripts.py` (create) | Pytest entrypoints (`-m unit`/`-m integration_db`/`-m integration_llm`) wrapping the ad-hoc scripts above |
| `scripts/generate_mcp_docs.py` (create) | Generates `docs/MCP_TOOLS.md` from the live MCP tool registry (no hand-maintained tool tables to drift) |
| `docs/MCP_TOOLS.md` (create, generated) | Auto-generated MCP tool reference — regenerate, don't hand-edit |

---

### Task 0: Developer tooling — pytest wiring + MCP docs generator

Priority infrastructure requested explicitly: real TDD tooling (selective,
markers-based test running instead of only whole-script pass/fail) and a
documentation generator for the MCP tools so the reference can never drift
from `@mcp.tool()` definitions the way a hand-written table can. Do this
**before** Task 1 — every later task's test script is written assuming these
markers exist, and the docs generator is exercised (and re-run) starting in
Task 12.

**Files:**
- Modify: `pyproject.toml` (pytest config + `pytest-asyncio` is NOT needed —
  the wrapper tests below shell out to the existing scripts as subprocesses,
  so no async test runner is required)
- Create: `tests/conftest.py`
- Create: `tests/test_scripts.py`
- Create: `scripts/generate_mcp_docs.py`

**Interfaces:**
- Consumes: nothing (this task only wraps scripts that already exist:
  `tests/unit_pure.py` today; `tests/unit_knowledge.py`,
  `tests/integration_knowledge_db.py`, `tests/integration_knowledge_llm.py`
  are added by later tasks — `test_scripts.py` references them by filename
  now and they simply don't exist to run yet, which is fine: pytest fails
  those specific tests until the corresponding task lands, exactly like any
  other not-yet-implemented test)
- Produces: `pytest -m unit` (fast, no services needed), `pytest -m
  integration_db` (needs Postgres), `pytest -m integration_llm` (needs
  Ollama), plain `pytest` (runs everything reachable, auto-skips the rest).
  `scripts/generate_mcp_docs.py` produces `docs/MCP_TOOLS.md`, re-run at the
  end of every task that adds/changes a tool (formalized in Task 12).

- [ ] **Step 1: Add pytest config to `pyproject.toml`**

In the `dev` optional-dependencies group, `pytest>=7.0.0` is already present.
Add a new section anywhere after `[project.scripts]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: pure-logic tests, no external services (fast, run always)",
    "integration_db: requires Postgres up + migrated (docker compose up -d postgres && alembic upgrade head)",
    "integration_llm: requires a local Ollama daemon with LLM_MODEL/EMBEDDING_MODEL pulled",
]
```

- [ ] **Step 2: Write the failing test — try running pytest before the wrapper exists**

```bash
cd $PROJECT_ROOT
uv run pytest -m unit -v
```

Expected: `ERROR: file or directory not found` / no tests collected (no
`tests/test_scripts.py` yet).

- [ ] **Step 3: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures: auto-skip integration tests when their service is unreachable."""
from __future__ import annotations

import os
import socket

import pytest


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    postgres_up = _port_open("127.0.0.1", int(os.environ.get("KB_POSTGRES_PORT", "5432")))
    ollama_up = _port_open("127.0.0.1", 11434)

    skip_db = pytest.mark.skip(
        reason="Postgres not reachable on KB_POSTGRES_PORT (docker compose up -d postgres)"
    )
    skip_llm = pytest.mark.skip(reason="Ollama not reachable on :11434")

    for item in items:
        if "integration_db" in item.keywords and not postgres_up:
            item.add_marker(skip_db)
        if "integration_llm" in item.keywords and not ollama_up:
            item.add_marker(skip_llm)
```

- [ ] **Step 4: Write `tests/test_scripts.py`**

```python
"""Pytest entrypoints for the ok()/bad()-style smoke scripts under tests/, so
`pytest -m unit` / `-m integration_db` / `-m integration_llm` work for
selective/CI-friendly runs without rewriting each script's internals."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_script(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tests" / name)],
        cwd=ROOT, capture_output=True, text=True,
    )


@pytest.mark.unit
def test_unit_pure():
    result = _run_script("unit_pure.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_knowledge():
    result = _run_script("unit_knowledge.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_db
def test_integration_knowledge_db():
    result = _run_script("integration_knowledge_db.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_llm
def test_integration_knowledge_llm():
    result = _run_script("integration_knowledge_llm.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 5: Run pytest to confirm current state**

```bash
uv run pytest -m unit -v
```

Expected: `test_unit_pure` PASSES (script already exists);
`test_unit_knowledge` FAILS (`tests/unit_knowledge.py` doesn't exist until
Task 3/6/8) — that's correct or now, both tests are collected and reported
individually instead of one opaque script failure.

```bash
uv run pytest -m integration_db -v
uv run pytest -m integration_llm -v
```

Expected: both report `SKIPPED` if Postgres/Ollama aren't up yet (or `FAILED`
with a clear "script not found" once the services ARE up but the task hasn't
landed) — either way, no crash.

- [ ] **Step 6: Write `scripts/generate_mcp_docs.py`**

```python
#!/usr/bin/env python3
"""Generate docs/MCP_TOOLS.md from the live MCP server's tool registry, so the
tool reference never drifts from the actual @mcp.tool() definitions.

Run: uv run --project . python scripts/generate_mcp_docs.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main() -> None:
    env = dict(os.environ)
    transport = StdioTransport(
        command="uv", args=["run", "--project", str(ROOT), "python", "src/minimax_mcp/server.py"],
        cwd=str(ROOT), env=env,
    )
    async with Client(transport) as client:
        tools = await client.list_tools()

    lines = [
        "<!-- AUTO-GENERATED by scripts/generate_mcp_docs.py — do not edit by hand -->",
        "# MCP Tools Reference",
        "",
        f"{len(tools)} tools exposed by `src/minimax_mcp/server.py`.",
        "",
    ]
    for tool in sorted(tools, key=lambda t: t.name):
        lines.append(f"## `{tool.name}`")
        lines.append("")
        lines.append(tool.description or "_(no description)_")
        lines.append("")
        props = (tool.inputSchema or {}).get("properties", {})
        required = set((tool.inputSchema or {}).get("required", []))
        if props:
            lines.append("| Parameter | Type | Required | Description |")
            lines.append("|---|---|---|---|")
            for name, schema in props.items():
                ptype = schema.get("type", "any")
                desc = schema.get("description", "")
                lines.append(f"| `{name}` | {ptype} | {'yes' if name in required else 'no'} | {desc} |")
            lines.append("")

    out_path = ROOT / "docs" / "MCP_TOOLS.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({len(tools)} tools)")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 7: Run it against the current server (before any knowledge tools exist) and verify**

```bash
cd $PROJECT_ROOT
uv run python scripts/generate_mcp_docs.py
grep -c '^## `' docs/MCP_TOOLS.md
grep -q '## `health_check`' docs/MCP_TOOLS.md && echo "health_check documented: ok"
```

Expected: `grep -c` prints the current tool count (11, matching the tools
listed in `server.py`'s module docstring); `health_check documented: ok`
prints.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_scripts.py scripts/generate_mcp_docs.py docs/MCP_TOOLS.md
git commit -m "feat(dev): add pytest markers for selective test runs + MCP tool docs generator"
```

---

### Task 1: Postgres + pgvector infrastructure

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Test: manual (`docker compose` + `psql`) — infra has no unit test

**Interfaces:**
- Consumes: nothing
- Produces: a reachable Postgres at `KB_POSTGRES_PORT` (default `5432`) on `127.0.0.1`, with the `pgvector` extension installable via `CREATE EXTENSION vector`; env var `KB_DATABASE_URL` that Task 2+ read.

- [ ] **Step 1: Add the `postgres` service to `docker/docker-compose.yml`**

Add a new top-level service, sibling to `comfyui` (independent — no GPU, no dependency on the ComfyUI container):

```yaml
  postgres:
    image: pgvector/pgvector:pg16
    container_name: ${KB_POSTGRES_CONTAINER:-minimax-kb-postgres}
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${KB_POSTGRES_USER:-kb}
      POSTGRES_PASSWORD: ${KB_POSTGRES_PASSWORD:-kb}
      POSTGRES_DB: ${KB_POSTGRES_DB:-knowledge}
    ports:
      - "127.0.0.1:${KB_POSTGRES_PORT:-5432}:5432"
    volumes:
      - ${KB_POSTGRES_DATA_DIR:-${PROJECT_ROOT:-..}/.pgdata}:/var/lib/postgresql/data
```

- [ ] **Step 2: Add knowledge-base vars to `.env.example`**

Append a new section at the end of the file:

```bash
# -----------------------------------------------------------------------------
# KNOWLEDGE BASE (Postgres + pgvector, local LLM, optional Obsidian export)
# -----------------------------------------------------------------------------
KB_POSTGRES_USER=kb
KB_POSTGRES_PASSWORD=kb
KB_POSTGRES_DB=knowledge
KB_POSTGRES_PORT=5432
KB_POSTGRES_CONTAINER=minimax-kb-postgres
KB_POSTGRES_DATA_DIR=/path/to/minimax-video-factory/.pgdata
# SQLAlchemy connection string (psycopg3 driver). Must match the vars above.
KB_DATABASE_URL=postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge

# Text-generation LLM: ollama (default, local/free) or openai-compatible.
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=qwen2.5:32b-instruct-q4_K_M
# Only used when LLM_PROVIDER=openai-compatible (e.g. OpenRouter, Groq free tier).
OPENAI_API_URL=
OPENAI_API_KEY=

# Embeddings are ALWAYS local via Ollama, regardless of LLM_PROVIDER.
EMBEDDING_MODEL=mxbai-embed-large
EMBEDDING_DIM=1024

# Optional: also write a human-readable markdown copy of each ingested item here.
# Leave empty to skip (the default — avoids touching the existing, possibly
# unhealthy, Obsidian vault).
VAULT_PATH=
```

- [ ] **Step 3: Add new dependencies to `pyproject.toml`**

In the `dependencies` list, after `"torch>=2.0.0",` add:

```toml
    "sqlalchemy>=2.0.30",
    "psycopg[binary]>=3.1.18",
    "pgvector>=0.3.2",
    "alembic>=1.13.1",
```

- [ ] **Step 4: Copy `.env.example` to `.env` (if not already present) and fill in `PROJECT_ROOT`-relative values, then bring Postgres up**

```bash
cd $PROJECT_ROOT
grep -q '^KB_DATABASE_URL' .env || cat .env.example | tail -n 20 >> .env
source scripts/config.sh
docker compose $COMPOSE_ARGS up -d postgres
```

- [ ] **Step 5: Verify Postgres is reachable and the pgvector extension is installable**

```bash
docker exec "${KB_POSTGRES_CONTAINER:-minimax-kb-postgres}" pg_isready -U "${KB_POSTGRES_USER:-kb}"
docker exec "${KB_POSTGRES_CONTAINER:-minimax-kb-postgres}" psql -U "${KB_POSTGRES_USER:-kb}" -d "${KB_POSTGRES_DB:-knowledge}" -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname='vector';"
```

Expected: `pg_isready` prints `accepting connections`; the `psql` command prints a row with `vector`.

- [ ] **Step 6: Sync Python deps and commit**

```bash
cd $PROJECT_ROOT
uv sync
git add docker/docker-compose.yml .env.example pyproject.toml uv.lock
git commit -m "feat(kb): add Postgres+pgvector service and knowledge-base dependencies"
```

---

### Task 2: SQLAlchemy models + Alembic migration

**Files:**
- Create: `src/minimax_mcp/db.py` (models + engine only in this task; CRUD/search come in Tasks 3-5)
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial.py`
- Test: manual (`alembic upgrade head` + `psql \dt`) — schema creation has no unit test, it's verified by running it

**Interfaces:**
- Consumes: `KB_DATABASE_URL` env var (Task 1)
- Produces: `db.Base`, `db.Document`, `db.Chunk`, `db.Embedding` ORM classes; `db.get_engine() -> Engine`; `db.get_session() -> Session`. Tasks 3-5 build on these.

- [ ] **Step 1: Write `src/minimax_mcp/db.py` (models + engine/session)**

```python
"""Knowledge base storage: Postgres + pgvector via SQLAlchemy ORM."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))  # mxbai-embed-large


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    transcription_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tutorial: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objectives: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    raw_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    embedding: Mapped[Optional["Embedding"]] = relationship(
        back_populates="chunk", uselist=False, cascade="all, delete-orphan"
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), unique=True
    )
    model: Mapped[str] = mapped_column(String(100))
    vector: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM))

    chunk: Mapped["Chunk"] = relationship(back_populates="embedding")


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ["KB_DATABASE_URL"]
        _engine = create_engine(url, future=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()
```

- [ ] **Step 2: Initialize Alembic config (`alembic.ini`)**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 3: Write `alembic/env.py`**

```python
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from minimax_mcp.db import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["KB_DATABASE_URL"])
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Write the initial migration `alembic/versions/0001_initial.py`**

```python
"""initial schema: documents, chunks, embeddings + pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # mxbai-embed-large; bump + new migration if EMBEDDING_MODEL changes


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("transcription_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("tutorial", sa.Text, nullable=True),
        sa.Column("objectives", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("raw_file_path", sa.Text, nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id", sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
    )
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "chunk_id", sa.Integer,
            sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("vector", Vector(EMBEDDING_DIM), nullable=False),
    )
    op.create_index(
        "ix_chunks_text_tsv",
        "chunks",
        [sa.text("to_tsvector('portuguese', chunk_text)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_text_tsv", table_name="chunks")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("documents")
```

- [ ] **Step 5: Run the migration and verify**

```bash
cd $PROJECT_ROOT
source scripts/config.sh
uv run alembic upgrade head
docker exec "${KB_POSTGRES_CONTAINER:-minimax-kb-postgres}" psql -U "${KB_POSTGRES_USER:-kb}" -d "${KB_POSTGRES_DB:-knowledge}" -c "\dt"
```

Expected: `\dt` lists `documents`, `chunks`, `embeddings`, `alembic_version`.

- [ ] **Step 6: Commit**

```bash
git add src/minimax_mcp/db.py alembic.ini alembic/env.py alembic/versions/0001_initial.py
git commit -m "feat(kb): add SQLAlchemy models and initial Postgres migration"
```

---

### Task 3: `db.chunk_text` (pure logic)

**Files:**
- Modify: `src/minimax_mcp/db.py` (append)
- Create: `tests/unit_knowledge.py`

**Interfaces:**
- Consumes: nothing
- Produces: `db.chunk_text(text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]` — used by `save_document` (Task 4) and `reindex_all` (Task 5).

- [ ] **Step 1: Write the failing test in `tests/unit_knowledge.py`**

```python
#!/usr/bin/env python3
"""Pure-logic unit tests for the knowledge base modules — no Postgres, no Ollama.

Run: uv run --project . python tests/unit_knowledge.py
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
from minimax_mcp import db  # noqa: E402

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

print("")
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 2: Run it to confirm it fails (no `chunk_text` yet)**

```bash
cd $PROJECT_ROOT
uv run python tests/unit_knowledge.py
```

Expected: `AttributeError: module 'minimax_mcp.db' has no attribute 'chunk_text'`

- [ ] **Step 3: Append `chunk_text` to `src/minimax_mcp/db.py`**

```python
def chunk_text(text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding/search."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/unit_knowledge.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/db.py tests/unit_knowledge.py
git commit -m "feat(kb): add chunk_text with unit tests"
```

---

### Task 4: `db.save_document` (Postgres CRUD)

**Files:**
- Modify: `src/minimax_mcp/db.py` (append)
- Create: `tests/integration_knowledge_db.py`

**Interfaces:**
- Consumes: `db.Base/Document/Chunk/Embedding` (Task 2), `db.chunk_text` (Task 3), `db.get_session` (Task 2)
- Produces: `db.save_document(session, *, type, source_url, platform, title, language, transcription_text, summary, tutorial, objectives, tags, raw_file_path, llm_provider, llm_model, embed_fn, embedding_model) -> Document`. Used by `knowledge.ingest_text` (Task 9).

- [ ] **Step 1: Write the failing test in `tests/integration_knowledge_db.py`**

Requires the Postgres container from Task 1 running with the Task 2 migration applied. Uses a fake, deterministic `embed_fn` so this test never needs Ollama.

```python
#!/usr/bin/env python3
"""Postgres-dependent tests for db.py. Requires: `docker compose up -d postgres`
+ `alembic upgrade head` already applied (see Task 1/2). No Ollama required —
uses a fake deterministic embedding function.

Run: uv run --project . python tests/integration_knowledge_db.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import os  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import db  # noqa: E402


def fake_embed(text: str) -> list[float]:
    """Deterministic fake embedding: length matches EMBEDDING_DIM, values from hash."""
    dim = db.EMBEDDING_DIM
    seed = sum(ord(c) for c in text)
    return [((seed + i) % 100) / 100.0 for i in range(dim)]


print("== integration_knowledge_db: save_document ==")
session = db.get_session()
try:
    doc = db.save_document(
        session,
        type="text",
        source_url="https://example.com/test",
        platform="manual",
        title="Teste de ingestão",
        language="pt",
        transcription_text="Este é um texto de teste sobre Python e Docker. " * 50,
        summary="Resumo de teste sobre Python e Docker.",
        tutorial="## Passo 1\nInstale o Docker.\n## Passo 2\nInstale o Python.",
        objectives="Aprender Docker\nAprender Python",
        tags=["python", "docker", "teste"],
        raw_file_path=None,
        llm_provider="ollama",
        llm_model="qwen2.5:32b-instruct-q4_K_M",
        embed_fn=fake_embed,
        embedding_model="fake-embed-test",
    )
    if doc.id is not None:
        ok(f"save_document created document id={doc.id}")
    else:
        bad("save_document did not assign an id")

    if len(doc.chunks) >= 1:
        ok(f"save_document created {len(doc.chunks)} chunk(s)")
    else:
        bad("save_document created no chunks")

    if all(c.embedding is not None for c in doc.chunks):
        ok("every chunk has an embedding")
    else:
        bad("some chunk is missing its embedding")
except Exception as e:
    bad(f"save_document raised: {e}")
finally:
    session.close()

print("")
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 2: Run it to confirm it fails (no `save_document` yet)**

```bash
cd $PROJECT_ROOT
source scripts/config.sh
uv run python tests/integration_knowledge_db.py
```

Expected: `AttributeError: module 'minimax_mcp.db' has no attribute 'save_document'`

- [ ] **Step 3: Append `save_document` to `src/minimax_mcp/db.py`**

Add these imports at the top alongside the existing ones: `from typing import Callable` and `from sqlalchemy import delete, select`.

```python
def save_document(
    session: Session,
    *,
    type: str,
    source_url: str | None,
    platform: str | None,
    title: str | None,
    language: str | None,
    transcription_text: str | None,
    summary: str | None,
    tutorial: str | None,
    objectives: str | None,
    tags: list[str] | None,
    raw_file_path: str | None,
    llm_provider: str | None,
    llm_model: str | None,
    embed_fn: Callable[[str], list[float]],
    embedding_model: str,
) -> Document:
    """Insert a Document + its chunks + their embeddings in one transaction."""
    doc = Document(
        type=type, source_url=source_url, platform=platform, title=title,
        language=language, transcription_text=transcription_text, summary=summary,
        tutorial=tutorial, objectives=objectives, tags=tags,
        raw_file_path=raw_file_path, llm_provider=llm_provider, llm_model=llm_model,
    )
    session.add(doc)
    session.flush()  # assigns doc.id

    text_for_chunks = "\n\n".join(filter(None, [summary, tutorial, transcription_text]))
    for idx, piece in enumerate(chunk_text(text_for_chunks)):
        chunk = Chunk(document_id=doc.id, chunk_text=piece, chunk_index=idx)
        session.add(chunk)
        session.flush()  # assigns chunk.id
        vector = embed_fn(piece)
        session.add(Embedding(chunk_id=chunk.id, model=embedding_model, vector=vector))

    session.commit()
    session.refresh(doc)
    return doc
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/integration_knowledge_db.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/db.py tests/integration_knowledge_db.py
git commit -m "feat(kb): add save_document with Postgres integration test"
```

---

### Task 5: `db.search_documents` + `db.reindex_all`

**Files:**
- Modify: `src/minimax_mcp/db.py` (append)
- Modify: `tests/integration_knowledge_db.py` (append)

**Interfaces:**
- Consumes: `db.Document/Chunk/Embedding`, `db.chunk_text`, `db.save_document`, `db.get_session`
- Produces: `db.search_documents(session, query: str, embed_fn, top_k: int = 5) -> list[dict]` and `db.reindex_all(session, embed_fn, embedding_model: str) -> int`. Used by `knowledge.search`/`knowledge.ask` (Task 11) and `knowledge.reindex` (Task 11).

- [ ] **Step 1: Append the failing test to `tests/integration_knowledge_db.py`**

Insert before the final `print("")` / `if FAIL:` block:

```python
print("== integration_knowledge_db: search_documents ==")
try:
    results = db.search_documents(session, "Docker", embed_fn=fake_embed, top_k=5)
    if isinstance(results, list) and len(results) >= 1:
        ok(f"search_documents('Docker') returned {len(results)} result(s)")
    else:
        bad(f"search_documents('Docker') returned {results!r}")

    if results and results[0].get("document_id") == doc.id:
        ok("top result matches the document created in save_document test")
    else:
        bad(f"top result did not match: {results[0] if results else None}")
except Exception as e:
    bad(f"search_documents raised: {e}")

print("== integration_knowledge_db: reindex_all ==")
try:
    count = db.reindex_all(session, embed_fn=fake_embed, embedding_model="fake-embed-test-v2")
    if count >= 1:
        ok(f"reindex_all processed {count} document(s)")
    else:
        bad("reindex_all processed 0 documents")

    refreshed = session.get(db.Document, doc.id)
    if refreshed and all(c.embedding.model == "fake-embed-test-v2" for c in refreshed.chunks):
        ok("reindex_all regenerated embeddings with the new model tag")
    else:
        bad("reindex_all did not update embedding model tags")
except Exception as e:
    bad(f"reindex_all raised: {e}")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd $PROJECT_ROOT
source scripts/config.sh
uv run python tests/integration_knowledge_db.py
```

Expected: `AttributeError: module 'minimax_mcp.db' has no attribute 'search_documents'`

- [ ] **Step 3: Append `search_documents` and `reindex_all` to `src/minimax_mcp/db.py`**

```python
def search_documents(
    session: Session, query: str, embed_fn: Callable[[str], list[float]], top_k: int = 5
) -> list[dict[str, Any]]:
    """Combine Postgres full-text search with pgvector cosine similarity."""
    tsquery = func.plainto_tsquery("portuguese", query)
    keyword_rows = session.execute(
        select(
            Chunk.document_id,
            Chunk.chunk_text,
            func.ts_rank(func.to_tsvector("portuguese", Chunk.chunk_text), tsquery).label("score"),
        )
        .where(func.to_tsvector("portuguese", Chunk.chunk_text).op("@@")(tsquery))
        .order_by(func.ts_rank(func.to_tsvector("portuguese", Chunk.chunk_text), tsquery).desc())
        .limit(top_k)
    ).all()

    query_vector = embed_fn(query)
    semantic_rows = session.execute(
        select(
            Chunk.document_id,
            Chunk.chunk_text,
            Embedding.vector.cosine_distance(query_vector).label("distance"),
        )
        .join(Embedding, Embedding.chunk_id == Chunk.id)
        .order_by(Embedding.vector.cosine_distance(query_vector))
        .limit(top_k)
    ).all()

    merged: dict[int, dict[str, Any]] = {}
    for row in keyword_rows:
        entry = merged.setdefault(
            row.document_id, {"document_id": row.document_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(row.chunk_text)
        entry["score"] += float(row.score)
    for row in semantic_rows:
        similarity = 1.0 - float(row.distance)
        entry = merged.setdefault(
            row.document_id, {"document_id": row.document_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(row.chunk_text)
        entry["score"] += similarity

    ranked = sorted(merged.values(), key=lambda r: r["score"], reverse=True)[:top_k]
    doc_ids = [r["document_id"] for r in ranked]
    if doc_ids:
        docs_by_id = {
            d.id: d for d in session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars()
        }
        for r in ranked:
            d = docs_by_id.get(r["document_id"])
            if d is not None:
                r["title"] = d.title
                r["source_url"] = d.source_url
                r["summary"] = d.summary
    return ranked


def reindex_all(session: Session, embed_fn: Callable[[str], list[float]], embedding_model: str) -> int:
    """Recompute chunks + embeddings for every document (e.g. after changing EMBEDDING_MODEL)."""
    docs = session.execute(select(Document)).scalars().all()
    for doc in docs:
        session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        session.flush()
        text_for_chunks = "\n\n".join(filter(None, [doc.summary, doc.tutorial, doc.transcription_text]))
        for idx, piece in enumerate(chunk_text(text_for_chunks)):
            chunk = Chunk(document_id=doc.id, chunk_text=piece, chunk_index=idx)
            session.add(chunk)
            session.flush()
            vector = embed_fn(piece)
            session.add(Embedding(chunk_id=chunk.id, model=embedding_model, vector=vector))
    session.commit()
    return len(docs)
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/integration_knowledge_db.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/db.py tests/integration_knowledge_db.py
git commit -m "feat(kb): add search_documents (full-text + cosine) and reindex_all"
```

---

### Task 6: `llm.py` — prompt building + JSON parsing (pure logic)

**Files:**
- Create: `src/minimax_mcp/llm.py`
- Modify: `tests/unit_knowledge.py` (append)

**Interfaces:**
- Consumes: nothing
- Produces: `llm.build_summary_prompt(transcription: str) -> str`, `llm.parse_llm_json(raw: str) -> dict`. Used by `llm.generate_structured` (Task 7).

- [ ] **Step 1: Append the failing test to `tests/unit_knowledge.py`**

Insert before the final `print("")` / `if FAIL:` block:

```python
print("== unit_knowledge: llm.build_summary_prompt / parse_llm_json ==")
from minimax_mcp import llm  # noqa: E402

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
```

- [ ] **Step 2: Run it to confirm it fails (module doesn't exist yet)**

```bash
cd $PROJECT_ROOT
uv run python tests/unit_knowledge.py
```

Expected: `ModuleNotFoundError: No module named 'minimax_mcp.llm'`

- [ ] **Step 3: Write `src/minimax_mcp/llm.py`**

```python
"""Abstract LLM client for the knowledge base: Ollama (default) or OpenAI-compatible."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:32b-instruct-q4_K_M")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "mxbai-embed-large")
OPENAI_API_URL = os.environ.get("OPENAI_API_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SUMMARY_PROMPT_TEMPLATE = """\
Você é um assistente que documenta conteúdo para uma base de conhecimento pessoal.

Dada a transcrição abaixo, responda APENAS com um JSON válido (sem markdown, sem texto \
fora do JSON) com estas chaves:
- "resumo": um resumo conciso (3-5 frases) do conteúdo.
- "tutorial": um tutorial detalhado, passo a passo, do que foi ensinado/demonstrado, em markdown.
- "objetivos": uma lista de objetivos/aprendizados principais (array de strings).
- "tags": uma lista de 3 a 8 tags curtas relevantes (array de strings).

Transcrição:
{transcription}
"""


def build_summary_prompt(transcription: str) -> str:
    return SUMMARY_PROMPT_TEMPLATE.format(transcription=transcription.strip())


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of an LLM response, tolerating ```json fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/unit_knowledge.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/llm.py tests/unit_knowledge.py
git commit -m "feat(kb): add llm.py prompt building and JSON parsing with unit tests"
```

---

### Task 7: `llm.generate_structured`, `llm.embed`, `llm.chat` (live Ollama)

**Files:**
- Modify: `src/minimax_mcp/llm.py` (append)
- Create: `tests/integration_knowledge_llm.py`

**Interfaces:**
- Consumes: `llm.build_summary_prompt`, `llm.parse_llm_json` (Task 6)
- Produces: `llm.generate_structured(transcription: str, *, provider=None, model=None) -> dict` (keys: `ok`, `resumo`, `tutorial`, `objetivos`, `tags`, `provider`, `model` on success; `ok=False`, `error` on failure), `llm.embed(text: str, *, model=None) -> list[float]`, `llm.chat(prompt: str, *, provider=None, model=None) -> str`. Used by `knowledge.ingest_text` (Task 9) and `knowledge.ask` (Task 11).

- [ ] **Step 1: Write the failing test in `tests/integration_knowledge_llm.py`**

Requires Ollama running locally with `qwen2.5:32b-instruct-q4_K_M` and `mxbai-embed-large` pulled (already confirmed present via `ollama list`).

```python
#!/usr/bin/env python3
"""Ollama-dependent tests for llm.py. Requires a local Ollama daemon at
OLLAMA_URL with LLM_MODEL and EMBEDDING_MODEL already pulled.

Run: uv run --project . python tests/integration_knowledge_llm.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import llm  # noqa: E402

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
if isinstance(vector, list) and len(vector) == llm.__dict__.get("EMBEDDING_DIM_HINT", len(vector)):
    ok(f"embed returned a {len(vector)}-dim vector")
elif isinstance(vector, list) and len(vector) > 0:
    ok(f"embed returned a {len(vector)}-dim vector")
else:
    bad(f"embed returned unexpected value: {vector!r}")

print("== integration_knowledge_llm: chat ==")
answer = llm.chat("Responda em uma frase curta: qual comando instala o Docker no Ubuntu?")
if isinstance(answer, str) and len(answer.strip()) > 0:
    ok(f"chat returned non-empty answer: {answer[:80]!r}...")
else:
    bad(f"chat returned unexpected value: {answer!r}")

print("")
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 2: Run it to confirm it fails (functions don't exist yet)**

```bash
cd $PROJECT_ROOT
uv run python tests/integration_knowledge_llm.py
```

Expected: `AttributeError: module 'minimax_mcp.llm' has no attribute 'generate_structured'`

- [ ] **Step 3: Append `generate_structured`, `embed`, `chat` (and their HTTP helpers) to `src/minimax_mcp/llm.py`**

```python
def _ollama_generate(prompt: str, model: str, *, force_json: bool) -> str:
    payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    if force_json:
        payload["format"] = "json"
    resp = httpx.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300.0)
    resp.raise_for_status()
    return resp.json()["response"]


def _openai_compatible_generate(prompt: str, model: str, *, force_json: bool) -> str:
    if not OPENAI_API_URL:
        raise RuntimeError("OPENAI_API_URL not configured")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}
    resp = httpx.post(f"{OPENAI_API_URL}/chat/completions", headers=headers, json=body, timeout=300.0)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def generate_structured(
    transcription: str, *, provider: str | None = None, model: str | None = None
) -> dict[str, Any]:
    """Ask the configured LLM for {resumo, tutorial, objetivos, tags} as JSON."""
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL
    prompt = build_summary_prompt(transcription)
    try:
        if provider == "ollama":
            raw = _ollama_generate(prompt, model, force_json=True)
        elif provider == "openai-compatible":
            raw = _openai_compatible_generate(prompt, model, force_json=True)
        else:
            return {"ok": False, "error": f"Unknown LLM_PROVIDER: {provider}"}

        parsed = parse_llm_json(raw)
        required = {"resumo", "tutorial", "objetivos", "tags"}
        missing = required - parsed.keys()
        if missing:
            return {"ok": False, "error": f"LLM response missing keys: {missing}", "raw": raw}
        return {"ok": True, "provider": provider, "model": model, **parsed}
    except Exception as e:
        return {"ok": False, "error": f"LLM generation failed: {e}"}


def embed(text: str, *, model: str | None = None) -> list[float]:
    """Generate an embedding via Ollama. Always local, independent of LLM_PROVIDER."""
    model = model or EMBEDDING_MODEL
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings", json={"model": model, "prompt": text}, timeout=120.0
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def chat(prompt: str, *, provider: str | None = None, model: str | None = None) -> str:
    """Free-text completion (no forced JSON) — used for RAG answers."""
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL
    if provider == "ollama":
        return _ollama_generate(prompt, model, force_json=False)
    if provider == "openai-compatible":
        return _openai_compatible_generate(prompt, model, force_json=False)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/integration_knowledge_llm.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/llm.py tests/integration_knowledge_llm.py
git commit -m "feat(kb): add generate_structured/embed/chat with Ollama integration tests"
```

---

### Task 8: `vault.py` — optional markdown export

**Files:**
- Create: `src/minimax_mcp/vault.py`
- Modify: `tests/unit_knowledge.py` (append)

**Interfaces:**
- Consumes: nothing
- Produces: `vault.write_markdown_copy(document: dict, vault_path: str | None) -> dict` (`{"ok": True, "skipped": bool, ...}` — never raises, never blocks the caller). Used by `knowledge.ingest_text` (Task 9).

- [ ] **Step 1: Append the failing test to `tests/unit_knowledge.py`**

Insert before the final `print("")` / `if FAIL:` block:

```python
print("== unit_knowledge: vault.write_markdown_copy ==")
import tempfile  # noqa: E402
from minimax_mcp import vault  # noqa: E402

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
```

- [ ] **Step 2: Run it to confirm it fails (module doesn't exist yet)**

```bash
cd $PROJECT_ROOT
uv run python tests/unit_knowledge.py
```

Expected: `ModuleNotFoundError: No module named 'minimax_mcp.vault'`

- [ ] **Step 3: Write `src/minimax_mcp/vault.py`**

```python
"""Optional, best-effort markdown export of knowledge base documents to Obsidian."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60] or "sem-titulo"


def write_markdown_copy(document: dict[str, Any], vault_path: str | Path | None) -> dict[str, Any]:
    """Write a readable .md copy of `document` under `<vault_path>/Knowledge/`.

    Never raises and never returns ok=False: a broken/missing vault must not
    block ingestion, which already succeeded in Postgres by the time this runs.
    """
    if not vault_path:
        return {"ok": True, "skipped": True, "reason": "VAULT_PATH not configured"}
    try:
        folder = Path(vault_path) / "Knowledge"
        folder.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = _slugify(document.get("title") or f"documento-{document.get('id')}")
        filepath = folder / f"{date_str}-{slug}.md"

        tags = document.get("tags") or []
        tags_line = " ".join(f"#{t}" for t in tags)

        content = (
            "---\n"
            f"source_url: {document.get('source_url') or ''}\n"
            f"platform: {document.get('platform') or ''}\n"
            f"type: {document.get('type') or ''}\n"
            f"created_at: {date_str}\n"
            "---\n\n"
            f"# {document.get('title') or slug}\n\n"
            f"{tags_line}\n\n"
            f"## Resumo\n\n{document.get('summary') or ''}\n\n"
            f"## Tutorial\n\n{document.get('tutorial') or ''}\n\n"
            f"## Transcrição completa\n\n{document.get('transcription_text') or ''}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return {"ok": True, "skipped": False, "path": str(filepath)}
    except Exception as e:
        logger.warning("Vault markdown copy failed (non-blocking): %s", e)
        return {"ok": True, "skipped": True, "reason": str(e)}
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
uv run python tests/unit_knowledge.py
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/vault.py tests/unit_knowledge.py
git commit -m "feat(kb): add best-effort Obsidian markdown export with unit tests"
```

---

### Task 9: `knowledge.ingest_text` + `knowledge_ingest_text` MCP tool

**Files:**
- Create: `src/minimax_mcp/knowledge.py`
- Modify: `src/minimax_mcp/server.py` (add tool)
- Create: `tests/08_knowledge.sh`

**Interfaces:**
- Consumes: `llm.generate_structured`, `llm.embed`, `llm.EMBEDDING_MODEL` (Task 6/7); `db.get_session`, `db.save_document` (Task 2/4); `vault.write_markdown_copy` (Task 8)
- Produces: `knowledge.ingest_text(text: str, *, source_url=None, title=None, platform="manual", doc_type="text", language="pt") -> dict` (`{"ok": True, "document_id", "title", "summary", "tutorial", "tags", "vault"}` or `{"ok": False, "stage", "error"}`). Used by `knowledge.ingest_video`/`ingest_audio` (Task 10). MCP tool `knowledge_ingest_text(text, source_url?, title?, platform?) -> dict`.

- [ ] **Step 1: Write `src/minimax_mcp/knowledge.py` with `ingest_text`**

```python
"""Orchestration layer for the knowledge base: ties together llm.py, db.py, vault.py
and the existing downloader/transcriber, and is what server.py's MCP tools call."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from minimax_mcp import db, llm, vault

logger = logging.getLogger(__name__)

VAULT_PATH = os.environ.get("VAULT_PATH") or None


def ingest_text(
    text: str,
    *,
    source_url: str | None = None,
    title: str | None = None,
    platform: str = "manual",
    doc_type: str = "text",
    language: str = "pt",
) -> dict[str, Any]:
    """Summarize+document `text` via the LLM and store it in the knowledge base."""
    if not text or not text.strip():
        return {"ok": False, "error": "empty text"}

    gen = llm.generate_structured(text)
    if not gen.get("ok"):
        return {"ok": False, "stage": "llm", "error": gen.get("error")}

    session = db.get_session()
    try:
        doc = db.save_document(
            session,
            type=doc_type,
            source_url=source_url,
            platform=platform,
            title=title or (gen["resumo"][:80] if gen.get("resumo") else "sem título"),
            language=language,
            transcription_text=text,
            summary=gen.get("resumo"),
            tutorial=gen.get("tutorial"),
            objectives="\n".join(gen.get("objetivos") or []),
            tags=gen.get("tags") or [],
            raw_file_path=None,
            llm_provider=gen.get("provider"),
            llm_model=gen.get("model"),
            embed_fn=llm.embed,
            embedding_model=llm.EMBEDDING_MODEL,
        )
        doc_dict = {
            "id": doc.id, "title": doc.title, "summary": doc.summary, "tutorial": doc.tutorial,
            "tags": doc.tags, "source_url": doc.source_url, "platform": doc.platform,
            "type": doc.type, "transcription_text": doc.transcription_text,
        }
    except Exception as e:
        session.rollback()
        return {"ok": False, "stage": "db", "error": str(e)}
    finally:
        session.close()

    vault_result = vault.write_markdown_copy(doc_dict, VAULT_PATH)
    return {
        "ok": True, "document_id": doc_dict["id"], "title": doc_dict["title"],
        "summary": doc_dict["summary"], "tutorial": doc_dict["tutorial"],
        "tags": doc_dict["tags"], "vault": vault_result,
    }
```

- [ ] **Step 2: Add the `knowledge_ingest_text` tool to `src/minimax_mcp/server.py`**

Add near the end of the `# NEW: Audiovisual Studio Tools` section (after `studio_pipeline`), and add `from typing import Optional` is already imported at the top:

```python
# =============================================================================
# NEW: Knowledge Base Tools
# =============================================================================

@mcp.tool()
def knowledge_ingest_text(
    text: str = Field(description="Texto/transcrição já pronta para processar"),
    source_url: Optional[str] = Field(default=None, description="URL de origem, se houver"),
    title: Optional[str] = Field(default=None, description="Título do documento"),
    platform: str = Field(default="manual", description="Origem: manual, instagram, youtube, podcast"),
) -> dict[str, Any]:
    """Gera resumo+tutorial via LLM local e salva um texto/transcrição já pronto na base de conhecimento."""
    from minimax_mcp import knowledge
    return knowledge.ingest_text(text, source_url=source_url, title=title, platform=platform)
```

- [ ] **Step 3: Write the failing end-to-end test `tests/08_knowledge.sh`**

```bash
#!/usr/bin/env bash
# tests/08_knowledge.sh — knowledge base MCP tools over stdio.
# Prerequisites: Postgres up + migrated (Task 1/2), Ollama running with
# LLM_MODEL and EMBEDDING_MODEL pulled (Task 6/7). Server runs in host-uv mode.
set -u
FAIL=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi

echo "== Knowledge base (MCP stdio, host uv) =="

SAMPLE_TEXT="Hoje vou mostrar como instalar o Docker no Ubuntu. Primeiro, atualize os pacotes com apt update. Depois, instale com apt install docker.io. Por fim, adicione seu usuario ao grupo docker para nao precisar de sudo."

uv run --project "$ROOT" python - "$ROOT" "$SAMPLE_TEXT" <<'PY' || FAIL=1
import asyncio, json, os, sys

root, sample_text = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "src"))

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main() -> int:
    env = dict(os.environ)
    transport = StdioTransport(
        command="uv", args=["run", "--project", root, "python", "src/minimax_mcp/server.py"],
        cwd=root, env=env,
    )
    async with Client(transport) as client:
        print("  [ok]   connected to MCP server over stdio (host uv)")

        r = await client.call_tool("knowledge_ingest_text", {
            "text": sample_text, "title": "Instalar Docker no Ubuntu", "platform": "manual",
        })
        rd = json.loads(r.content[0].text)
        if not rd.get("ok"):
            print(f"  [BAD] knowledge_ingest_text failed: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_ingest_text -> document_id={rd['document_id']}")
        print(f"         tags={rd.get('tags')}")
        return 0

try:
    sys.exit(asyncio.run(main()))
except Exception as e:  # noqa: BLE001
    print(f"  [BAD] exception: {e}")
    sys.exit(1)
PY

exit "$FAIL"
```

```bash
chmod +x $PROJECT_ROOT/tests/08_knowledge.sh
```

- [ ] **Step 4: Run it to confirm it fails (tool not registered yet / module missing)**

```bash
cd $PROJECT_ROOT
./tests/08_knowledge.sh
```

Expected: fails with an MCP "unknown tool" error before Step 1/2 are applied; after applying them it should reach Step 5.

- [ ] **Step 5: Run it again to confirm it passes**

```bash
./tests/08_knowledge.sh
```

Expected: `[ok] knowledge_ingest_text -> document_id=<N>`, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add src/minimax_mcp/knowledge.py src/minimax_mcp/server.py tests/08_knowledge.sh
git commit -m "feat(kb): add knowledge.ingest_text and knowledge_ingest_text MCP tool"
```

---

### Task 10: `knowledge.ingest_video` / `ingest_audio` + MCP tools

**Files:**
- Modify: `src/minimax_mcp/knowledge.py` (append)
- Modify: `src/minimax_mcp/server.py` (add 2 tools)

**Interfaces:**
- Consumes: `knowledge.ingest_text` (Task 9), `downloader.VideoDownloader` (existing), `transcriber.AudioTranscriber` (existing)
- Produces: `knowledge.ingest_video(url, *, browser="chrome", downloads_dir="downloads", whisper_model="small", whisper_device="cuda") -> dict`, `knowledge.ingest_audio(path_or_url, *, browser="chrome", downloads_dir="downloads", whisper_model="small", whisper_device="cuda") -> dict`. MCP tools `knowledge_ingest_video`, `knowledge_ingest_audio`.

This task is network/GPU-dependent (Instagram download + Whisper on GPU), matching how `download_video`/`transcribe_video`/`studio_pipeline` are already excluded from the automated test suite — verification here is manual, run once against a real URL, same as documented in `AGENTS.md` §9.

- [ ] **Step 1: Append `ingest_video` and `ingest_audio` to `src/minimax_mcp/knowledge.py`**

```python
def ingest_video(
    url: str,
    *,
    browser: str = "chrome",
    downloads_dir: str | Path = "downloads",
    whisper_model: str = "small",
    whisper_device: str = "cuda",
) -> dict[str, Any]:
    """Download a video, transcribe it, and document it in the knowledge base."""
    from minimax_mcp.downloader import VideoDownloader
    from minimax_mcp.transcriber import AudioTranscriber

    downloader = VideoDownloader(output_dir=downloads_dir, browser=browser)
    dl = downloader.download(url)
    if not dl.get("ok"):
        return {"ok": False, "stage": "download", "error": dl.get("error")}

    transcriber = AudioTranscriber(model_size=whisper_model, device=whisper_device)
    tr = transcriber.transcribe(dl["filepath"])
    if not tr.get("ok"):
        return {"ok": False, "stage": "transcribe", "error": tr.get("error")}

    if "instagram" in url:
        platform = "instagram"
    elif "youtu" in url:
        platform = "youtube"
    else:
        platform = "video"

    result = ingest_text(
        tr["text"], source_url=dl.get("webpage_url", url), title=dl.get("title"),
        platform=platform, doc_type="video", language=tr.get("language", "pt"),
    )
    if result.get("ok"):
        result["downloaded_file"] = dl["filepath"]
    return result


def ingest_audio(
    path_or_url: str,
    *,
    browser: str = "chrome",
    downloads_dir: str | Path = "downloads",
    whisper_model: str = "small",
    whisper_device: str = "cuda",
) -> dict[str, Any]:
    """Transcribe a local audio file (or download it first if given a URL) and
    document it in the knowledge base."""
    from minimax_mcp.downloader import VideoDownloader
    from minimax_mcp.transcriber import AudioTranscriber

    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        downloader = VideoDownloader(output_dir=downloads_dir, browser=browser)
        dl = downloader.download(path_or_url)
        if not dl.get("ok"):
            return {"ok": False, "stage": "download", "error": dl.get("error")}
        filepath = dl["filepath"]
        title = dl.get("title")
        source_url = dl.get("webpage_url", path_or_url)
    else:
        filepath = path_or_url
        title = Path(path_or_url).stem
        source_url = None

    transcriber = AudioTranscriber(model_size=whisper_model, device=whisper_device)
    tr = transcriber.transcribe(filepath)
    if not tr.get("ok"):
        return {"ok": False, "stage": "transcribe", "error": tr.get("error")}

    result = ingest_text(
        tr["text"], source_url=source_url, title=title,
        platform="podcast", doc_type="audio", language=tr.get("language", "pt"),
    )
    if result.get("ok"):
        result["source_file"] = filepath
    return result
```

- [ ] **Step 2: Add the two MCP tools to `src/minimax_mcp/server.py`**

Append after `knowledge_ingest_text`:

```python
@mcp.tool()
def knowledge_ingest_video(
    url: str = Field(description="URL do vídeo (Instagram Reel, YouTube, etc.)"),
    browser: str = Field(default=STUDIO_BROWSER, description="Navegador para cookies"),
    whisper_model: str = Field(default=WHISPER_MODEL, description="Tamanho do modelo Whisper"),
) -> dict[str, Any]:
    """Baixa, transcreve e documenta um vídeo na base de conhecimento (resumo + tutorial via LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ingest_video(
        url, browser=browser, downloads_dir=STUDIO_DOWNLOADS_DIR,
        whisper_model=whisper_model, whisper_device=WHISPER_DEVICE,
    )


@mcp.tool()
def knowledge_ingest_audio(
    path_or_url: str = Field(description="Caminho local de um áudio/podcast, ou URL para baixar"),
    browser: str = Field(default=STUDIO_BROWSER, description="Navegador para cookies (se for URL)"),
    whisper_model: str = Field(default=WHISPER_MODEL, description="Tamanho do modelo Whisper"),
) -> dict[str, Any]:
    """Transcreve e documenta um áudio/podcast na base de conhecimento (resumo + tutorial via LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ingest_audio(
        path_or_url, browser=browser, downloads_dir=STUDIO_DOWNLOADS_DIR,
        whisper_model=whisper_model, whisper_device=WHISPER_DEVICE,
    )
```

- [ ] **Step 3: Manual verification (documented, not automated — mirrors existing `studio_pipeline` testing)**

```bash
cd $PROJECT_ROOT
source scripts/config.sh
uv run python -c "
from minimax_mcp import knowledge
r = knowledge.ingest_video('https://www.instagram.com/p/REPLACE_ME/', whisper_model='small', whisper_device='cpu')
print(r)
"
```

Expected: `{"ok": True, "document_id": ..., ...}`. Replace the URL with a real Reel you have access to; use `whisper_device='cpu'` if the GPU is busy with ComfyUI.

- [ ] **Step 4: Commit**

```bash
git add src/minimax_mcp/knowledge.py src/minimax_mcp/server.py
git commit -m "feat(kb): add knowledge.ingest_video/ingest_audio and their MCP tools"
```

---

### Task 11: `knowledge.search` / `ask` / `reindex` + MCP tools

**Files:**
- Modify: `src/minimax_mcp/knowledge.py` (append)
- Modify: `src/minimax_mcp/server.py` (add 3 tools)
- Modify: `tests/08_knowledge.sh` (append)

**Interfaces:**
- Consumes: `db.search_documents`, `db.reindex_all` (Task 5), `llm.embed`, `llm.chat` (Task 7), `knowledge.ingest_text` (Task 9, for the test fixture)
- Produces: `knowledge.search(query, top_k=5) -> dict`, `knowledge.ask(query, top_k=3) -> dict`, `knowledge.reindex(embedding_model=None) -> dict`. MCP tools `knowledge_search`, `knowledge_ask`, `knowledge_reindex`.

- [ ] **Step 1: Append `search`, `ask`, `reindex` to `src/minimax_mcp/knowledge.py`**

```python
def search(query: str, top_k: int = 5) -> dict[str, Any]:
    if not query or not query.strip():
        return {"ok": False, "error": "empty query"}
    session = db.get_session()
    try:
        results = db.search_documents(session, query, embed_fn=llm.embed, top_k=top_k)
    finally:
        session.close()
    return {"ok": True, "query": query, "results": results}


def ask(query: str, top_k: int = 3) -> dict[str, Any]:
    search_result = search(query, top_k=top_k)
    if not search_result.get("ok"):
        return search_result

    results = search_result["results"]
    if not results:
        return {
            "ok": True, "query": query,
            "answer": "Nada encontrado na base de conhecimento para essa pergunta.",
            "sources": [],
        }

    context = "\n\n---\n\n".join(
        f"[{r.get('title') or 'sem título'}] {' '.join(r['snippets'])}" for r in results
    )
    prompt = (
        "Responda à pergunta do usuário usando APENAS o contexto abaixo, extraído da base "
        "de conhecimento pessoal dele. Se o contexto não tiver a resposta, diga isso "
        "claramente em vez de inventar.\n\n"
        f"Contexto:\n{context}\n\nPergunta: {query}\n\nResposta:"
    )
    try:
        answer = llm.chat(prompt)
    except Exception as e:
        return {"ok": False, "error": f"LLM chat failed: {e}"}

    sources = [
        {"document_id": r["document_id"], "title": r.get("title"), "source_url": r.get("source_url")}
        for r in results
    ]
    return {"ok": True, "query": query, "answer": answer, "sources": sources}


def reindex(embedding_model: str | None = None) -> dict[str, Any]:
    session = db.get_session()
    try:
        count = db.reindex_all(
            session, embed_fn=llm.embed, embedding_model=embedding_model or llm.EMBEDDING_MODEL
        )
    finally:
        session.close()
    return {"ok": True, "documents_reindexed": count}
```

- [ ] **Step 2: Add the three MCP tools to `src/minimax_mcp/server.py`**

```python
@mcp.tool()
def knowledge_search(
    query: str = Field(description="Termo ou pergunta para buscar na base de conhecimento"),
    top_k: int = Field(default=5, description="Número máximo de resultados"),
) -> dict[str, Any]:
    """Busca na base de conhecimento (palavra-chave + semântica) e retorna os documentos mais relevantes."""
    from minimax_mcp import knowledge
    return knowledge.search(query, top_k=top_k)


@mcp.tool()
def knowledge_ask(
    query: str = Field(description="Pergunta em linguagem natural sobre o que já foi salvo"),
    top_k: int = Field(default=3, description="Quantos documentos usar como contexto"),
) -> dict[str, Any]:
    """Responde a uma pergunta usando RAG sobre a base de conhecimento (busca + LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ask(query, top_k=top_k)


@mcp.tool()
def knowledge_reindex(
    embedding_model: Optional[str] = Field(
        default=None, description="Modelo de embedding a usar (default: EMBEDDING_MODEL do .env)"
    ),
) -> dict[str, Any]:
    """Recalcula chunks e embeddings de todos os documentos (use após trocar de modelo de embedding)."""
    from minimax_mcp import knowledge
    return knowledge.reindex(embedding_model=embedding_model)
```

- [ ] **Step 3: Append to the Python block inside `tests/08_knowledge.sh`**

Replace the `return 0` at the end of `main()` with:

```python
        r = await client.call_tool("knowledge_search", {"query": "Docker Ubuntu", "top_k": 5})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or not rd.get("results"):
            print(f"  [BAD] knowledge_search failed or empty: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_search -> {len(rd['results'])} result(s)")

        r = await client.call_tool("knowledge_ask", {"query": "Como instalar o Docker no Ubuntu?"})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or not rd.get("answer"):
            print(f"  [BAD] knowledge_ask failed or empty answer: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_ask -> {rd['answer'][:100]!r}...")

        r = await client.call_tool("knowledge_reindex", {})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or rd.get("documents_reindexed", 0) < 1:
            print(f"  [BAD] knowledge_reindex failed: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_reindex -> {rd['documents_reindexed']} document(s)")

        print("  [PASS] full knowledge base flow OK")
        return 0
```

- [ ] **Step 4: Run `tests/08_knowledge.sh` to confirm it fails, then passes**

```bash
cd $PROJECT_ROOT
./tests/08_knowledge.sh   # fails: unknown tool knowledge_search
# apply Steps 1-2 above
./tests/08_knowledge.sh   # expected: [PASS] full knowledge base flow OK
```

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/knowledge.py src/minimax_mcp/server.py tests/08_knowledge.sh
git commit -m "feat(kb): add knowledge.search/ask/reindex and their MCP tools"
```

---

### Task 12: Docs + host-mode wiring

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `~/.config/opencode/opencode.json` (or wherever the project's OpenCode MCP config lives — confirm path before editing)

**Interfaces:**
- Consumes: nothing new — this task only documents Tasks 1-11.
- Produces: nothing new — no other task depends on this one.

- [ ] **Step 1: Add a "Knowledge Base" section to `README.md`**

Insert after the existing "New: Audiovisual Studio MCP Tools" table:

```markdown
## New: Knowledge Base MCP Tools

Personal knowledge base backed by Postgres + pgvector, with a local LLM (Ollama by
default) turning transcriptions into structured summaries/tutorials.

| Tool | Description |
|---|---|
| `knowledge_ingest_text(text, source_url?, title?, platform?)` | Summarize+document a ready-made text/transcription |
| `knowledge_ingest_video(url, browser?, whisper_model?)` | Download + transcribe + document a video |
| `knowledge_ingest_audio(path_or_url, browser?, whisper_model?)` | Transcribe + document a local/downloaded audio (podcasts) |
| `knowledge_search(query, top_k?)` | Full-text + semantic (pgvector) search |
| `knowledge_ask(query, top_k?)` | RAG: answer a question using the knowledge base as context |
| `knowledge_reindex(embedding_model?)` | Recompute chunks/embeddings for every document |

Setup: `docker compose $COMPOSE_ARGS up -d postgres` then `uv run alembic upgrade head`
(see `AGENTS.md` §10). Requires Ollama running locally with `LLM_MODEL` and
`EMBEDDING_MODEL` pulled.

Full parameter-level reference for every tool (this table and the original
Audiovisual Studio one) is auto-generated — see
[`docs/MCP_TOOLS.md`](docs/MCP_TOOLS.md), regenerated via
`uv run python scripts/generate_mcp_docs.py`. Don't hand-edit that file.
```

- [ ] **Step 2: Regenerate `docs/MCP_TOOLS.md` now that all 6 knowledge tools exist**

```bash
cd $PROJECT_ROOT
uv run python scripts/generate_mcp_docs.py
grep -c '^## `' docs/MCP_TOOLS.md
```

Expected: count is now 11 (original) + 6 (knowledge) = 17.

- [ ] **Step 3: Add a "§10. Knowledge Base" section to `AGENTS.md`**

Append after §9 (before the final validation cheat-sheet section, or at the end):

```markdown
## 10. Knowledge Base (Postgres + pgvector + local LLM)

**Setup:**
1. `docker compose $COMPOSE_ARGS up -d postgres` — brings up Postgres with pgvector.
2. `uv run alembic upgrade head` — creates `documents`/`chunks`/`embeddings` tables.
3. Ensure Ollama is running (`ollama list` should show `LLM_MODEL` and
   `EMBEDDING_MODEL` from `.env`, default `qwen2.5:32b-instruct-q4_K_M` and
   `mxbai-embed-large`).
4. The MCP server runs in **host mode** for these tools (`uv run --directory
   <project> python src/minimax_mcp/server.py`), not inside the `comfyui`
   container — it needs direct access to `localhost:11434` (Ollama) and
   `127.0.0.1:${KB_POSTGRES_PORT}` (Postgres).

**Data model:** one `documents` row per ingested item (`type`: video/audio/text),
each split into `chunks`, each chunk with one `embeddings` row (pgvector,
`mxbai-embed-large`, 1024 dims). `knowledge_search` combines Postgres full-text
search (`to_tsvector`/`plainto_tsquery`, GIN index) with pgvector cosine
similarity.

**LLM provider:** `LLM_PROVIDER=ollama` (default) or `openai-compatible`
(set `OPENAI_API_URL`/`OPENAI_API_KEY`, e.g. OpenRouter/Groq free tier).
Embeddings are always local via Ollama regardless of `LLM_PROVIDER`.

**Obsidian export:** optional, controlled by `VAULT_PATH` in `.env`. Leave
empty to skip — the existing vault at `~/Documents/Obsidian Vault` was flagged
as possibly unhealthy, so Postgres (not Obsidian) is the source of truth.
Failures writing the markdown copy never fail the ingest call.

**Validation:** `./tests/08_knowledge.sh` (requires Postgres + Ollama running).
```

- [ ] **Step 4: Confirm the OpenCode MCP config location and add the host-uv entry**

```bash
cat ~/.config/opencode/opencode.json 2>/dev/null | head -50
```

If a `minimax-video-factory` entry already exists using the `docker exec` (container) command, add a **second**, separate entry (or a documented alternative block, matching how the README documents 3 ways to run the MCP already) so the knowledge tools — which need host-mode access to Ollama/Postgres — are reachable:

```jsonc
"minimax-knowledge-base": {
  "type": "local",
  "command": ["uv", "run", "--directory", "$PROJECT_ROOT", "python", "src/minimax_mcp/server.py"],
  "environment": { "MCP_TRANSPORT": "stdio" },
  "description": "Knowledge base tools (Postgres + Ollama) — host mode"
}
```

Ask for confirmation before editing `~/.config/opencode/opencode.json` directly, since it's outside the project repo and may have other unrelated config in it.

- [ ] **Step 5: Run the full local validation one more time — via pytest markers (Task 0), not by hand**

```bash
cd $PROJECT_ROOT
uv run pytest -m unit -v
uv run pytest -m integration_db -v
uv run pytest -m integration_llm -v
./tests/08_knowledge.sh
uv run python scripts/generate_mcp_docs.py
```

Expected: all `pytest` runs report passing (or cleanly `SKIPPED` if a service
isn't up), `tests/08_knowledge.sh` reports `[PASS]`, and `docs/MCP_TOOLS.md`
lists 17 tools.

- [ ] **Step 6: Commit**

```bash
git add README.md AGENTS.md docs/MCP_TOOLS.md
git commit -m "docs(kb): document knowledge base setup, tools, and host-mode MCP config"
```

---

## Self-Review Notes

- **Spec coverage:** every item in the "Novas tools MCP" / "Novos arquivos" / "Schema Postgres" / "Decisões técnicas-chave" sections of the design spec maps to a task above (infra → schema → chunking → CRUD → search → LLM client → vault export → the three ingest tools → search/ask/reindex → docs). `Erros e casos de borda` from the spec are implemented inline (LLM failure ⇒ no partial write via `session.rollback()` in Task 9; DB unreachable ⇒ caught by the same try/except; vault failure ⇒ soft-fail in Task 8; empty query/base ⇒ handled in Task 11's `search`/`ask`).
- **Type/signature consistency:** `embed_fn: Callable[[str], list[float]]` is the same shape everywhere it's threaded through (`save_document`, `search_documents`, `reindex_all`, and the real `llm.embed`). `db.EMBEDDING_DIM` (Task 2) and `EMBEDDING_DIM = 1024` in the Alembic migration (Task 2) and `EMBEDDING_MODEL`/dimension in `.env.example` (Task 1) are all pinned to the verified 1024-dim output of `mxbai-embed-large`.
- **Dev tooling (explicit user priority, added as Task 0):** pytest markers (`unit`/`integration_db`/`integration_llm`) give selective, CI-friendly test execution instead of only whole-script pass/fail, without rewriting the ok()/bad()-style scripts each task already produces — `tests/test_scripts.py` wraps them. `scripts/generate_mcp_docs.py` makes the MCP tool reference (`docs/MCP_TOOLS.md`) generated from the live tool registry, so it cannot drift the way the hand-written README/AGENTS.md tables can; Task 12 regenerates it as the last step. "Robust architecture" for this MVP means: ORM-only DB access (swappable engine), a provider-abstracted LLM client (swappable backend), transactional writes (Task 9's `session.rollback()` on failure), and every module (`llm.py`/`db.py`/`vault.py`/`knowledge.py`) independently testable — see `docs/ROADMAP.md` for what "robust" additionally means once this becomes a multi-user product (auth, hosted Postgres, cost model), which is explicitly out of scope here.
- **Deferred to Post-MVP** (per spec, not part of this plan): Karakeep→Postgres ingestion, a web UI/site, reranking/dedup/MOCs, and the "product for other people" phase — see the separate roadmap document.
