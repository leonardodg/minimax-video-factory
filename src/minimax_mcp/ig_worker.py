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
import time
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


def _pick_download_target(client: Any, pk: str) -> tuple[str, str]:
    """Choose the download method + media pk for a saved post.

    Returns ("photo_download"|"clip_download", target_pk). Carousels
    (media_type 8) have no clip of their own — the pk is an album container and
    clip_download raises "Must been video". Instead, pick the first video
    resource (or the first image when the album has no video) and download that
    individual resource. Single media fall through to the pk itself.
    """
    info = client.media_info(pk)
    mtype = int(getattr(info, "media_type", 0) or 0)
    if mtype == 8:
        resources = list(getattr(info, "resources", None) or [])
        for r in resources:
            if int(getattr(r, "media_type", 0) or 0) == 2:
                return "clip_download", str(r.pk)
        if resources:
            return "photo_download", str(resources[0].pk)
        return "photo_download", pk
    if mtype == 1:
        return "photo_download", pk
    return "clip_download", pk


def _default_download(message: dict) -> dict:
    """Download the media for a saved post.

    Prefers the authenticated instagrapi client (the worker already has
    IG_SESSIONID, and saved/private posts are unreachable by anonymous yt-dlp),
    falling back to yt-dlp (public posts, or when IG_SESSIONID is unset).
    """
    url = message.get("url", "")
    pk = message.get("ig_pk", "")
    if pk:
        try:
            IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            from minimax_mcp import ig_sync

            client = ig_sync.make_client()
            client.delay_range = [0.5, 1.0]
            method, target = _pick_download_target(client, pk)
            out = getattr(client, method)(target, folder=str(IG_DOWNLOADS_DIR))
            if out and Path(out).exists():
                return {"ok": True, "filepath": str(Path(out))}
        except Exception as e:
            logger.warning("instagrapi download failed for %s: %s", pk, e)

    from minimax_mcp.downloader import VideoDownloader

    IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=IG_DOWNLOADS_DIR, browser="chrome")
    return downloader.download(url)


def _default_transcribe(filepath: str) -> dict:
    from minimax_mcp.transcriber import AudioTranscriber

    transcriber = AudioTranscriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE)
    try:
        return transcriber.transcribe(filepath)
    finally:
        # Release the Whisper VRAM right after transcribing, before the LLM
        # step: lfm2:24b needs ~6 GB and the worker runs on the same 12 GB GPU
        # as ComfyUI. Otherwise the next knowledge call 500s with cudaMalloc
        # out-of-memory until a retry happens to run after the cache cleared.
        #
        # Guarded because this runs in a `finally`: an exception raised here
        # would replace the transcription we just spent minutes producing, and
        # the message would be nacked and redone. Failing to free is worth a
        # warning, never worth discarding the work.
        try:
            transcriber.free()
        except Exception:
            logger.warning("could not release Whisper VRAM", exc_info=True)


def _safe_ack(ch, method) -> None:
    """Ack a delivery, swallowing channel/connection errors (e.g. the broker
    closed the transport while a long LLM/Whisper step was running). If the
    connection died the message is left unacked and RabbitMQ redelivers it once
    the worker reconnects."""
    try:
        ch.basic_ack(method.delivery_tag)
    except Exception as exc:  # noqa: BLE001 - connection-level errors
        logger.warning("ack failed for delivery_tag=%s (%s); will redeliver", method.delivery_tag, exc)


def run() -> None:
    """Daemon main: connect, declare, consume ig.saved + control queue.

    The connection can drop (heartbeat timeout, broker restart) while a long
    Whisper/LLM step is running; the old code crashed the whole daemon with
    StreamLostError on the post-processing ack, orphaning queued messages.
    This loop reconnects with backoff and keeps the item-paused state across
    connections.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    state = {"paused": False}

    def on_work(ch, method, properties, body):
        parsed = ig_queue.parse_message(body)
        if not parsed["ok"]:
            logger.warning("corrupted message -> DLQ: %s", parsed["error"])
            try:
                ig_queue.dead_letter(ch, properties, body)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dead_letter failed: %s", exc)
            _safe_ack(ch, method)
            return

        message = parsed["message"]
        session = db.get_session()
        try:
            already = db.document_exists(session, ig_pk=message.get("ig_pk"))
        finally:
            session.close()
        if already:
            logger.info("duplicate ig_pk=%s -> ack without processing", message["ig_pk"])
            _safe_ack(ch, method)
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
            _safe_ack(ch, method)
        else:
            logger.warning("processing failed ig_pk=%s: %s", message["ig_pk"], res["error"])
            try:
                ig_queue.handle_failure(ch, properties, body)
            except Exception as exc:  # noqa: BLE001
                logger.warning("handle_failure failed: %s", exc)
            _safe_ack(ch, method)

    def on_control(ch, method, properties, body):
        import json

        try:
            command = json.loads(body).get("command", "")
        except (ValueError, TypeError):
            command = ""
        logger.info("control command: %s", apply_command(state, command))
        _safe_ack(ch, method)

    def consume_once() -> None:
        """Connect and consume until the connection dies; returns on error."""
        connection = ig_queue.connect()
        try:
            channel = connection.channel()
            ig_queue.declare(channel)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=ig_queue.QUEUE, on_message_callback=on_work)
            channel.basic_consume(queue=ig_queue.CONTROL_QUEUE, on_message_callback=on_control)
            logger.info("ig-worker consuming %s (paused=%s)", ig_queue.QUEUE, state["paused"])
            channel.start_consuming()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - connection-level errors
            logger.warning("consumer connection dropped: %s", exc)
        finally:
            ig_queue.close(connection)

    backoff = 1
    while True:
        try:
            consume_once()
        except KeyboardInterrupt:
            break
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)
        logger.info("reconnecting in %ss...", backoff)


if __name__ == "__main__":
    run()
