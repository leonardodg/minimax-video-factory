# Instagram Saved → Knowledge Base Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enumerate all of the user's Instagram saved posts (via `IG_SESSIONID`), enqueue them on RabbitMQ, and have a background daemon worker (`ig-worker`, same Docker stack as the H3 container) download → transcribe (video) or describe (image via Ollama vision) → document each one in the Postgres knowledge base, skipping duplicates by `ig_pk`.

**Architecture:** Three new modules under `minimax_mcp/` — `ig_queue.py` (thin RabbitMQ abstraction: declare/publish/parse/retry/DLQ), `ig_sync.py` (instagrapi enumeration → message dicts → publish), `ig_worker.py` (daemon consumer; per-item logic in pure, injectable functions). Data model gains an `ig_pk` column on `documents` (migration `0002`). The MCP server exposes 5 new fail-soft tools; the compose file gains `rabbitmq` + `ig-worker` services.

**Tech Stack:** Python ≥ 3.10, `instagrapi>=2.1.0`, `pika>=1.3.2`, RabbitMQ `3-management`, Postgres pgvector, Ollama (`OLLAMA_VISION_MODEL`, default `qwen2.5vl:7b`), yt-dlp, faster-whisper, FastMCP 3.x, Docker Compose v2.

## Global Constraints

- All work happens in the **worktree** `.worktrees/igsync` (branch `feat/ig-saved-sync`).
- RabbitMQ: queue `ig.saved` durable, DLQ `ig.saved.dead`, header `attempts` starts 0, `MAX_ATTEMPTS = 3` → beyond that route to DLQ. Corrupted message → DLQ directly (no requeue loop).
- Dedup: key is `ig_pk`; before processing, worker checks the KB by `ig_pk` (fallback `source_url`) → if present, `ack` without processing (no GPU/LLM spent).
- Message contract keys (must all be present or message is "corrupted"): `ig_pk`, `media_type` (`video`|`image`|`carousel`), `url`, `title`, `owner_username`, `collection_name`, `status`.
- `IG_SESSIONID` is required and comes from the Chrome cookies (`sessionid`), never a password; never log it, never commit it (`.env` is gitignored).
- instagrapi must use `delay_range` (e.g. `[1, 3]`) to avoid Instagram checkpoint/rate-limit.
- Worker runs in the same image/stack as H3: `--gpus all`, compose network (reaches `postgres:5432`, `rabbitmq:5672`), `extra_hosts: host.docker.internal:host-gateway` for host Ollama. `IG_WORKER_CONCURRENCY` default `1` (shares VRAM with H3), prefetch `1`.
- `IG_DELETE_AFTER_INGEST` default `true`: worker deletes the downloaded media file after a successful KB ingest.
- Every MCP tool is fail-soft: backend errors return `{"ok": False, "error": ...}`, never raise.
- Rebuild/restart of the Docker stack is only allowed when the ComfyUI render queue is **empty** — check via the `queue_status` MCP tool (or `curl -s http://127.0.0.1:8188/queue`) first.
- Every new `@mcp.tool()` follows the 9-step checklist in `docs/dev/extending.md`: domain fn in module (unit-testable), `@mcp.tool()` + `Field(description=…)` per param, command name in `scripts/command_docs/catalog.py`, optional `overrides.py`, run `scripts/generate_commands.py` and commit generated `.md`, run `scripts/generate_mcp_docs.py`, add to `tests/unit_registry.py`, bump count in `tests/unit_commands.py`, add README table row. Six of these are enforced by tests.
- Docs: update `docs/KNOWLEDGE_BASE.md` (IG sync section), `.env.example` (new vars), and `uv run mkdocs build --strict` must pass.
- `tests/unit_privacy.py` forbids committed absolute home-directory paths.
- New runtime deps (`pika`, `instagrapi`) must be in `pyproject.toml`; after the code lands, rebuild the container (only with an empty render queue) and verify `tests/09_container_deps.sh`.

---

### Task 1: `ig_queue.py` — RabbitMQ abstraction (queue/DLQ/parse/retry/status)

**Files:**
- Modify: `pyproject.toml` (add `pika>=1.3.2`)
- Create: `src/minimax_mcp/ig_queue.py`
- Test: `tests/unit_ig_queue.py`
- Modify: `tests/test_scripts.py` (add pytest entry)

**Interfaces:**
- Produces (consumed by Tasks 3, 5, 6):
  - `ig_queue.QUEUE` (`ig.saved`), `ig_queue.DLQ` (`ig.saved.dead`), `ig_queue.CONTROL_QUEUE` (`ig.worker.command`), `ig_queue.MAX_ATTEMPTS` (`3`)
  - `declare(channel) -> None`
  - `publish(channel, message: dict) -> None`
  - `parse_message(body: bytes) -> dict` → `{"ok": True, "message": {...}}` or `{"ok": False, "error": ...}`
- `attempts_of(properties) -> int`
- `handle_failure(channel, properties, body: bytes) -> str` → `"dead"` or `"requeue"`
- `dead_letter(channel, properties, body: bytes) -> None` → publish straight to the DLQ (corrupted messages; no attempts bump, no requeue)
- `queue_status(channel) -> dict`
  - `connect() -> BlockingConnection`, `close(connection) -> None`

- [ ] **Step 1: Add pika to `pyproject.toml`**

In `pyproject.toml`, add `"pika>=1.3.2"` to the `dependencies` list (alphabetical, after `"pgvector>=0.3.2"`).

- [ ] **Step 2: Write the failing unit test** `tests/unit_ig_queue.py`

```python
#!/usr/bin/env python3
"""Unit tests for ig_queue.py — no real RabbitMQ; a fake channel records calls."""
from __future__ import annotations

import json
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


class FakeMethod:
    message_count = 0
    consumer_count = 0


class FakeDeclareResult:
    method = FakeMethod()


class FakeProperties:
    def __init__(self, headers=None):
        self.headers = headers or {}


class FakeChannel:
    def __init__(self):
        self.declared: list[tuple] = []
        self.published: list[tuple] = []
        self.acks: list[int] = []

    def queue_declare(self, queue, durable=False, arguments=None, passive=False):
        self.declared.append((queue, durable, arguments, passive))
        return FakeDeclareResult()

    def basic_publish(self, exchange="", routing_key="", body=b"", properties=None):
        h = properties.headers if properties is not None else None
        self.published.append((routing_key, body, h))

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)


from minimax_mcp import ig_queue


print("== unit_ig_queue: parse_message ==")
good = ig_queue.parse_message(
    json.dumps({
        "ig_pk": "123", "media_type": "video", "url": "https://instagram.com/p/123",
        "title": "t", "owner_username": "u", "collection_name": None, "status": "queued",
    }).encode()
)
if good.get("ok") and good["message"]["ig_pk"] == "123":
    ok("parse_message accepts a valid message")
else:
    bad(f"parse_message(valid) = {good!r}")

if not ig_queue.parse_message(b"not json").get("ok"):
    ok("parse_message rejects invalid JSON")
else:
    bad("parse_message accepted invalid JSON")

if not ig_queue.parse_message(b'{"ig_pk": "1"}').get("ok"):
    ok("parse_message rejects a message missing required keys")
else:
    bad("parse_message accepted a truncated message")

print("== unit_ig_queue: declare ==")
ch = FakeChannel()
ig_queue.declare(ch)
names = {d[0] for d in ch.declared}
if {ig_queue.QUEUE, ig_queue.DLQ, ig_queue.CONTROL_QUEUE} <= names:
    ok("declare creates queue, DLQ and control queue")
else:
    bad(f"declare created: {names}")

work_decl = [d for d in ch.declared if d[0] == ig_queue.QUEUE][0]
if work_decl[1] is True and work_decl[2].get("x-dead-letter-routing-key") == ig_queue.DLQ:
    ok("ig.saved is durable and dead-letters to the DLQ")
else:
    bad(f"ig.saved declare args = {work_decl!r}")

print("== unit_ig_queue: publish ==")
ch = FakeChannel()
ig_queue.publish(ch, {"ig_pk": "1", "media_type": "image", "url": "x"})
rk, body, headers = ch.published[0]
if rk == ig_queue.QUEUE and json.loads(body)["ig_pk"] == "1" and headers.get("attempts") == 0:
    ok("publish sends to ig.saved with attempts=0 header")
else:
    bad(f"publish = {ch.published!r}")

print("== unit_ig_queue: attempts_of ==")
if ig_queue.attempts_of(FakeProperties({"attempts": 2})) == 2:
    ok("attempts_of reads the header")
else:
    bad("attempts_of mis-read the header")
if ig_queue.attempts_of(FakeProperties({})) == 0 and ig_queue.attempts_of(FakeProperties(None)) == 0:
    ok("attempts_of defaults to 0")
else:
    bad("attempts_of default != 0")

print("== unit_ig_queue: handle_failure ==")
body = b'{"ig_pk": "1", "media_type": "video", "url": "x"}'

ch = FakeChannel()
r = ig_queue.handle_failure(ch, FakeProperties({"attempts": 0}), body)
if r == "requeue" and ch.published and ch.published[0][0] == ig_queue.QUEUE:
    h = ch.published[0][2]
    if h.get("attempts") == 1:
        ok("attempt 0 -> requeue with attempts=1")
    else:
        bad(f"requeue header attempts = {h}")
else:
    bad(f"handle_failure(attempts=0) = {r}, published={ch.published}")

ch = FakeChannel()
r = ig_queue.handle_failure(ch, FakeProperties({"attempts": 2}), body)
if r == "dead" and ch.published and ch.published[0][0] == ig_queue.DLQ:
    ok("attempts == MAX-1 -> dead-lettered to the DLQ")
else:
    bad(f"handle_failure(attempts=2) = {r}, published={ch.published}")

print("== unit_ig_queue: dead_letter ==")
ch = FakeChannel()
ig_queue.dead_letter(ch, FakeProperties({"attempts": 2}), body)
if ch.published and ch.published[0][0] == ig_queue.DLQ:
    ok("dead_letter publishes straight to the DLQ (no requeue)")
else:
    bad(f"dead_letter = {ch.published!r}")

print("== unit_ig_queue: queue_status ==")
ch = FakeChannel()
status = ig_queue.queue_status(ch)
if status.get("ok") and {"queue", "ready", "dead", "consumers"} <= set(status):
    ok("queue_status returns the expected keys")
else:
    bad(f"queue_status = {status!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project . python tests/unit_ig_queue.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'minimax_mcp.ig_queue'`

