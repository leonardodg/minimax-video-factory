#!/usr/bin/env python3
"""Backfill: re-apply CTA cleanup to already-ingested Instagram documents.

For each document with an ig_pk, it:
  1. snapshots the current state as .md + .json in output/kb-backup/
  2. strips CTA from transcription_text
  3. regenerates summary/tutorial/objectives/tags via the LLM (new prompt)
  4. writes the UPDATE, preserving id/ig_pk/source_url/platform/created_at

Modes:
  --dry-run            show what would change, write nothing
  --restore <id>       truly restores <id>'s fields from its .json snapshot
                       (rollback): writes transcription_text/summary/tutorial/
                       objectives/tags/language/title/llm_* back to Postgres.

Run from the worktree: uv run --directory . python scripts/backfill_cta.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
from sqlalchemy import select

from minimax_mcp import db, knowledge, llm, vault
from minimax_mcp.db import Document
from minimax_mcp.ig_worker import strip_cta

load_dotenv()

BACKUP_DIR = Path("output/kb-backup")


def _snapshot_path(doc_id: int, ig_pk: str) -> Path:
    return BACKUP_DIR / f"{doc_id}-{ig_pk}.md"


def _snapshot_json_path(doc_id: int, ig_pk: str) -> Path:
    return BACKUP_DIR / f"{doc_id}-{ig_pk}.json"


def snapshot_doc(doc) -> Path:
    """Snapshot `doc` to disk: a machine-readable .json (authoritative for
    restore) plus a human-readable .md (comparison artifact).

    `vault.write_markdown_copy` never returns ok=False (it swallows errors and
    returns `{"skipped": True}`), so the presence of a `path` in its result is
    the only reliable success signal. The .json is written directly and is the
    source of truth for restore_doc.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    json_path = _snapshot_json_path(doc.id, doc.ig_pk)
    json_path.write_text(
        json.dumps(
            {
                "id": doc.id,
                "type": doc.type,
                "source_url": doc.source_url,
                "platform": doc.platform,
                "title": doc.title,
                "language": doc.language,
                "transcription_text": doc.transcription_text,
                "summary": doc.summary,
                "tutorial": doc.tutorial,
                "objectives": doc.objectives,
                "tags": doc.tags or [],
                "raw_file_path": doc.raw_file_path,
                "llm_provider": doc.llm_provider,
                "llm_model": doc.llm_model,
                "ig_pk": doc.ig_pk,
                "created_at": doc.created_at,
            },
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    res = vault.write_markdown_copy(knowledge._document_to_dict(doc), str(BACKUP_DIR))
    if not res.get("path"):
        raise RuntimeError(
            f"snapshot write failed for doc {doc.id}: {res.get('reason')}"
        )
    target = _snapshot_path(doc.id, doc.ig_pk)
    os.replace(res["path"], target)
    return target


def restore_doc(doc_id: int, ig_pk: str) -> dict:
    """Read the .json snapshot back into a field dict for Postgres restore.

    The .json is authoritative; the .md is only a human-readable fallback.
    """
    p = _snapshot_json_path(doc_id, ig_pk)
    if not p.exists():
        return {"ok": False, "error": f"no snapshot at {p}"}
    try:
        fields = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"unparseable snapshot {p}: {e!r}"}
    return {"ok": True, "fields": fields, "path": str(p)}


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
        if not res.get("ok"):
            print(res.get("error", "restore failed"))
            return 1
        fields = res["fields"]
        s2 = db.get_session()
        try:
            row = s2.get(Document, doc.id)
            if row is None:
                print(f"document {doc.id} not found in database")
                return 1
            row.transcription_text = fields.get("transcription_text")
            row.summary = fields.get("summary")
            row.tutorial = fields.get("tutorial")
            row.objectives = fields.get("objectives")
            row.tags = fields.get("tags")
            row.language = fields.get("language")
            row.title = fields.get("title")
            if "llm_provider" in fields:
                row.llm_provider = fields.get("llm_provider")
            if "llm_model" in fields:
                row.llm_model = fields.get("llm_model")
            s2.commit()
        except Exception as e:
            s2.rollback()
            print(f"restore failed for {doc.id}: {e!r}")
            return 1
        finally:
            s2.close()
        print(f"restored document {doc.id} from snapshot")
        return 0

    for doc in docs:
        cleaned = strip_cta(doc.transcription_text or "")
        changed = cleaned != doc.transcription_text
        print(f"[{doc.id}] cta_changed={changed}")
        if args.dry_run:
            print(f"    transcription {len(doc.transcription_text or '')} -> {len(cleaned)} chars")
            continue

        if _snapshot_path(doc.id, doc.ig_pk).exists() or _snapshot_json_path(doc.id, doc.ig_pk).exists():
            print(
                f"    snapshot exists at {_snapshot_path(doc.id, doc.ig_pk)} "
                f"— already backfilled; skipping (use --restore {doc.id} to roll back)"
            )
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
