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
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    """Download -> transcribe/describe -> ingest. Pure; all IO injected.

    Videos transcribe the first downloaded file. Images/carousels describe
    EVERY downloaded file and join their conteudo_principal into one text so
    content spread across carousel photos is captured. The first photo's
    categoria becomes a `categoria:<name>` tag.
    """
    if not message:
        return {"status": "error", "error": "empty message"}

    dl = download(message)
    if not dl.get("ok"):
        return {"status": "error", "error": dl.get("error", "download failed")}
    filepaths = dl.get("filepaths") or [dl.get("filepath")]
    filepaths = [f for f in filepaths if f]
    if not filepaths:
        return {"status": "error", "error": "no file downloaded"}

    kind = classify_file(filepaths[0])
    categoria = None
    if kind == "video":
        if transcribe is None:
            return {"status": "error", "error": "no transcribe provided for video"}
        tr = transcribe(filepaths[0])
        if not tr.get("ok"):
            return {"status": "error", "error": tr.get("error", "transcribe failed")}
        text, lang = tr["text"], tr.get("language", "pt")
        doc_type = "video"
    else:
        if describe is None:
            return {"status": "error", "error": "no describe provided for image"}
        pieces: list[str] = []
        for fp in filepaths:
            de = describe(fp)
            if not de.get("ok"):
                return {"status": "error", "error": de.get("error", "describe failed")}
            pieces.append(de.get("conteudo_principal") or de.get("text") or "")
            if categoria is None:
                categoria = de.get("categoria")
        text = "\n\n".join(p for p in pieces if p)
        lang = "pt"
        doc_type = "image"

    # Namespaced like `categoria:`: a bare collection name is indistinguishable
    # from a semantic tag the LLM produced, and it was landing on nearly every
    # document, so tag search could not tell "about Dev" from "filed under Dev".
    extra_tags = [f"colecao:{message['collection_name']}"] if message.get("collection_name") else None
    if categoria and categoria != "outros":
        extra_tags = (extra_tags or []) + [f"categoria:{categoria}"]
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

    return {
        "status": "done",
        "document_id": ing.get("document_id"),
        "kind": kind,
        "filepath": filepaths[0],
        "filepaths": filepaths,
    }


def apply_command(state: dict, command: str) -> str:
    """Handle a start/stop control message, mutating `state`."""
    if command == "start":
        state["paused"] = False
        return "resumed"
    if command == "stop":
        state["paused"] = True
        return "paused"
    return "unknown"


def _download_targets(client: Any, pk: str) -> list[tuple[str, str]]:
    """All (method, target_pk) download pairs for a post.

    Carousels (media_type 8) have no clip of their own — the pk is an album
    container and clip_download raises "Must been video". Return one pair per
    resource: clip_download for video resources, photo_download for photo
    resources, so the whole album is captured. Single media returns the pk.
    """
    info = client.media_info(pk)
    mtype = int(getattr(info, "media_type", 0) or 0)
    if mtype == 8:
        resources = list(getattr(info, "resources", None) or [])
        if not resources:
            return [("photo_download", pk)]
        pairs: list[tuple[str, str]] = []
        for r in resources:
            rm = int(getattr(r, "media_type", 0) or 0)
            pairs.append(("clip_download" if rm == 2 else "photo_download", str(r.pk)))
        return pairs
    if mtype == 1:
        return [("photo_download", pk)]
    return [("clip_download", pk)]


def _default_download(message: dict) -> dict:
    """Download the media for a saved post.

    Prefers the authenticated instagrapi client (the worker already has
    IG_SESSIONID, and saved/private posts are unreachable by anonymous yt-dlp),
    falling back to yt-dlp (public posts, or when IG_SESSIONID is unset).
    Carousels download every resource; the result exposes both `filepath`
    (first item) and `filepaths` (all items) for back-compat.
    """
    url = message.get("url", "")
    pk = message.get("ig_pk", "")
    if pk:
        try:
            IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            from minimax_mcp import ig_sync

            client = ig_sync.make_client()
            client.delay_range = [0.5, 1.0]
            filepaths: list[str] = []
            for method, target in _download_targets(client, pk):
                out = getattr(client, method)(target, folder=str(IG_DOWNLOADS_DIR))
                if out and Path(out).exists():
                    filepaths.append(str(Path(out)))
            if filepaths:
                return {"ok": True, "filepath": filepaths[0], "filepaths": filepaths}
        except Exception as e:
            logger.warning("instagrapi download failed for %s: %s", pk, e)

    from minimax_mcp.downloader import VideoDownloader

    IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=IG_DOWNLOADS_DIR, browser="chrome")
    dl = downloader.download(url)
    if dl.get("ok") and dl.get("filepath"):
        dl["filepaths"] = [dl["filepath"]]
    return dl


_categories_cache: list[str] | None = None


def _default_describe(filepath: str) -> dict:
    """Describe an image with the category vocabulary threaded in.

    Fetches the category list once per process and reuses it for every
    describe call, so the worker doesn't hit instagrapi per message.
    """
    global _categories_cache
    if _categories_cache is None:
        try:
            from minimax_mcp import ig_sync

            _categories_cache = ig_sync.list_categories(ig_sync.make_client())
        except Exception:
            _categories_cache = ig_sync.list_categories(None)
    return llm.describe_image(filepath, categories=_categories_cache)


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
    except Exception as exc:
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
            except Exception as exc:
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
            describe=_default_describe,
            ingest=knowledge.ingest_text,
        )
        if res["status"] == "done":
            logger.info("ingested ig_pk=%s document_id=%s", message["ig_pk"], res["document_id"])
            if IG_DELETE_AFTER_INGEST:
                for fp in res.get("filepaths") or [res.get("filepath")]:
                    try:
                        Path(fp).unlink(missing_ok=True)
                    except OSError:
                        logger.warning("could not delete %s", fp)
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
            except Exception as exc:
                # The progress file is a convenience for /ig-progress, not the
                # source of truth -- the document is already in the KB. Failing
                # to write it must not nack a message that actually succeeded.
                logger.warning("could not update the progress file: %s", exc)
            _safe_ack(ch, method)
        else:
            logger.warning("processing failed ig_pk=%s: %s", message["ig_pk"], res["error"])
            try:
                ig_queue.handle_failure(ch, properties, body)
            except Exception as exc:
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
        except Exception as exc:
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
