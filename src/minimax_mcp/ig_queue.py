"""RabbitMQ abstraction for the Instagram saved-posts sync.

Declares the durable work queue (ig.saved) with a dead-letter queue
(ig.saved.dead), publishes messages, parses+validates them, and implements the
attempts/DLQ retry policy. No business logic here — unit-tested with a fake
channel (see tests/unit_ig_queue.py).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE = os.environ.get("RABBITMQ_QUEUE", "ig.saved")
DLQ = f"{QUEUE}.dead"
CONTROL_QUEUE = "ig.worker.command"
MAX_ATTEMPTS = int(os.environ.get("IG_MAX_ATTEMPTS", "3"))

REQUIRED_KEYS = {"ig_pk", "media_type", "url", "title", "owner_username", "collection_name", "status"}


def connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))


def close(connection: pika.BlockingConnection | None) -> None:
    if connection is not None:
        try:
            connection.close()
        except Exception as exc:
            # Closing a connection the broker already dropped raises, and there
            # is nothing left to do about it -- but swallowing it silently hid
            # exactly the transport drops the worker was reconnecting around.
            logger.debug("ignoring error while closing connection: %s", exc)


def declare(channel: Any) -> None:
    """Declare work queue (durable, dead-letters to DLQ), DLQ, control queue."""
    channel.queue_declare(
        queue=QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": DLQ},
    )
    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_declare(queue=CONTROL_QUEUE, durable=False)


def publish(channel: Any, message: dict) -> None:
    """Publish a durable message to ig.saved with attempts=0."""
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": 0}),
    )


def parse_message(body: bytes) -> dict:
    """Validate a queue body against the message contract.

    Returns {"ok": True, "message": {...}} or {"ok": False, "error": ...}.
    """
    try:
        msg = json.loads(body)
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid json"}
    if not isinstance(msg, dict):
        return {"ok": False, "error": "message is not an object"}
    missing = sorted(REQUIRED_KEYS - set(msg))
    if missing:
        return {"ok": False, "error": f"missing keys {missing}"}
    return {"ok": True, "message": msg}


def attempts_of(properties: Any) -> int:
    """Read the attempts header, defaulting to 0."""
    headers = getattr(properties, "headers", None) or {}
    try:
        return int(headers.get("attempts", 0))
    except (TypeError, ValueError):
        return 0


def handle_failure(channel: Any, properties: Any, body: bytes) -> str:
    """Retry policy for a processing failure.

    Re-publishes to ig.saved with attempts+1 while under MAX_ATTEMPTS, else
    re-publishes to the DLQ. Returns "requeue" or "dead". The caller acks the
    original delivery after this (the copy is the retry).
    """
    attempts = attempts_of(properties)
    if attempts + 1 >= MAX_ATTEMPTS:
        channel.basic_publish(
            exchange="",
            routing_key=DLQ,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts + 1}),
        )
        return "dead"
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts + 1}),
    )
    return "requeue"


def dead_letter(channel: Any, properties: Any, body: bytes) -> None:
    """Publish a message straight to the DLQ (corrupted bodies only).

    Unlike handle_failure this never bumps attempts and never requeues —
    a corrupted message goes to the DLQ exactly once.
    """
    channel.basic_publish(
        exchange="",
        routing_key=DLQ,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, headers={"attempts": attempts_of(properties) + 1}),
    )


def queue_status(channel: Any) -> dict:
    """Passive-declare ig.saved + DLQ and report message/consumer counts."""
    work = channel.queue_declare(queue=QUEUE, durable=True, passive=True)
    dead = channel.queue_declare(queue=DLQ, durable=True, passive=True)
    return {
        "ok": True,
        "queue": QUEUE,
        "ready": int(work.method.message_count),
        "dead": int(dead.method.message_count),
        "consumers": int(work.method.consumer_count),
    }
