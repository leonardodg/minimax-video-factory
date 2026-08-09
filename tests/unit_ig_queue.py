#!/usr/bin/env python3
"""Unit tests for ig_queue.py — no real RabbitMQ; a fake channel records calls."""
from __future__ import annotations

import json
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


class FakeMethod:
    message_count = 0
    consumer_count = 0


class FakeDeclareResult:
    method = FakeMethod()


class FakeProperties:
    def __init__(self, headers=None):
        self.headers = headers or {}


class FakeChannel:
    def __init__(self):
        self.declared: list[tuple] = []
        self.published: list[tuple] = []
        self.acks: list[int] = []

    def queue_declare(self, queue, durable=False, arguments=None, passive=False):
        self.declared.append((queue, durable, arguments, passive))
        return FakeDeclareResult()

    def basic_publish(self, exchange="", routing_key="", body=b"", properties=None):
        h = properties.headers if properties is not None else None
        self.published.append((routing_key, body, h))

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)


from minimax_mcp import ig_queue


print("== unit_ig_queue: parse_message ==")
good = ig_queue.parse_message(
    json.dumps({
        "ig_pk": "123", "media_type": "video", "url": "https://instagram.com/p/123",
        "title": "t", "owner_username": "u", "collection_name": None, "status": "queued",
    }).encode()
)
if good.get("ok") and good["message"]["ig_pk"] == "123":
    ok("parse_message accepts a valid message")
else:
    bad(f"parse_message(valid) = {good!r}")

if not ig_queue.parse_message(b"not json").get("ok"):
    ok("parse_message rejects invalid JSON")
else:
    bad("parse_message accepted invalid JSON")

if not ig_queue.parse_message(b'{"ig_pk": "1"}').get("ok"):
    ok("parse_message rejects a message missing required keys")
else:
    bad("parse_message accepted a truncated message")

print("== unit_ig_queue: declare ==")
ch = FakeChannel()
ig_queue.declare(ch)
names = {d[0] for d in ch.declared}
if {ig_queue.QUEUE, ig_queue.DLQ, ig_queue.CONTROL_QUEUE} <= names:
    ok("declare creates queue, DLQ and control queue")
else:
    bad(f"declare created: {names}")

work_decl = [d for d in ch.declared if d[0] == ig_queue.QUEUE][0]
if work_decl[1] is True and work_decl[2].get("x-dead-letter-routing-key") == ig_queue.DLQ:
    ok("ig.saved is durable and dead-letters to the DLQ")
else:
    bad(f"ig.saved declare args = {work_decl!r}")

print("== unit_ig_queue: publish ==")
ch = FakeChannel()
ig_queue.publish(ch, {"ig_pk": "1", "media_type": "image", "url": "x"})
rk, body, headers = ch.published[0]
if rk == ig_queue.QUEUE and json.loads(body)["ig_pk"] == "1" and headers.get("attempts") == 0:
    ok("publish sends to ig.saved with attempts=0 header")
else:
    bad(f"publish = {ch.published!r}")

print("== unit_ig_queue: attempts_of ==")
if ig_queue.attempts_of(FakeProperties({"attempts": 2})) == 2:
    ok("attempts_of reads the header")
else:
    bad("attempts_of mis-read the header")
if ig_queue.attempts_of(FakeProperties({})) == 0 and ig_queue.attempts_of(FakeProperties(None)) == 0:
    ok("attempts_of defaults to 0")
else:
    bad("attempts_of default != 0")

print("== unit_ig_queue: handle_failure ==")
body = b'{"ig_pk": "1", "media_type": "video", "url": "x"}'

ch = FakeChannel()
r = ig_queue.handle_failure(ch, FakeProperties({"attempts": 0}), body)
if r == "requeue" and ch.published and ch.published[0][0] == ig_queue.QUEUE:
    h = ch.published[0][2]
    if h.get("attempts") == 1:
        ok("attempt 0 -> requeue with attempts=1")
    else:
        bad(f"requeue header attempts = {h}")
else:
    bad(f"handle_failure(attempts=0) = {r}, published={ch.published}")

ch = FakeChannel()
r = ig_queue.handle_failure(ch, FakeProperties({"attempts": 2}), body)
if r == "dead" and ch.published and ch.published[0][0] == ig_queue.DLQ:
    ok("attempts == MAX-1 -> dead-lettered to the DLQ")
else:
    bad(f"handle_failure(attempts=2) = {r}, published={ch.published}")

print("== unit_ig_queue: dead_letter ==")
ch = FakeChannel()
ig_queue.dead_letter(ch, FakeProperties({"attempts": 2}), body)
if ch.published and ch.published[0][0] == ig_queue.DLQ:
    ok("dead_letter publishes straight to the DLQ (no requeue)")
else:
    bad(f"dead_letter = {ch.published!r}")

print("== unit_ig_queue: queue_status ==")
ch = FakeChannel()
status = ig_queue.queue_status(ch)
if status.get("ok") and {"queue", "ready", "dead", "consumers"} <= set(status):
    ok("queue_status returns the expected keys")
else:
    bad(f"queue_status = {status!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