- [ ] **Step 4: Write `src/minimax_mcp/ig_queue.py`**

```python
"""RabbitMQ abstraction for the Instagram saved-posts sync.

Declares the durable work queue (ig.saved) with a dead-letter queue
(ig.saved.dead), publishes messages, parses+validates them, and implements the
attempts/DLQ retry policy. No business logic here — unit-tested with a fake
channel (see tests/unit_ig_queue.py).
"""
from __future__ import annotations

import json
import os
from typing import Any

import pika

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE = os.environ.get("RABBITMQ_QUEUE", "ig.saved")
DLQ = f"{QUEUE}.dead"
CONTROL_QUEUE = "ig.worker.command"
MAX_ATTEMPTS = int(os.environ.get("IG_MAX_ATTEMPTS", "3"))

REQUIRED_KEYS = {"ig_pk", "media_type", "url", "title", "owner_username", "collection_name", "status"}


def connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))


def close(connection: pika.BlockingConnection | None) -> None:
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass


def declare(channel: Any) -> None:
    """Declare work queue (durable, dead-letters to DLQ), DLQ, control queue."""
    channel.queue_declare(
        queue=QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": DLQ},
    )
    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_declare(queue=CONTROL_QUEUE, durable=False)


def publish(channel: Any, message: dict) -> None:
    """Publish a durable message to ig.saved with attempts=0."""
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": 0}),
    )


def parse_message(body: bytes) -> dict:
    """Validate a queue body against the message contract.

    Returns {"ok": True, "message": {...}} or {"ok": False, "error": ...}.
    """
    try:
        msg = json.loads(body)
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid json"}
    if not isinstance(msg, dict):
        return {"ok": False, "error": "message is not an object"}
    missing = sorted(REQUIRED_KEYS - set(msg))
    if missing:
        return {"ok": False, "error": f"missing keys {missing}"}
    return {"ok": True, "message": msg}


def attempts_of(properties: Any) -> int:
    """Read the attempts header, defaulting to 0."""
    headers = getattr(properties, "headers", None) or {}
    try:
        return int(headers.get("attempts", 0))
    except (TypeError, ValueError):
        return 0


def handle_failure(channel: Any, properties: Any, body: bytes) -> str:
    """Retry policy for a processing failure.

    Re-publishes to ig.saved with attempts+1 while under MAX_ATTEMPTS, else
    re-publishes to the DLQ. Returns "requeue" or "dead". The caller acks the
    original delivery after this (the copy is the retry).
    """
    attempts = attempts_of(properties)
    if attempts + 1 >= MAX_ATTEMPTS:
        channel.basic_publish(
            exchange="",
            routing_key=DLQ,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts + 1}),
        )
        return "dead"
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts + 1}),
    )
    return "requeue"


def dead_letter(channel: Any, properties: Any, body: bytes) -> None:
    """Publish a message straight to the DLQ (corrupted bodies only).

    Unlike handle_failure this never bumps attempts and never requeues —
    a corrupted message goes to the DLQ exactly once.
    """
    channel.basic_publish(
        exchange="",
        routing_key=DLQ,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts_of(properties) + 1}),
    )


def queue_status(channel: Any) -> dict:
    """Passive-declare ig.saved + DLQ and report message/consumer counts."""
    work = channel.queue_declare(queue=QUEUE, durable=True, passive=True)
    dead = channel.queue_declare(queue=DLQ, durable=True, passive=True)
    return {
        "ok": True,
        "queue": QUEUE,
        "ready": int(work.method.message_count),
        "dead": int(dead.method.message_count),
        "consumers": int(work.method.consumer_count),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project . python tests/unit_ig_queue.py`
Expected: `PASS`

- [ ] **Step 6: Add the pytest entry in `tests/test_scripts.py`**

Add near the other `test_unit_*` functions:

```python
@pytest.mark.unit
def test_unit_ig_queue():
    result = _run_script("unit_ig_queue.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 7: Run the unit suite**

Run: `uv run --project . pytest -m unit`
Expected: all pass (previous tests unchanged).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/minimax_mcp/ig_queue.py tests/unit_ig_queue.py tests/test_scripts.py
git commit -m "feat(ig): RabbitMQ abstraction for the Instagram saved-posts queue"
```

---

### Task 2: `ig_pk` column + dedup helpers + migration `0002`

**Files:**
- Modify: `src/minimax_mcp/db.py` (Document model + `save_document` + helpers)
- Modify: `src/minimax_mcp/knowledge.py` (`ingest_text` gains `ig_pk` + `extra_tags`)
- Create: `alembic/versions/0002_ig_pk.py`
- Modify: `tests/unit_db.py` (assert the model column exists)
- Modify: `tests/integration_knowledge_db.py` (exercise `document_exists`/`list_ig_pks` with a fake `ig_pk`)

**Interfaces:**
- Consumes: `db.get_session()` (existing).
- Produces (consumed by Tasks 3, 5, 6):
  - `db.Document.ig_pk` (nullable `String(64)`)
  - `db.save_document(..., ig_pk: str | None = None)`
  - `db.document_exists(session, *, ig_pk: str | None = None, source_url: str | None = None) -> bool`
  - `db.list_ig_pks(session) -> set[str]`
  - `knowledge.ingest_text(text, *, ..., ig_pk: str | None = None, extra_tags: list[str] | None = None)` (unchanged return shape)

- [ ] **Step 1: Write the failing unit assertion** in `tests/unit_db.py`

Append at the end (before the final `FAIL`/exit block):

```python
print("== unit_db: ig_pk column on Document ==")
from minimax_mcp.db import Document

cols = {c.name for c in Document.__table__.columns}
if "ig_pk" in cols:
    ok("Document model has an ig_pk column")
else:
    bad("Document model is missing ig_pk")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . python tests/unit_db.py`
Expected: FAIL with `[BAD] Document model is missing ig_pk`

- [ ] **Step 3: Update the `Document` model and `save_document`** in `src/minimax_mcp/db.py`

Add the column after `source_url` (line ~44):

