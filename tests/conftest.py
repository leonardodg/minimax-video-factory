"""Shared pytest fixtures: auto-skip integration tests when their service is unreachable."""
from __future__ import annotations

import os
import socket

import pytest


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    postgres_up = _port_open("127.0.0.1", int(os.environ.get("KB_POSTGRES_PORT", "5432")))
    ollama_up = _port_open("127.0.0.1", 11434)

    skip_db = pytest.mark.skip(
        reason="Postgres not reachable on KB_POSTGRES_PORT (docker compose up -d postgres)"
    )
    skip_llm = pytest.mark.skip(reason="Ollama not reachable on :11434")

    for item in items:
        if "integration_db" in item.keywords and not postgres_up:
            item.add_marker(skip_db)
        if "integration_llm" in item.keywords and not ollama_up:
            item.add_marker(skip_llm)
