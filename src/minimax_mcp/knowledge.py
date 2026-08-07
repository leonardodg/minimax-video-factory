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