```python
    ig_pk: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

Add the `ig_pk` keyword to `save_document` (default `None`), pass it to `Document(...)`, and add the two dedup helpers after `delete_documents`:

```python
def document_exists(
    session: Session,
    *,
    ig_pk: str | None = None,
    source_url: str | None = None,
) -> bool:
    """True if a document with that ig_pk (or source_url) already exists."""
    if ig_pk is not None:
        stmt = select(Document.id).where(Document.ig_pk == ig_pk)
    elif source_url is not None:
        stmt = select(Document.id).where(Document.source_url == source_url)
    else:
        return False
    return session.execute(stmt.limit(1)).first() is not None


def list_ig_pks(session: Session) -> set[str]:
    """Every non-null ig_pk currently stored (used to skip re-publishing)."""
    rows = session.execute(
        select(Document.ig_pk).where(Document.ig_pk.isnot(None))
    ).all()
    return {r[0] for r in rows}
```

- [ ] **Step 4: Update `knowledge.ingest_text`** in `src/minimax_mcp/knowledge.py`

Add `ig_pk` and `extra_tags` keyword params; merge `extra_tags` into the LLM tags and pass `ig_pk` through:

```python
def ingest_text(
    text: str,
    *,
    source_url: str | None = None,
    title: str | None = None,
    platform: str = "manual",
    doc_type: str = "text",
    language: str = "pt",
    ig_pk: str | None = None,
    extra_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize+document `text` via the LLM and store it in the knowledge base."""
    if not text or not text.strip():
        return {"ok": False, "error": "empty text"}

    gen = llm.generate_structured(text)
    if not gen.get("ok"):
        return {"ok": False, "stage": "llm", "error": gen.get("error")}

    tags = list(dict.fromkeys([t for t in (gen.get("tags") or []) + (extra_tags or []) if t]))

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
            tags=tags,
            raw_file_path=None,
            llm_provider=gen.get("provider"),
            llm_model=gen.get("model"),
            embed_fn=llm.embed,
            embedding_model=llm.EMBEDDING_MODEL,
            ig_pk=ig_pk,
        )
```

- [ ] **Step 5: Write the migration** `alembic/versions/0002_ig_pk.py`

```python
"""add ig_pk to documents for Instagram saved-posts dedup

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ig_pk", sa.String(64), nullable=True))
    op.create_index("ix_documents_ig_pk", "documents", ["ig_pk"])


def downgrade() -> None:
    op.drop_index("ix_documents_ig_pk", table_name="documents")
    op.drop_column("documents", "ig_pk")
```

- [ ] **Step 6: Run tests — unit**

Run: `uv run --project . python tests/unit_db.py`
Expected: PASS

Run: `uv run --project . pytest -m unit`
Expected: all pass.

- [ ] **Step 7: Add integration assertions** to `tests/integration_knowledge_db.py`

Inside the existing `save_document` test block, pass `ig_pk="12345"` to `save_document`. After the `reindex_all` block, add:

```python
print("== integration_knowledge_db: ig_pk dedup helpers ==")
session = db.get_session()
try:
    if db.document_exists(session, ig_pk="12345"):
        ok("document_exists(ig_pk) finds the saved document")
    else:
        bad("document_exists(ig_pk) did not find the saved document")

    pks = db.list_ig_pks(session)
    if "12345" in pks:
        ok("list_ig_pks returns the stored ig_pk")
    else:
        bad(f"list_ig_pks = {pks!r}")
finally:
    session.close()
```

- [ ] **Step 8: Apply the migration and run the integration test**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project . alembic upgrade head
uv run --project . python tests/integration_knowledge_db.py
```
Expected: `PASS` (Postgres is up at `KB_POSTGRES_PORT`).

- [ ] **Step 9: Commit**

```bash
git add src/minimax_mcp/db.py src/minimax_mcp/knowledge.py alembic/versions/0002_ig_pk.py tests/unit_db.py tests/integration_knowledge_db.py
git commit -m "feat(ig): add ig_pk dedup column to documents (migration 0002)"
```

---

### Task 3: `ig_sync.py` — instagrapi enumeration → messages

**Files:**
- Modify: `pyproject.toml` (add `instagrapi>=2.1.0`)
- Create: `src/minimax_mcp/ig_sync.py`
- Test: `tests/unit_ig_sync.py`
- Modify: `tests/test_scripts.py` (pytest entry)

**Interfaces:**
- Consumes: `ig_queue.publish`, `ig_queue.connect`/`close`, `db.list_ig_pks`.
- Produces (consumed by Task 6 `ig_sync_saved` tool):
  - `ig_sync.MEDIA_TYPES` (`{1: "image", 2: "video", 8: "carousel"}`)
  - `ig_sync.to_messages(media_items) -> list[dict]`
  - `ig_sync.split_new(messages, existing_pks: set[str]) -> tuple[list[dict], int]` → `(new_messages, skipped_count)`
  - `ig_sync.sync_saved_posts(client, *, existing_pks, publish_fn) -> dict` → `{"ok", "published", "skipped_existing", "total"}`
  - `ig_sync.make_client() -> instagrapi.Client`
  - `ig_sync.SESSIONID_MISSING = "IG_SESSIONID not configured"` (constant, reused by Task 6)

- [ ] **Step 1: Add instagrapi to `pyproject.toml`**

Add `"instagrapi>=2.1.0"` to `dependencies` (alphabetical, after `"httpx>=0.28.1"`).

- [ ] **Step 2: Write the failing unit test** `tests/unit_ig_sync.py`

```python
#!/usr/bin/env python3
"""Unit tests for ig_sync.py — duck-typed Media objects, injected client."""
from __future__ import annotations

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


from minimax_mcp import ig_sync


class User:
    username = "anajcodes"


class Media:
    def __init__(self, pk, media_type, caption="", user=None):
        self.pk = pk
        self.media_type = media_type
        self.caption_text = caption
        self.user = user or User()


print("== unit_ig_sync: to_messages ==")
items = [
    Media("1001", 2, "Reel de teste\nsegunda linha"),
    Media("1002", 1, "Foto"),
    Media("1003", 8),
    Media(None, 2),
]
msgs = ig_sync.to_messages(items)

if len(msgs) == 3:
    ok("to_messages keeps video/image/carousel, drops pk-less")
else:
    bad(f"to_messages returned {len(msgs)} messages")

m0 = msgs[0]
if (
    m0["ig_pk"] == "1001"
    and m0["media_type"] == "video"
    and m0["url"] == "https://www.instagram.com/p/1001/"
    and m0["owner_username"] == "anajcodes"
    and m0["title"] == "Reel de teste"
    and m0["collection_name"] is None
    and m0["status"] == "queued"
):
    ok("to_messages maps video Media to the message contract")
else:
    bad(f"video message = {m0!r}")

if msgs[1]["media_type"] == "image" and msgs[2]["media_type"] == "carousel":
    ok("image and carousel media_types map correctly")
else:
    bad(f"media types = {[m['media_type'] for m in msgs]}")

print("== unit_ig_sync: split_new ==")
new, skipped = ig_sync.split_new(msgs, existing_pks={"1001"})
if len(new) == 2 and skipped == 1:
    ok("split_new drops existing ig_pks")
else:
    bad(f"split_new = new={len(new)} skipped={skipped}")

print("== unit_ig_sync: sync_saved_posts ==")
published = []


def fake_publish(msg):
    published.append(msg)


class FakeClient:
    def saved_posts(self):
        return items


result = ig_sync.sync_saved_posts(FakeClient(), existing_pks={"1001"}, publish_fn=fake_publish)
if (
    result["ok"]
    and result["published"] == 2
    and result["skipped_existing"] == 1
    and result["total"] == 3
    and len(published) == 2
):
    ok("sync_saved_posts publishes only new posts and reports counts")
else:
    bad(f"sync_saved_posts = {result!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project . python tests/unit_ig_sync.py`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write `src/minimax_mcp/ig_sync.py`**

```python
"""Enumerate the user's Instagram saved posts and publish them to the queue.

instagrapi is used only here (enumeration) — the worker downloads by pk via
yt-dlp, so IG_SESSIONID is only needed for enumeration. Business logic
(to_messages/split_new) is pure and unit-tested with duck-typed Media objects.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from minimax_mcp import db, ig_queue

logger = logging.getLogger(__name__)

IG_SESSIONID = os.environ.get("IG_SESSIONID", "")
SESSIONID_MISSING = "IG_SESSIONID not configured"

# instagrapi MediaType values: 1 = image, 2 = video, 8 = album/carousel
MEDIA_TYPES = {1: "image", 2: "video", 8: "carousel"}


def make_client() -> Any:
    """Build an authenticated instagrapi Client from IG_SESSIONID."""
    from instagrapi import Client

    client = Client()
    client.delay_range = [1, 3]  # avoid Instagram checkpoint/rate-limit
    client.set_sessionid(IG_SESSIONID)
    return client


def to_messages(media_items: list[Any]) -> list[dict]:
    """Map instagrapi Media-like objects to queue message dicts.

    Duck-typed on .pk/.media_type/.caption_text/.user.username so tests can
    pass simple stand-ins. Skips items with no pk or unknown media_type.
    """
    messages: list[dict] = []
    for m in media_items:
        pk = getattr(m, "pk", None)
        media_type = MEDIA_TYPES.get(getattr(m, "media_type", None))
        if not pk or not media_type:
            continue
        caption = (getattr(m, "caption_text", "") or "").strip()
        title = caption.splitlines()[0][:80] if caption else "sem título"
        user = getattr(m, "user", None)
        messages.append({
            "ig_pk": str(pk),
            "media_type": media_type,
            "url": f"https://www.instagram.com/p/{pk}/",
            "title": title,
            "owner_username": getattr(user, "username", None),
            "collection_name": getattr(m, "collection_name", None),
            "status": "queued",
        })
    return messages


def split_new(messages: list[dict], existing_pks: set[str]) -> tuple[list[dict], int]:
    """Partition messages into not-yet-ingested vs already-known ig_pks."""
    new: list[dict] = []
    skipped = 0
    for msg in messages:
        if msg["ig_pk"] in existing_pks:
            skipped += 1
        else:
            new.append(msg)
    return new, skipped


def sync_saved_posts(
    client: Any,
    *,
    existing_pks: set[str],
    publish_fn: Callable[[dict], None],
) -> dict:
    """Enumerate saved posts, filter to new ig_pks, publish each. Returns counts.

    `publish_fn` is injected so the tool can wire it to ig_queue.publish with a
    real channel while tests pass a recorder.
    """
    posts = list(client.saved_posts())
    messages = to_messages(posts)
    new, skipped = split_new(messages, existing_pks)
    for msg in new:
        publish_fn(msg)
    return {
        "ok": True,
        "published": len(new),
        "skipped_existing": skipped,
        "total": len(messages),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project . python tests/unit_ig_sync.py`
Expected: `PASS`

- [ ] **Step 6: Add the pytest entry** in `tests/test_scripts.py`

```python
@pytest.mark.unit
def test_unit_ig_sync():
    result = _run_script("unit_ig_sync.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 7: Run the unit suite**

Run: `uv run --project . pytest -m unit`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/minimax_mcp/ig_sync.py tests/unit_ig_sync.py tests/test_scripts.py
git commit -m "feat(ig): instagrapi enumeration + message publishing for saved posts"
```

---

### Task 4: Ollama vision description (`llm.describe_image`)

**Files:**
- Modify: `src/minimax_mcp/llm.py` (add `VISION_MODEL`, `build_vision_prompt`, `describe_image`)
- Modify: `tests/unit_knowledge.py` (test `build_vision_prompt`)
- Modify: `tests/integration_knowledge_llm.py` (vision describe against real Ollama, skippable)

**Interfaces:**
- Consumes: `llm.OLLAMA_URL`, `llm.LLM_TIMEOUT` (existing).
- Produces (consumed by Task 5 image path):
  - `llm.VISION_MODEL` (`OLLAMA_VISION_MODEL`, default `qwen2.5vl:7b`)
  - `llm.build_vision_prompt() -> str`
  - `llm.describe_image(image_path: str, *, model: str | None = None) -> dict` → `{"ok": True, "text": ...}` or `{"ok": False, "error": ...}`

- [ ] **Step 1: Write the failing unit test** (append to `tests/unit_knowledge.py`)

```python
print("== unit_knowledge: llm.build_vision_prompt ==")
prompt = llm.build_vision_prompt()
if "portugu" in prompt and "imagem" in prompt:
    ok("build_vision_prompt asks for a PT-BR image description")
else:
    bad(f"build_vision_prompt = {prompt[:120]!r}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . python tests/unit_knowledge.py`
Expected: FAIL with `AttributeError: ... build_vision_prompt`

- [ ] **Step 3: Add the vision functions to `src/minimax_mcp/llm.py`**

Add imports `base64` and `Path` at the top, a module constant, and the functions at the end of the module:

```python
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")


def build_vision_prompt() -> str:
    return (
        "Descreva esta imagem em português, com detalhes: o que aparece, "
        "cores, composição, texto visível e o contexto. Descreva apenas o "
        "que está na imagem; não invente informações."
    )


def describe_image(image_path: str, *, model: str | None = None) -> dict:
    """Describe an image with a local vision LLM via Ollama /api/generate."""
    model = model or VISION_MODEL
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    except OSError as e:
        return {"ok": False, "error": f"read image failed: {e}"}

    payload = {
        "model": model,
        "prompt": build_vision_prompt(),
        "images": [b64],
        "stream": False,
        "options": {"num_predict": 512, "temperature": 0.2},
    }
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=LLM_TIMEOUT
        )
        resp.raise_for_status()
        text = (resp.json().get("response") or "").strip()
    except Exception as e:
        return {"ok": False, "error": f"vision failed: {e}"}
    if not text:
        return {"ok": False, "error": "vision returned empty text"}
    return {"ok": True, "text": text}
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `uv run --project . python tests/unit_knowledge.py`
Expected: PASS

- [ ] **Step 5: Add the integration test** (append to `tests/integration_knowledge_llm.py`)

```python
print("== integration_knowledge_llm: vision describe (skippable) ==")
import shutil
from pathlib import Path

VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
have = os.popen(f"ollama list 2>/dev/null | awk '{{print $1}}'").read()
if VISION_MODEL.split(":")[0] not in have:
    print("  [SKIP] vision model not pulled; run: ollama pull qwen2.5vl:7b")
else:
    img = Path(tempfile.mkdtemp()) / "pixel.png"
    # 4x4 solid-color PNG (a real file the vision model can read)
    import struct, zlib

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
```

Note: the test uses the already-imported `llm`/`ok`/`bad`/`tempfile`/`os` from the top of `integration_knowledge_llm.py` — reuse whatever the file already imports; adjust the header imports if `tempfile`/`os` are already present.

- [ ] **Step 6: Run the integration test**

Run: `uv run --project . python tests/integration_knowledge_llm.py`
Expected: `[SKIP] vision model not pulled` (qwen2.5vl still downloading) or PASS. Both are acceptable — the test must not fail while the model is absent.

- [ ] **Step 7: Commit**

```bash
git add src/minimax_mcp/llm.py tests/unit_knowledge.py tests/integration_knowledge_llm.py
git commit -m "feat(ig): Ollama vision image description for photo ingests"
```

---

### Task 5: `ig_worker.py` — daemon consumer

**Files:**
- Create: `src/minimax_mcp/ig_worker.py`
- Test: `tests/unit_ig_worker.py`
- Modify: `tests/test_scripts.py` (pytest entry)

**Interfaces:**
- Consumes: `ig_queue` (declare/parse/handle_failure/attempts_of), `db.document_exists`, `knowledge.ingest_text`, `llm.describe_image`, `AudioTranscriber`, `VideoDownloader`, `IG_DOWNLOADS_DIR`/`IG_DELETE_AFTER_INGEST` env.
- Produces (consumed by Task 6 `ig_worker_start/stop` control loop, Task 8 compose command `python -m minimax_mcp.ig_worker`):
  - `ig_worker.classify_file(filepath: str) -> str` → `"video"` | `"image"`
  - `ig_worker.process_message(message, *, download, transcribe, describe, ingest) -> dict` → `{"status": "done", "document_id", "kind", "filepath"}` | `{"status": "duplicate"}` | `{"status": "error", "error": ...}`
  - `ig_worker.apply_command(state: dict, command: str) -> str` → `"paused"` | `"resumed"`
  - `ig_worker.run() -> None` (daemon main)

- [ ] **Step 1: Write the failing unit test** `tests/unit_ig_worker.py`

```python
#!/usr/bin/env python3
"""Unit tests for ig_worker.py — injected download/transcribe/describe/ingest."""
from __future__ import annotations

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


from minimax_mcp import ig_worker

MESSAGE = {
    "ig_pk": "1001", "media_type": "video",
    "url": "https://www.instagram.com/p/1001/", "title": "t",
    "owner_username": "u", "collection_name": None, "status": "queued",
}

print("== unit_ig_worker: classify_file ==")
if ig_worker.classify_file("x.mp4") == "video" and ig_worker.classify_file("x.jpg") == "image":
    ok("classify_file splits video/image by extension")
else:
    bad(f"classify_file = {ig_worker.classify_file('x.mp4')}/{ig_worker.classify_file('x.jpg')}")

print("== unit_ig_worker: process_message (video) ==")


def dl_video(msg):
    assert msg == MESSAGE
    return {"ok": True, "filepath": "/tmp/x.mp4"}


def tr(path):
    assert path == "/tmp/x.mp4"
    return {"ok": True, "text": "transcrito", "language": "pt"}


def ingest_ok(text, **kw):
    assert text == "transcrito"
    assert kw["doc_type"] == "video" and kw["ig_pk"] == "1001"
    return {"ok": True, "document_id": 42}


res = ig_worker.process_message(
    MESSAGE, download=dl_video, transcribe=tr, describe=None, ingest=ingest_ok
)
if res["status"] == "done" and res["document_id"] == 42 and res["kind"] == "video":
    ok("video message -> transcribe -> ingest -> done")
else:
    bad(f"video process = {res!r}")

print("== unit_ig_worker: process_message (image via describe) ==")


def dl_img(msg):
    return {"ok": True, "filepath": "/tmp/x.jpg"}


def describe(path):
    assert path == "/tmp/x.jpg"
    return {"ok": True, "text": "descrição da foto"}


def ingest_img(text, **kw):
    assert text == "descrição da foto"
    assert kw["doc_type"] == "image"
    return {"ok": True, "document_id": 43}


res = ig_worker.process_message(
    MESSAGE, download=dl_img, transcribe=None, describe=describe, ingest=ingest_img
)
if res["status"] == "done" and res["kind"] == "image":
    ok("image message -> describe -> ingest -> done")
else:
    bad(f"image process = {res!r}")

print("== unit_ig_worker: process_message (carousel -> first item) ==")


def dl_carousel(msg):
    assert msg["media_type"] == "carousel"
    return {"ok": True, "filepath": "/tmp/first.mp4"}


res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_carousel, transcribe=tr, describe=describe, ingest=ingest_ok,
)
if res["status"] == "done" and res["kind"] == "video":
    ok("carousel message is processed via its first downloaded item")
