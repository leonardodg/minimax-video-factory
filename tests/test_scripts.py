"""Pytest entrypoints for the ok()/bad()-style smoke scripts under tests/, so
`pytest -m unit` / `-m integration_db` work for selective/CI-friendly runs
without rewriting each script's internals."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_script(name: str) -> subprocess.CompletedProcess:
    # GPU_LOCK_DIR isolated per run: several unit_*.py scripts call
    # submit_scene_core with ComfyUIClient mocked but NOT gpu_lock -- without
    # this, they'd acquire() the real ~/.gpu-lock and can hang for real
    # minutes if insta_kb's ig-worker (or a render) happens to hold it at
    # the same time (found 2026-10-07, see docs/HANDOFF.md).
    with tempfile.TemporaryDirectory() as gpu_lock_dir:
        env = {**os.environ, "GPU_LOCK_DIR": gpu_lock_dir}
        return subprocess.run(
            [sys.executable, str(ROOT / "tests" / name)],
            cwd=ROOT, capture_output=True, text=True, check=False, env=env,
        )


@pytest.mark.unit
def test_unit_pure():
    result = _run_script("unit_pure.py")
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
def test_unit_transcriber():
    result = _run_script("unit_transcriber.py")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_unit_gpu_lock():
    result = _run_script("unit_gpu_lock.py")
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


