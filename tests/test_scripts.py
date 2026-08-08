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
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


@pytest.mark.unit
def test_unit_pure():
    result = _run_script("unit_pure.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_knowledge():
    result = _run_script("unit_knowledge.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_orchestrator():
    result = _run_script("unit_orchestrator.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_core():
    result = _run_script("unit_core.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_registry():
    result = _run_script("unit_registry.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_db():
    result = _run_script("unit_db.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_defaults():
    result = _run_script("unit_defaults.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_commands():
    result = _run_script("unit_commands.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_privacy():
    result = _run_script("unit_privacy.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_ig_queue():
    result = _run_script("unit_ig_queue.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_db
def test_container_deps():
    """The image the README tells users to configure must be able to import
    every tool. Marked integration_db only because it needs Docker up; it
    touches no database itself."""
    result = subprocess.run(
        ["bash", str(ROOT / "tests" / "09_container_deps.sh")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode == 78:
        pytest.skip(result.stdout.strip().splitlines()[-1] if result.stdout else "skipped")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_db
def test_integration_knowledge_db():
    result = _run_script("integration_knowledge_db.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration_llm
def test_integration_knowledge_llm():
    result = _run_script("integration_knowledge_llm.py")
    assert result.returncode == 0, result.stdout + result.stderr