else:
    bad(f"carousel process = {res!r}")

print("== unit_ig_worker: process_message (failures) ==")
if ig_worker.process_message(MESSAGE, download=lambda m: {"ok": False, "error": "x"},
                             transcribe=tr, describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("download failure -> error status")
else:
    bad("download failure not reported")

if ig_worker.process_message(MESSAGE, download=dl_video,
                             transcribe=lambda p: {"ok": False, "error": "t"},
                             describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("transcribe failure -> error status")
else:
    bad("transcribe failure not reported")

print("== unit_ig_worker: apply_command ==")
state = {"paused": True}
if ig_worker.apply_command(state, "start") == "resumed" and state["paused"] is False:
    ok("start resumes a paused worker")
else:
    bad(f"apply_command(start) = {ig_worker.apply_command(state, 'start')}")
if ig_worker.apply_command(state, "stop") == "paused" and state["paused"] is True:
    ok("stop pauses a running worker")
else:
    bad("apply_command(stop) did not pause")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . python tests/unit_ig_worker.py`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/minimax_mcp/ig_worker.py`**

```python
"""Background daemon consumer for the Instagram saved-posts queue.

Consumes ig.saved one message at a time (prefetch=1, IG_WORKER_CONCURRENCY=1
by default — Whisper/vision share the VRAM with the H3 renderer), downloads the
media with yt-dlp, transcribes (video) or describes (image) it, ingests it into
the knowledge base, optionally deletes the downloaded file, and acks. Failures
go through ig_queue.handle_failure (attempts -> DLQ).

The per-item logic (process_message/classify_file/apply_command) is pure and
injected with download/transcribe/describe/ingest callables so it can be unit
tested without RabbitMQ, GPU or network.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from minimax_mcp import db, ig_queue, knowledge, llm

logger = logging.getLogger(__name__)

IG_DOWNLOADS_DIR = Path(os.environ.get("IG_DOWNLOADS_DIR", "downloads/ig"))
IG_DELETE_AFTER_INGEST = os.environ.get("IG_DELETE_AFTER_INGEST", "true").lower() in (
    "1", "true", "yes",
)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def classify_file(filepath: str) -> str:
    return "video" if Path(filepath).suffix.lower() in VIDEO_EXTS else "image"


def process_message(
    message: dict,
    *,
    download: Callable[[dict], dict],
    transcribe: Callable[[str], dict] | None,
    describe: Callable[[str], dict] | None,
    ingest: Callable[[str], dict],
) -> dict:
    """Download -> transcribe/describe -> ingest. Pure; all IO injected."""
    if not message:
        return {"status": "error", "error": "empty message"}

    dl = download(message)
    if not dl.get("ok"):
        return {"status": "error", "error": dl.get("error", "download failed")}
    filepath = dl["filepath"]

    kind = classify_file(filepath)
    if kind == "video":
        if transcribe is None:
            return {"status": "error", "error": "no transcribe provided for video"}
        tr = transcribe(filepath)
        if not tr.get("ok"):
            return {"status": "error", "error": tr.get("error", "transcribe failed")}
        text, lang = tr["text"], tr.get("language", "pt")
        doc_type = "video"
    else:
        if describe is None:
            return {"status": "error", "error": "no describe provided for image"}
        de = describe(filepath)
        if not de.get("ok"):
            return {"status": "error", "error": de.get("error", "describe failed")}
        text, lang = de["text"], "pt"
        doc_type = "image"

    extra_tags = [message["collection_name"]] if message.get("collection_name") else None
    ing = ingest(
        text,
        source_url=message.get("url"),
        title=message.get("title"),
        platform="instagram",
        doc_type=doc_type,
        language=lang,
        ig_pk=message.get("ig_pk"),
        extra_tags=extra_tags,
    )
    if not ing.get("ok"):
        return {"status": "error", "error": ing.get("error", "ingest failed")}

    return {"status": "done", "document_id": ing.get("document_id"), "kind": kind, "filepath": filepath}


def apply_command(state: dict, command: str) -> str:
    """Handle a start/stop control message, mutating `state`."""
    if command == "start":
        state["paused"] = False
        return "resumed"
    if command == "stop":
        state["paused"] = True
        return "paused"
    return "unknown"


def _default_download(message: dict) -> dict:
    from minimax_mcp.downloader import VideoDownloader

    IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=IG_DOWNLOADS_DIR, browser="chrome")
    return downloader.download(message.get("url", ""))


def _default_transcribe(filepath: str) -> dict:
    from minimax_mcp.transcriber import AudioTranscriber

    transcriber = AudioTranscriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE)
    return transcriber.transcribe(filepath)


def run() -> None:
    """Daemon main: connect, declare, consume ig.saved + control queue."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    connection = ig_queue.connect()
    channel = connection.channel()
    ig_queue.declare(channel)
    state = {"paused": False}

    def on_work(ch, method, properties, body):
        parsed = ig_queue.parse_message(body)
        if not parsed["ok"]:
            logger.warning("corrupted message -> DLQ: %s", parsed["error"])
            ig_queue.dead_letter(ch, properties, body)
            ch.basic_ack(method.delivery_tag)
            return

        message = parsed["message"]
        session = db.get_session()
        try:
            already = db.document_exists(session, ig_pk=message.get("ig_pk"))
        finally:
            session.close()
        if already:
            logger.info("duplicate ig_pk=%s -> ack without processing", message["ig_pk"])
            ch.basic_ack(method.delivery_tag)
            return

        res = process_message(
            message,
            download=_default_download,
            transcribe=_default_transcribe,
            describe=llm.describe_image,
            ingest=knowledge.ingest_text,
        )
        if res["status"] == "done":
            logger.info("ingested ig_pk=%s document_id=%s", message["ig_pk"], res["document_id"])
            if IG_DELETE_AFTER_INGEST:
                try:
                    Path(res["filepath"]).unlink(missing_ok=True)
                except OSError:
                    logger.warning("could not delete %s", res["filepath"])
            ch.basic_ack(method.delivery_tag)
        else:
            logger.warning("processing failed ig_pk=%s: %s", message["ig_pk"], res["error"])
            ig_queue.handle_failure(ch, properties, body)
            ch.basic_ack(method.delivery_tag)

    def on_control(ch, method, properties, body):
        import json

        try:
            command = json.loads(body).get("command", "")
        except (ValueError, TypeError):
            command = ""
        logger.info("control command: %s", apply_command(state, command))
        ch.basic_ack(method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=ig_queue.QUEUE, on_message_callback=on_work)
    channel.basic_consume(queue=ig_queue.CONTROL_QUEUE, on_message_callback=on_control)
    logger.info("ig-worker consuming %s (paused=%s)", ig_queue.QUEUE, state["paused"])
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        ig_queue.close(connection)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . python tests/unit_ig_worker.py`
Expected: `PASS`

- [ ] **Step 5: Add the pytest entry** in `tests/test_scripts.py`

```python
@pytest.mark.unit
def test_unit_ig_worker():
    result = _run_script("unit_ig_worker.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 6: Run the unit suite**

Run: `uv run --project . pytest -m unit`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/minimax_mcp/ig_worker.py tests/unit_ig_worker.py tests/test_scripts.py
git commit -m "feat(ig): daemon worker consumes ig.saved, ingests into the KB"
```

---

### Task 6: MCP tools + the 9-step checklist

**Files:**
- Modify: `src/minimax_mcp/server.py` (5 tools)
- Modify: `scripts/command_docs/catalog.py` (command names + group)
- Modify: `tests/unit_registry.py` (5 tools + required-described entries)
- Modify: `tests/unit_commands.py` (count 19 → 24)
- Modify: `README.md` (tool table rows)
- Modify: `docs/KNOWLEDGE_BASE.md` (IG sync section)
- Modify: `.env.example` (new vars)
- Generated (commit after running): `.opencode/command/*.md`, `docs/COMMANDS.md`, `docs/MCP_TOOLS.md`

**Interfaces:**
- Consumes: `ig_sync` (Task 3), `ig_queue` (Task 1), `ig_worker.apply_command` (Task 5), `db` (Task 2).
- Produces: MCP tools `ig_sync_saved`, `ig_queue_status`, `ig_worker_start`, `ig_worker_stop`, `ig_get_progress`.

**Command names** (add to `catalog.py`):
```python
    "ig_sync_saved": "ig-sync",
    "ig_queue_status": "ig-status",
    "ig_worker_start": "ig-worker",
    "ig_worker_stop": "ig-worker-stop",
    "ig_get_progress": "ig-progress",
```
`group_of` returns `"kb"` for `kb-*` else `"video"`; the `ig-*` commands will land in the video group. To keep the catalog page readable, add `"ig": "Instagram sync"` to `GROUP_TITLES` and make `group_of` return `"ig"` for `ig-*` commands (update the `unit_commands.py` group assertions accordingly).

- [ ] **Step 1: Write the failing registry/commands tests**

In `tests/unit_registry.py`, add the 5 tools to `EXPECTED_TOOLS` and nothing to `REQUIRED_DESCRIBED` (the tools have no required params; `ig_get_progress` has only an optional `last_n`). Update the module docstring count (19 → 24) if it states a number.

In `tests/unit_commands.py`, change the expected count from `19` to `24` and, if `group_of` changed, update the `group_of` assertions:

```python
if catalog.group_of("kb-buscar") == "kb" and catalog.group_of("ig-status") == "ig":
    ok("group_of splits the product areas")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project . python tests/unit_registry.py`
Expected: FAIL with `missing tools: ['ig_get_progress', 'ig_queue_status', 'ig_sync_saved', 'ig_worker_start', 'ig_worker_stop']`

Run: `uv run --project . python tests/unit_commands.py`
Expected: FAIL (count mismatch + missing command names).

- [ ] **Step 3: Add the 5 tools to `server.py`**

Insert before the `# ---------------- entrypoint ----------------` block:

```python
# =============================================================================
# NEW: Instagram Saved Posts -> Knowledge Base (RabbitMQ queue + ig-worker)
# =============================================================================

@mcp.tool()
def ig_sync_saved() -> dict[str, Any]:
    """Enfileira todos os posts salvos do Instagram (via IG_SESSIONID) na fila ig.saved.
    Nao processa nada — o daemon ig-worker consome a fila em background.
    Retorna {ok, published, skipped_existing, total}."""
    from minimax_mcp import db, ig_sync

    if not ig_sync.IG_SESSIONID:
        return {"ok": False, "error": ig_sync.SESSIONID_MISSING}
    conn = ig_queue.connect()
    try:
        channel = conn.channel()
        ig_queue.declare(channel)
        session = db.get_session()
        try:
            existing = db.list_ig_pks(session)
        finally:
            session.close()
        client = ig_sync.make_client()
        return ig_sync.sync_saved_posts(
            client, existing_pks=existing,
            publish_fn=lambda msg: ig_queue.publish(channel, msg),
        )
    except Exception as e:
        return {"ok": False, "error": f"ig_sync_saved failed: {e}"}
    finally:
        ig_queue.close(conn)


@mcp.tool()
def ig_queue_status() -> dict[str, Any]:
    """Mostra o tamanho da fila ig.saved (ready/dead) e quantos consumidores ativos."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        return _q.queue_status(conn.channel())
    except Exception as e:
        return {"ok": False, "error": f"ig_queue_status failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_worker_start() -> dict[str, Any]:
    """Envia o comando 'start' ao daemon ig-worker (retoma o consumo da fila)."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        channel = conn.channel()
        _q.declare(channel)
        import json as _json

        channel.basic_publish(
            exchange="", routing_key=_q.CONTROL_QUEUE,
            body=_json.dumps({"command": "start"}), properties=None,
        )
        return {"ok": True, "command": "start"}
    except Exception as e:
        return {"ok": False, "error": f"ig_worker_start failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_worker_stop() -> dict[str, Any]:
    """Envia o comando 'stop' ao daemon ig-worker (pausa o consumo da fila)."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        channel = conn.channel()
        _q.declare(channel)
        import json as _json

        channel.basic_publish(
            exchange="", routing_key=_q.CONTROL_QUEUE,
            body=_json.dumps({"command": "stop"}), properties=None,
        )
        return {"ok": True, "command": "stop"}
    except Exception as e:
        return {"ok": False, "error": f"ig_worker_stop failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_get_progress(
    last_n: int = Field(default=10, description="Quantos últimos resultados processados mostrar"),
) -> dict[str, Any]:
    """Mostra os últimos N posts do Instagram processados pelo ig-worker (state em downloads/ig)."""
    from minimax_mcp import db

    state_file = os.environ.get("IG_STATE_FILE", "downloads/ig/state.json")
    entries: list[dict] = []
    try:
        from pathlib import Path as _P

        if _P(state_file).exists():
            import json as _json

            entries = _json.loads(_P(state_file).read_text(encoding="utf-8"))
    except Exception:
        entries = []
    session = db.get_session()
    try:
        total_ig = len(db.list_ig_pks(session))
    finally:
        session.close()
    return {"ok": True, "last": entries[-last_n:], "documents_with_ig_pk": total_ig}
```

Note: the tools import `ig_queue` at module top via `from minimax_mcp import ig_queue` — add that import next to the existing `from minimax_mcp import knowledge` usage. `ig_get_progress` reads `downloads/ig/state.json`, which the worker writes in Task 5's `run()` — add a `state.json` write in `on_work`'s done branch:

```python
            _state = os.environ.get("IG_STATE_FILE", "downloads/ig/state.json")
            try:
                import json as _json
                from pathlib import Path as _P

                _p = _P(_state)
                _existing = _json.loads(_p.read_text(encoding="utf-8")) if _p.exists() else []
                _existing.append({"ig_pk": message["ig_pk"], "status": "done",
                                  "document_id": res["document_id"], "title": message.get("title")})
                _p.parent.mkdir(parents=True, exist_ok=True)
                _p.write_text(_json.dumps(_existing[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
```

- [ ] **Step 4: Add command names + group** to `scripts/command_docs/catalog.py`

```python
COMMAND_NAMES: dict[str, str] = {
    # ... existing entries ...
    # Instagram sync
    "ig_sync_saved": "ig-sync",
    "ig_queue_status": "ig-status",
    "ig_worker_start": "ig-worker",
    "ig_worker_stop": "ig-worker-stop",
    "ig_get_progress": "ig-progress",
}

GROUP_TITLES: dict[str, str] = {
    "video": "Pipeline de vídeo",
    "kb": "Base de conhecimento",
    "ig": "Instagram sync",
}


def group_of(command: str) -> str:
    """Which product area a command belongs to: 'kb', 'ig' or 'video'."""
    if command.startswith("kb-"):
        return "kb"
    if command.startswith("ig-"):
        return "ig"
    return "video"
```

- [ ] **Step 5: Run generators (commit generated files)**

```bash
cd "$(git rev-parse --show-toplevel)"
uv run python scripts/generate_commands.py
uv run python scripts/generate_mcp_docs.py
```

- [ ] **Step 6: Update `README.md` tool table**

Add a row per new tool (matching the existing table columns `tool | slash | purpose`):

```markdown
| `ig_sync_saved` | `/ig-sync` | Enqueue every Instagram saved post (via IG_SESSIONID) onto the RabbitMQ queue |
| `ig_queue_status` | `/ig-status` | RabbitMQ queue depth and active consumers |
| `ig_worker_start` | `/ig-worker` | Send 'start' to the ig-worker daemon |
| `ig_worker_stop` | `/ig-worker-stop` | Send 'stop' to the ig-worker daemon |
| `ig_get_progress` | `/ig-progress` | Last processed Instagram items + KB document count |
```

- [ ] **Step 7: Update `.env.example`** (append a section)

```bash
# -----------------------------------------------------------------------------
# INSTAGRAM SAVED -> KNOWLEDGE BASE (RabbitMQ + ig-worker daemon)
# -----------------------------------------------------------------------------
# sessionid from the Chrome cookies (Instagram, logged-in). Never a password.
IG_SESSIONID=
# RabbitMQ: default local docker service; VPS = point at your RabbitMQ.
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_QUEUE=ig.saved
IG_WORKER_CONCURRENCY=1
IG_DOWNLOADS_DIR=downloads/ig
IG_DELETE_AFTER_INGEST=true
IG_STATE_FILE=downloads/ig/state.json
# Local vision model for describing saved photos (Ollama).
OLLAMA_VISION_MODEL=qwen2.5vl:7b
```

- [ ] **Step 8: Update `docs/KNOWLEDGE_BASE.md`**

Add a short section (e.g. before `## 7. Configuration`) documenting the IG sync: what it does, the 5 tools, prerequisites (`IG_SESSIONID`, RabbitMQ, `ollama pull qwen2.5vl:7b`), and the golden rule (never rebuild/restart with a busy render queue — check `queue_status` first).

- [ ] **Step 9: Run the enforced tests**

```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project . python tests/unit_registry.py
uv run --project . python tests/unit_commands.py
uv run --project . pytest -m unit
uv run mkdocs build --strict
```
Expected: all pass. The generated `.opencode/command/*.md`, `docs/COMMANDS.md`, `docs/MCP_TOOLS.md` must be committed.

- [ ] **Step 10: Commit**

```bash
git add src/minimax_mcp/server.py scripts/command_docs/catalog.py tests/unit_registry.py tests/unit_commands.py README.md docs/KNOWLEDGE_BASE.md .env.example .opencode/command docs/COMMANDS.md docs/MCP_TOOLS.md
git commit -m "feat(ig): MCP tools + slash commands + docs for Instagram sync"
```

---

### Task 7: Docker Compose — `rabbitmq` + `ig-worker` services

**Files:**
- Modify: `docker/docker-compose.yml`

**Interfaces:**
- Consumes: `ig_worker.run()` (Task 5) as the `ig-worker` container command; `.env` vars from `.env.example`.
- Produces: `rabbitmq` (mgmt UI on `127.0.0.1:15672`), `ig-worker` container.

- [ ] **Step 1: Add the `rabbitmq` service**

Append to `docker/docker-compose.yml` (after the `postgres` service):

```yaml
  # Message broker for the Instagram saved-posts sync. Local by default; a VPS
  # RabbitMQ can be used instead by setting RABBITMQ_URL in .env.
  rabbitmq:
    image: rabbitmq:3-management
    container_name: ${RABBITMQ_CONTAINER:-minimax-rabbitmq}
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-guest}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS:-guest}
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    volumes:
      - ${RABBITMQ_DATA_DIR:-.rabbitmq}:/var/lib/rabbitmq
```

- [ ] **Step 2: Add the `ig-worker` service**

```yaml
  # Instagram saved-posts -> knowledge base worker. Same image/stack as the H3
  # renderer (shares its GPU for Whisper/vision); reaches postgres + rabbitmq on
  # the compose network and host Ollama via host.docker.internal.
  ig-worker:
    image: ${COMFY_IMAGE:-minimax-comfyui:local}
    container_name: ${IG_WORKER_CONTAINER:-minimax-ig-worker}
    depends_on:
      - comfyui
      - postgres
      - rabbitmq
    volumes:
      - ${PROJECT_ROOT:-..}:/workspace:ro
      - ${DOWNLOADS_DIR:-${PROJECT_ROOT:-..}/downloads}:/downloads
      - ${HF_CACHE_DIR:-${PROJECT_ROOT:-..}/.hf-cache}:/root/.cache/huggingface
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility,video
      PYTHONPATH: /workspace/src
      RABBITMQ_URL: amqp://${RABBITMQ_USER:-guest}:${RABBITMQ_PASS:-guest}@rabbitmq:5672/
      RABBITMQ_QUEUE: ${RABBITMQ_QUEUE:-ig.saved}
      KB_DATABASE_URL: postgresql+psycopg://${KB_POSTGRES_USER:-kb}:${KB_POSTGRES_PASSWORD:-kb}@postgres:5432/${KB_POSTGRES_DB:-knowledge}
      OLLAMA_URL: http://host.docker.internal:11434
      OLLAMA_VISION_MODEL: ${OLLAMA_VISION_MODEL:-qwen2.5vl:7b}
      WHISPER_MODEL: ${WHISPER_MODEL:-small}
      WHISPER_DEVICE: ${WHISPER_DEVICE:-cuda}
      LLM_MODEL: ${LLM_MODEL:-lfm2:24b}
      LLM_TIMEOUT: ${LLM_TIMEOUT:-900}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-mxbai-embed-large}
      EMBEDDING_DIM: ${EMBEDDING_DIM:-1024}
      IG_SESSIONID: ${IG_SESSIONID}
      IG_WORKER_CONCURRENCY: ${IG_WORKER_CONCURRENCY:-1}
      IG_DOWNLOADS_DIR: /downloads/ig
      IG_DELETE_AFTER_INGEST: ${IG_DELETE_AFTER_INGEST:-true}
      IG_STATE_FILE: /downloads/ig/state.json
      VAULT_PATH: ${VAULT_PATH:-}
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [ gpu ]
    restart: unless-stopped
    command: ["bash", "-c", "cd /workspace && /opt/mcp-venv/bin/python -m minimax_mcp.ig_worker"]
```

- [ ] **Step 3: Validate the compose file parses**

Run: `docker compose --project-directory . --env-file .env -f docker/docker-compose.yml config >/dev/null`
Expected: exit 0 (config valid). Note: `.env` must exist in the worktree (copy from main if missing); `IG_SESSIONID` may be empty in the worktree `.env` — compose will still validate.

- [ ] **Step 4: Commit**

```bash
git add docker/docker-compose.yml
git commit -m "feat(ig): add rabbitmq + ig-worker services to the docker stack"
```

---

### Task 8: Integration tests + container deps

**Files:**
- Create: `tests/integration_ig_db.py` (dedup against real Postgres)
- Create: `tests/integration_ig_llm.py` (vision describe against real Ollama)
- Modify: `tests/test_scripts.py` (integration entries)
- Modify: `tests/09_container_deps.sh` (module list)

**Interfaces:**
- Consumes: `db.save_document` (Task 2), `ig_sync.to_messages` (Task 3), `llm.describe_image` (Task 4), `ig_worker.process_message` (Task 5).

- [ ] **Step 1: Write `tests/integration_ig_db.py`**

```python
#!/usr/bin/env python3
"""Postgres integration for IG dedup: re-sync must not duplicate.

Requires: `docker compose up -d postgres` + `alembic upgrade head` applied.
Run: uv run --project . python tests/integration_ig_db.py
"""
from __future__ import annotations

import sys
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


from minimax_mcp import db


def fake_embed(text: str) -> list[float]:
    seed = sum(ord(c) for c in text)
    return [((seed + i) % 100) / 100.0 for i in range(db.EMBEDDING_DIM)]


print("== integration_ig_db: dedup by ig_pk ==")
session = db.get_session()
try:
    db.delete_documents(session, source_url="https://www.instagram.com/p/igtest1/")
    db.delete_documents(session, source_url="https://www.instagram.com/p/igtest2/")
finally:
    session.close()

session = db.get_session()
try:
    doc = db.save_document(
        session,
        type="video", source_url="https://www.instagram.com/p/igtest1/",
        platform="instagram", title="IG teste", language="pt",
        transcription_text="teste instagram " * 30, summary="s", tutorial="t",
        objectives="o", tags=["instagram"], raw_file_path=None,
        llm_provider="ollama", llm_model="lfm2:24b",
        embed_fn=fake_embed, embedding_model="fake-embed-test",
        ig_pk="igtest1",
    )
    if db.document_exists(session, ig_pk="igtest1"):
        ok("document_exists(ig_pk) true after save")
    else:
        bad("document_exists(ig_pk) false after save")

    if "igtest1" in db.list_ig_pks(session):
        ok("list_ig_pks contains the saved ig_pk")
    else:
        bad("list_ig_pks missing the saved ig_pk")
finally:
    session.close()

print("== integration_ig_db: second ingest does not duplicate ==")
from minimax_mcp import ig_sync

session = db.get_session()
try:
    existing = db.list_ig_pks(session)
    new, skipped = ig_sync.split_new(
        [{"ig_pk": "igtest1", "media_type": "video", "url": "https://www.instagram.com/p/igtest1/"}],
        existing,
    )
    if skipped == 1 and new == []:
        ok("re-sync skips an already-ingested ig_pk")
    else:
        bad(f"split_new = new={new} skipped={skipped}")
finally:
    session.close()

session = db.get_session()
try:
    removed = db.delete_documents(session, source_url="https://www.instagram.com/p/igtest1/")
    if removed >= 1:
        ok(f"cleanup removed {removed} document(s)")
    else:
        bad("cleanup removed nothing")
finally:
    session.close()

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
```

- [ ] **Step 2: Write `tests/integration_ig_llm.py`**

```python
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
```

- [ ] **Step 3: Wire into `tests/test_scripts.py`**

```python
@pytest.mark.integration_db
def test_integration_ig_db():
    result = _run_script("integration_ig_db.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_llm
def test_integration_ig_llm():
    result = _run_script("integration_ig_llm.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 4: Add the modules to `tests/09_container_deps.sh`**

In the `MODULES="..."` string, append:

```
minimax_mcp.ig_queue minimax_mcp.ig_sync minimax_mcp.ig_worker
```

- [ ] **Step 5: Run the integration tests**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project . alembic upgrade head
uv run --project . pytest -m "integration_db or integration_llm"
```
Expected: `integration_ig_db` PASS; `integration_ig_llm` PASS (or SKIP while the vision model is downloading). The 09-container-deps test requires a rebuilt image — skip it here and run after Task 9's rebuild.

- [ ] **Step 6: Commit**

```bash
git add tests/integration_ig_db.py tests/integration_ig_llm.py tests/test_scripts.py tests/09_container_deps.sh
git commit -m "test(ig): integration tests for IG dedup and vision describe"
```

---

### Task 9: Container rebuild + full validation

**Files:**
- Modify: none (build + validate).

**Interface check:** The image must include `pika`/`instagrapi` (added in Tasks 1/3). The compose `ig-worker` service (Task 7) mounts `/workspace:ro` and runs `/opt/mcp-venv/bin/python -m minimax_mcp.ig_worker`.

- [ ] **Step 1: Check the render queue is EMPTY before touching the stack**

Run: `curl -s http://127.0.0.1:8188/queue`
Expected: `running: 0 pending: 0` (or use the `queue_status` MCP tool). **If the queue is busy, stop and wait — never rebuild with a render running.**

- [ ] **Step 2: Rebuild and restart the stack (only after Step 1 is confirmed)**

```bash
cd "$(git rev-parse --show-toplevel)"
./scripts/stop_comfyui.sh && ./scripts/start_comfyui.sh
```
Expected: comfyui, postgres, rabbitmq, ig-worker all `Up`. Watch `docker compose --project-directory . --env-file .env -f docker/docker-compose.yml ps`.

- [ ] **Step 3: Validate in-container deps and tool registry**

```bash
cd "$(git rev-parse --show-toplevel)"
bash tests/09_container_deps.sh
```
Expected: `ALL PASS` (pika/instagrapi present, all modules import, container exposes 24 tools).

- [ ] **Step 4: Full test sweep**

```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project . pytest
uv run mkdocs build --strict
./scripts/diagnose.sh
```
Expected: all green.

- [ ] **Step 5: Commit any leftover generated/changed files**

```bash
git add -A
git commit -m "chore(ig): rebuild image with pika+instagrapi and validate stack"
```

---

## Self-Review

**Spec coverage:**
- Enumeration via instagrapi + `IG_SESSIONID` → Task 3 (`make_client` sets sessionid; `delay_range`).
- RabbitMQ queue `ig.saved` + DLQ `ig.saved.dead`, durable, `attempts` header, DLQ after 3 → Task 1 (`declare`, `handle_failure`).
- Dedup by `ig_pk` (worker checks KB before processing) → Task 2 (`document_exists`) + Task 5 (`on_work`).
- Scope everything (video/image/carousel; carousel → first item) → Task 3 (`MEDIA_TYPES`) + Task 5 (`classify_file` for carousel first item).
- Photos via vision LLM (`OLLAMA_VISION_MODEL` qwen2.5vl:7b) → Task 4 (`describe_image`).
- Collection → tag (`collection_name` → `extra_tags`) → Task 3 (`to_messages`) + Task 5 (`process_message` extra_tags).
- Worker daemon, concurrency=1, prefetch=1, same stack/GPU, host-gateway Ollama → Task 5 + Task 7.
- Tools fail-soft `{ok: false, error}` → Task 6 (all tools wrap in try/except).
- `IG_DELETE_AFTER_INGEST` default true → Task 5 (`run()` deletes after done).
- Never rebuild with busy render queue → Task 9 Step 1.
- 9-step tool checklist → Task 6 (catalog, generators, unit_registry, unit_commands, README, docs).
- `knowledge.ingest_text` reuse → Task 2 signature extension, used in Task 5.
- Docs: KNOWLEDGE_BASE.md, .env.example, mkdocs strict → Task 6 Steps 7-9.

**Placeholder scan:** no TBD/TODO; every code step contains real code; injected-callable seams (`download`, `transcribe`, `describe`, `ingest`, `publish_fn`, `channel`) are defined in the same task that uses them.

**Type consistency:**
- `handle_failure(channel, properties, body)` — Task 1 defines it; Task 5 calls `ig_queue.handle_failure(ch, properties, body)` with the pika consumer's `properties` argument. Consistent.
- `process_message(message, *, download, transcribe, describe, ingest)` — defined once in Task 5; tests and `on_work` call it with the same kwargs. Consistent.
- `knowledge.ingest_text(..., ig_pk=..., extra_tags=...)` — Task 2 changes the signature; Task 5 passes those kwargs. Consistent.
- `split_new(messages, existing_pks) -> (list, int)` — Task 3 defines; Task 8 uses it. Consistent.
- `db.save_document(..., ig_pk=...)` — Task 2 adds; Task 8 uses it. Consistent.
- Counts: 19 tools → +5 = 24 (unit_commands Step 1, registry Step 1, container deps Step 4 expects `@mcp.tool()` count from source so it auto-adapts). Consistent.
