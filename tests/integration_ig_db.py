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
