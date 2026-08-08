#!/usr/bin/env python3
"""Unit tests for ig_worker.py — injected download/transcribe/describe/ingest."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import ig_worker

MESSAGE = {
    "ig_pk": "1001", "media_type": "video",
    "url": "https://www.instagram.com/p/1001/", "title": "t",
    "owner_username": "u", "collection_name": None, "status": "queued",
}

print("== unit_ig_worker: classify_file ==")
if ig_worker.classify_file("x.mp4") == "video" and ig_worker.classify_file("x.jpg") == "image":
    ok("classify_file splits video/image by extension")
else:
    bad(f"classify_file = {ig_worker.classify_file('x.mp4')}/{ig_worker.classify_file('x.jpg')}")

print("== unit_ig_worker: process_message (video) ==")


def dl_video(msg):
    assert msg == MESSAGE
    return {"ok": True, "filepath": "/tmp/x.mp4"}


def tr(path):
    assert path == "/tmp/x.mp4"
    return {"ok": True, "text": "transcrito", "language": "pt"}


def ingest_ok(text, **kw):
    assert text == "transcrito"
    assert kw["doc_type"] == "video" and kw["ig_pk"] == "1001"
    return {"ok": True, "document_id": 42}


res = ig_worker.process_message(
    MESSAGE, download=dl_video, transcribe=tr, describe=None, ingest=ingest_ok
)
if res["status"] == "done" and res["document_id"] == 42 and res["kind"] == "video":
    ok("video message -> transcribe -> ingest -> done")
else:
    bad(f"video process = {res!r}")

print("== unit_ig_worker: process_message (image via describe) ==")


def dl_img(msg):
    return {"ok": True, "filepath": "/tmp/x.jpg"}


def describe(path):
    assert path == "/tmp/x.jpg"
    return {"ok": True, "text": "descrição da foto"}


def ingest_img(text, **kw):
    assert text == "descrição da foto"
    assert kw["doc_type"] == "image"
    return {"ok": True, "document_id": 43}


res = ig_worker.process_message(
    MESSAGE, download=dl_img, transcribe=None, describe=describe, ingest=ingest_img
)
if res["status"] == "done" and res["kind"] == "image":
    ok("image message -> describe -> ingest -> done")
else:
    bad(f"image process = {res!r}")

print("== unit_ig_worker: process_message (carousel -> first item) ==")


def dl_carousel(msg):
    assert msg["media_type"] == "carousel"
    return {"ok": True, "filepath": "/tmp/first.mp4"}


def tr_first(path):
    assert path == "/tmp/first.mp4"
    return {"ok": True, "text": "transcrito", "language": "pt"}


res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_carousel, transcribe=tr_first, describe=describe, ingest=ingest_ok,
)
if res["status"] == "done" and res["kind"] == "video":
    ok("carousel message is processed via its first downloaded item")
else:
    bad(f"carousel process = {res!r}")

print("== unit_ig_worker: process_message (failures) ==")
if ig_worker.process_message(MESSAGE, download=lambda m: {"ok": False, "error": "x"},
                             transcribe=tr, describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("download failure -> error status")
else:
    bad("download failure not reported")

if ig_worker.process_message(MESSAGE, download=dl_video,
                             transcribe=lambda p: {"ok": False, "error": "t"},
                             describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("transcribe failure -> error status")
else:
    bad("transcribe failure not reported")

print("== unit_ig_worker: apply_command ==")
state = {"paused": True}
if ig_worker.apply_command(state, "start") == "resumed" and state["paused"] is False:
    ok("start resumes a paused worker")
else:
    bad(f"apply_command(start) = {ig_worker.apply_command(state, 'start')}")
if ig_worker.apply_command(state, "stop") == "paused" and state["paused"] is True:
    ok("stop pauses a running worker")
else:
    bad("apply_command(stop) did not pause")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
