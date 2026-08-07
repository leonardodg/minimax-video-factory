"""Pytest entrypoints for the ok()/bad()-style smoke scripts under tests/, so
`pytest -m unit` / `-m integration_db` / `-m integration_llm` work for
selective/CI-friendly runs without rewriting each script's internals."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_script(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tests" / name)],
        cwd=ROOT, capture_output=True, text=True,
    )


@pytest.mark.unit
def test_unit_pure():
    result = _run_script("unit_pure.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_knowledge():
    result = _run_script("unit_knowledge.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_db
def test_integration_knowledge_db():
    result = _run_script("integration_knowledge_db.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_llm
def test_integration_knowledge_llm():
    result = _run_script("integration_knowledge_llm.py")
    assert result.returncode == 0, result.stdout + result.stderr
