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


# Sem heartbeat. NAO e negligencia -- e o unico valor que funciona aqui.
#
# O pika negocia ~60 s por padrao, e uma BlockingConnection so responde ao
# heartbeat quando o processo devolve o controle ao seu laco de eventos. Este
# projeto e feito de trabalho bloqueante mais longo que isso:
#
#   enumerar uma colecao grande do Instagram   392 s (medido 2026-08-12)
#   transcrever um video de 75 s com Whisper   ~120 s
#   uma leitura de tela no modelo de visao     ~135 s
#
# O resultado media era o broker derrubar a conexao no meio do trabalho:
#
#   - a sincronizacao morria com `StreamLostError: Transport indicated EOF`
#     aos 392 s, depois de publicar 79 de ~3600 posts
#   - o ig-worker ficava `Up`, transcrevendo, com ZERO conexoes AMQP: a fila
#     acumulava 79 mensagens com 0 consumidores, e o ack no fim do processamento
#     falhava, devolvendo a mensagem para a fila
#
# Isso era anterior aos consertos do RABBITMQ_URL e da publicacao incremental,
# e por baixo deles: mesmo com tudo certo, a conexao caia sozinha.
#
# A alternativa seria chamar `process_data_events()` periodicamente durante o
# trabalho, o que exigiria enfiar o laco do pika dentro do Whisper e do Ollama.
# heartbeat=0 e o que a propria documentacao do RabbitMQ recomenda para
# consumidores de tarefa longa. A queda de conexao morta passa a ser detectada
# pelo TCP keepalive, mais lento e suficiente: o worker ja reconecta sozinho.
#
# O valor pode ser sobrescrito pela URL (`?heartbeat=30`), para quem quiser.
HEARTBEAT_PADRAO = 0
BLOCKED_TIMEOUT = int(os.environ.get("RABBITMQ_BLOCKED_TIMEOUT", "300"))


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(RABBITMQ_URL)
    if params.heartbeat is None:
        params.heartbeat = HEARTBEAT_PADRAO
    # Sem isto, um broker sob pressao de memoria (connection.blocked) deixa o
    # publisher pendurado para sempre em vez de levantar.
    if params.blocked_connection_timeout is None:
        params.blocked_connection_timeout = BLOCKED_TIMEOUT
    return pika.BlockingConnection(params)


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
