#!/usr/bin/env python3
"""Postgres-dependent tests for db.py. Requires: `docker compose up -d postgres`
+ `alembic upgrade head` already applied (see Task 1/2). No Ollama required —
uses a fake deterministic embedding function.

Run: uv run --directory . python tests/integration_knowledge_db.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import db, knowledge


def fake_embed(text: str) -> list[float]:
    """Deterministic fake embedding: length matches EMBEDDING_DIM, values from hash."""
    dim = db.EMBEDDING_DIM
    seed = sum(ord(c) for c in text)
    return [((seed + i) % 100) / 100.0 for i in range(dim)]


doc = None
export_doc_id = None
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
        ig_pk="12345",
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

print("== integration_knowledge_db: export round-trip ==")
session = db.get_session()
try:
    export_doc = db.save_document(
        session,
        type="text",
        source_url="https://example.com/export-test",
        platform="manual",
        title="Export test doc",
        language="pt",
        transcription_text="Receita: bata 2 ovos com açúcar. Finalize com canela.",
        summary="Resumo de export test.",
        tutorial="## Passo 1\nBata ovos.",
        objectives="Objetivo 1\nObjetivo 2",
        tags=["test", "export"],
        raw_file_path=None,
        llm_provider="ollama",
        llm_model="lfm2:24b",
        embed_fn=fake_embed,
        embedding_model="fake-embed-test",
    )
    export_doc_id = export_doc.id
    if export_doc_id is not None:
        ok(f"save_document created export-test document id={export_doc_id}")
    else:
        bad("save_document did not assign an id to the export-test document")
except Exception as e:
    bad(f"export round-trip: save_document raised: {e}")
finally:
    session.close()

try:
    if export_doc_id is None:
        bad("export round-trip: skipping exercises because save_document failed")
    else:
        try:
            listed = knowledge.export_search(ids=[export_doc_id])
            if (
                listed.get("ok")
                and listed.get("total") == 1
                and listed["documents"][0]["id"] == export_doc_id
            ):
                ok("export_search(ids=[doc_id]) lists exactly the saved document")
            else:
                bad(f"export_search returned unexpected result: {listed!r}")
        except Exception as e:
            bad(f"export_search raised: {e}")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                exported = knowledge.export_documents([export_doc_id], output_dir=tmp)
                f0 = exported["files"][0]
                if (
                    exported.get("ok")
                    and f0.get("ok")
                    and Path(f0["path"]).exists()
                ):
                    ok(f"export_documents wrote markdown file: {f0['path']}")
                else:
                    bad(f"export_documents returned unexpected result: {exported!r}")
        except Exception as e:
            bad(f"export_documents raised: {e}")

        try:
            missing = knowledge.export_documents([99999999])
            if missing.get("ok") and missing["files"][0]["ok"] is False:
                ok("export_documents tolerates a missing id (files[0].ok is False)")
            else:
                bad(f"export_documents missing-id result unexpected: {missing!r}")
        except Exception as e:
            bad(f"export_documents(missing id) raised: {e}")
finally:
    session = db.get_session()
    try:
        removed = db.delete_documents(session, source_url="https://example.com/export-test")
        if removed >= 1:
            ok(f"export round-trip cleanup removed {removed} document(s)")
        else:
            bad("export round-trip cleanup removed 0 documents")
    except Exception as e:
        bad(f"export round-trip cleanup raised: {e}")
    finally:
        session.close()

print("== integration_knowledge_db: export skipped -> files[0].ok False ==")
try:
    session = db.get_session()
    try:
        skip_doc = db.save_document(
            session,
            type="text",
            source_url="https://example.com/export-skip-test",
            platform="manual",
            title="Export skip test doc",
            language="pt",
            transcription_text="Texto do skip test.",
            summary="Resumo do skip test.",
            tutorial=None,
            objectives=None,
            tags=["test"],
            raw_file_path=None,
            llm_provider="ollama",
            llm_model="lfm2:24b",
            embed_fn=fake_embed,
            embedding_model="fake-embed-test",
        )
    finally:
        session.close()

    # empty output_dir is falsy -> vault.write_markdown_copy returns
    # {ok: True, skipped: True}; the per-file ok must reflect "written",
    # i.e. False, while the overall export stays ok=True.
    res = knowledge.export_documents([skip_doc.id], output_dir="")
    f0 = res["files"][0]
    if (
        res.get("ok") is True
        and f0.get("ok") is False
        and f0.get("skipped") is True
    ):
        ok("export_documents with empty output_dir: files[0].ok False, skipped True, overall ok True")
    else:
        bad(f"export_documents empty output_dir unexpected: {res!r}")
except Exception as e:
    bad(f"export skip test raised: {e}")
finally:
    session = db.get_session()
    try:
        removed = db.delete_documents(session, source_url="https://example.com/export-skip-test")
        if removed >= 1:
            ok(f"export skip test cleanup removed {removed} document(s)")
        else:
            bad("export skip test cleanup removed 0 documents")
    except Exception as e:
        bad(f"export skip test cleanup raised: {e}")
    finally:
        session.close()

print("== integration_knowledge_db: backfill snapshot/restore round-trip ==")
import backfill_cta as backfill

restore_doc_id = None
restore_md_path = None
restore_json_path = None
try:
    session = db.get_session()
    try:
        restore_doc = db.save_document(
            session,
            type="text",
            source_url="https://example.com/export-restore-test",
            platform="manual",
            title="Restore test doc",
            language="pt",
            transcription_text="Transcrição original do restore test.",
            summary="Resumo original.",
            tutorial="Tutorial original.",
            objectives="Objetivo original.",
            tags=["restore"],
            raw_file_path=None,
            llm_provider="ollama",
            llm_model="lfm2:24b",
            embed_fn=fake_embed,
            embedding_model="fake-embed-test",
            ig_pk="999",
        )
        restore_doc_id = restore_doc.id
        original_summary = restore_doc.summary
    finally:
        session.close()
    if restore_doc_id is None:
        bad("restore round-trip: save_document failed")
    else:
        restore_md_path = backfill._snapshot_path(restore_doc_id, "999")
        restore_json_path = backfill._snapshot_json_path(restore_doc_id, "999")

        session = db.get_session()
        try:
            doc_for_snap = session.get(db.Document, restore_doc_id)
        finally:
            session.close()
        try:
            backfill.snapshot_doc(doc_for_snap)
            if restore_md_path.exists() and restore_json_path.exists():
                ok(f"snapshot_doc wrote .md + .json for doc {restore_doc_id}")
            else:
                bad(
                    f"snapshot_doc missing files: "
                    f"md={restore_md_path.exists()} json={restore_json_path.exists()}"
                )
        except Exception as e:
            bad(f"snapshot_doc raised: {e}")

        session = db.get_session()
        try:
            row = session.get(db.Document, restore_doc_id)
            row.summary = "Resumo MUTADO."
            session.commit()
        finally:
            session.close()

        res = backfill.restore_doc(restore_doc_id, "999")
        if res.get("ok") and res["fields"].get("summary") == original_summary:
            ok("restore_doc reads the .json snapshot with the original summary")
        else:
            bad(f"restore_doc unexpected: {res!r}")

        session = db.get_session()
        try:
            row = session.get(db.Document, restore_doc_id)
            fields = res["fields"]
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
            session.commit()
        finally:
            session.close()

        session = db.get_session()
        try:
            re_read = session.get(db.Document, restore_doc_id)
            if re_read.summary == original_summary:
                ok("row summary restored to the original after applying restore")
            else:
                bad(f"row summary after restore = {re_read.summary!r}, expected {original_summary!r}")
        finally:
            session.close()
except Exception as e:
    bad(f"restore round-trip raised: {e}")
finally:
    for p in (restore_md_path, restore_json_path):
        if p is not None and p.exists():
            try:
                p.unlink()
            except Exception as e:
                bad(f"restore cleanup unlink failed for {p}: {e}")
    session = db.get_session()
    try:
        removed = db.delete_documents(session, source_url="https://example.com/export-restore-test")
        if removed >= 1:
            ok(f"restore round-trip cleanup removed {removed} document(s)")
        else:
            bad("restore round-trip cleanup removed 0 documents")
    except Exception as e:
        bad(f"restore round-trip cleanup raised: {e}")
    finally:
        session.close()

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
