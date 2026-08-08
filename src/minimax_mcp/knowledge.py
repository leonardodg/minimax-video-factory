"""Orchestration layer for the knowledge base: ties together llm.py, db.py, vault.py
and the existing downloader/transcriber, and is what server.py's MCP tools call."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from minimax_mcp import db, llm, vault

logger = logging.getLogger(__name__)

VAULT_PATH = os.environ.get("VAULT_PATH") or None


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter (`---` delimited, if present) from the markdown body.

    Returns (meta, body). Tolerates missing/broken frontmatter.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta_raw, body = parts[1], parts[2]
    try:
        meta = yaml.safe_load(meta_raw) or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body.lstrip("\n")


def _extract_section(body: str, heading: str = "Summary") -> str | None:
    """Extract the text under a `## <heading>` markdown section (case-insensitive),
    e.g. the `## Summary` block found in Claude Chat transcripts."""
    pat = re.compile(
        rf"^##+\s*{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE
    )
    m = pat.search(body)
    if not m:
        return None
    start = m.end()
    # section ends at the next top-level (## or lower) heading
    nxt = re.search(r"^##+\s+\S", body[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(body)
    text = body[start:end].strip()
    return text or None


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

    if path_or_url.startswith(("http://", "https://")):
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


def ingest_markdown(
    path: str | Path,
    *,
    recursive: bool = False,
    doc_type: str = "document",
    platform: str = "obsidian",
    language: str = "pt",
    reindex_if_exists: bool = False,
) -> dict[str, Any]:
    """Import one or more markdown files (e.g. Obsidian tutorials) into the KB.

    Accepts a file path or a directory (recursive optional). YAML frontmatter is
    used for title/tags/source_url; a `## Summary` section is reused when present,
    otherwise the LLM generates summary+tutorial+objectives+tags. Skips `.trash`,
    `.obsidian` and other dot-directories. Returns per-file results.
    """
    p = Path(path).expanduser()
    if p.is_file():
        files = [p]
    elif p.is_dir():
        files = sorted(
            f
            for f in (p.rglob("*.md") if recursive else p.glob("*.md"))
            if not any(part.startswith(".") for part in f.relative_to(p).parts)
        )
    else:
        return {"ok": False, "error": f"path not found: {path}"}
    if not files:
        return {"ok": False, "error": f"no .md files found in {path}"}

    results: list[dict[str, Any]] = []
    imported = 0
    for f in files:
        res = _ingest_markdown_file(
            f,
            doc_type=doc_type,
            platform=platform,
            language=language,
            reindex_if_exists=reindex_if_exists,
        )
        results.append({"file": str(f), **res})
        if res.get("ok"):
            imported += 1
    failed = len(files) - imported

    # ok reflects whether anything was actually imported. Returning ok=True with
    # imported=0 reads as success and hides the common causes -- an unreachable
    # database, Ollama down -- behind a green result. A partial import is still
    # a success, but the caller is told how many fell over and why.
    first_error = next(
        (r.get("error") for r in results if not r.get("ok") and r.get("error")), None
    )
    out = {
        "ok": imported > 0,
        "imported": imported,
        "failed": failed,
        "total": len(files),
        "results": results,
    }
    if failed:
        out["error"] = (
            f"{failed} of {len(files)} file(s) failed"
            + (f": {first_error}" if first_error else "")
        )
    return out


def _ingest_markdown_file(
    f: Path,
    *,
    doc_type: str,
    platform: str,
    language: str,
    reindex_if_exists: bool,
) -> dict[str, Any]:
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"read failed: {e}"}
    if not content.strip():
        return {"ok": False, "error": "empty file"}

    meta, body = _parse_frontmatter(content)
    title = str(meta.get("title") or f.stem).strip()
    source_url = meta.get("url") or None
    fm_tags = meta.get("tags") or []
    if isinstance(fm_tags, str):
        fm_tags = [t.strip() for t in fm_tags.split(",") if t.strip()]
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]

    summary = _extract_section(body, "Summary")
    if summary:
        return _save_document_with(
            f, doc_type=doc_type, platform=platform, language=language,
            title=title, source_url=source_url, text=body,
            summary=summary, tutorial=None, objectives=None, tags=fm_tags,
            llm_provider="frontmatter", llm_model="none",
        )

    gen = llm.generate_structured(body)
    if not gen.get("ok"):
        gen = llm.generate_structured(body[:4000])
    if not gen.get("ok"):
        return {"ok": False, "stage": "llm", "error": gen.get("error")}

    tags = list(dict.fromkeys([t for t in (fm_tags + (gen.get("tags") or [])) if t]))
    return _save_document_with(
        f, doc_type=doc_type, platform=platform, language=language,
        title=title, source_url=source_url, text=body,
        summary=gen.get("resumo"), tutorial=gen.get("tutorial"),
        objectives="\n".join(gen.get("objetivos") or []), tags=tags,
        llm_provider=gen.get("provider"), llm_model=gen.get("model"),
    )


def _save_document_with(
    f: Path,
    *,
    doc_type: str,
    platform: str,
    language: str,
    title: str,
    source_url: str | None,
    text: str,
    summary: str | None,
    tutorial: str | None,
    objectives: str | None,
    tags: list[str],
    llm_provider: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    session = db.get_session()
    try:
        doc = db.save_document(
            session,
            type=doc_type,
            source_url=source_url,
            platform=platform,
            title=title,
            language=language,
            transcription_text=text,
            summary=summary,
            tutorial=tutorial,
            objectives=objectives,
            tags=tags,
            raw_file_path=str(f),
            llm_provider=llm_provider,
            llm_model=llm_model,
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
        "summary": doc_dict["summary"], "tags": doc_dict["tags"], "vault": vault_result,
    }


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
