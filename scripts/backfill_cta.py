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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
from sqlalchemy import select

from minimax_mcp import db, llm, vault
from minimax_mcp.db import Document
from minimax_mcp.ig_worker import strip_cta

load_dotenv()

BACKUP_DIR = Path("output/kb-backup")


def _snapshot_path(doc_id: int, ig_pk: str) -> Path:
    return BACKUP_DIR / f"{doc_id}-{ig_pk}.md"


def snapshot_doc(doc) -> Path:
    """Serialize `doc` through the shared vault writer, then park it at the
    deterministic snapshot path so restore_doc can always find it.

    `vault.write_markdown_copy` never returns ok=False (it swallows errors and
    returns `{"skipped": True}`), so the presence of a `path` in its result is
    the only reliable success signal.
    """
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
    if not res.get("path"):
        raise RuntimeError(
            f"snapshot write failed for doc {doc.id}: {res.get('reason')}"
        )
    target = _snapshot_path(doc.id, doc.ig_pk)
    os.replace(res["path"], target)
    return target


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
        cleaned = strip_cta(doc.transcription_text or "")
        changed = cleaned != doc.transcription_text
        print(f"[{doc.id}] cta_changed={changed}")
        if args.dry_run:
            print(f"    transcription {len(doc.transcription_text or '')} -> {len(cleaned)} chars")
            continue

        snap = snapshot_doc(doc)
        print(f"    snapshot={snap}")

        # generate_structured never raises: success -> {"ok", provider, model,
        # resumo, tutorial, objetivos, tags}; failure -> {"ok": False, error}.
        gen = llm.generate_structured(cleaned, is_image=(doc.type == "image"))
        if not gen.get("ok"):
            print(f"    LLM failed for {doc.id}: {gen.get('error')}")
            continue
        fields = gen

        s2 = db.get_session()
        try:
            doc = s2.get(Document, doc.id)
            doc.transcription_text = cleaned
            doc.summary = fields.get("resumo")
            doc.tutorial = fields.get("tutorial")
            doc.objectives = "\n".join(fields.get("objetivos") or [])
            doc.tags = fields.get("tags")
            doc.llm_provider = fields.get("provider")
            doc.llm_model = fields.get("model")
            s2.commit()
        except Exception as e:
            s2.rollback()
            print(f"    update failed for {doc.id}: {e!r}")
            continue
        finally:
            s2.close()
        print(f"    updated summary len={len(fields.get('resumo') or '')}")

    print("done. snapshots in", BACKUP_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
