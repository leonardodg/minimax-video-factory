#!/usr/bin/env python3
"""Postgres-dependent tests for db.py. Requires: `docker compose up -d postgres`
+ `alembic upgrade head` already applied (see Task 1/2). No Ollama required —
uses a fake deterministic embedding function.

Run: uv run --directory . python tests/integration_knowledge_db.py
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


doc = None
print("== integration_knowledge_db: cleanup previous test runs ==")
session = db.get_session()
try:
    removed = db.delete_documents(session, source_url="https://example.com/test")
    if removed >= 0:
        ok(f"removed {removed} leftover test document(s)")
except Exception as e:
    bad(f"cleanup raised: {e}")
finally:
    session.close()

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
        llm_model="lfm2:24b",
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

print("== integration_knowledge_db: search_documents ==")
session = db.get_session()
try:
    # Unique query only the test document matches, so real KB content (e.g. the
    # imported Docker tutorials) can't outrank it.
    results = db.search_documents(session, "texto de teste sobre Python", embed_fn=fake_embed, top_k=5)
    if isinstance(results, list) and len(results) >= 1:
        ok(f"search_documents('texto de teste sobre Python') returned {len(results)} result(s)")
    else:
        bad(f"search_documents returned {results!r}")

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
finally:
    session.close()

print("")
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
