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
