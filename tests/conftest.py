"""Shared pytest config.

No auto-skip fixture here anymore: the one remaining `integration_db` test
(test_container_deps) needs Docker, not Postgres -- it already self-skips
with returncode 78 when the comfyui container is not up (see
tests/09_container_deps.sh). The Postgres/Ollama auto-skip this file used to
provide was for the knowledge-base integration tests, migrated to insta_kb
in 2026-10-06.
"""
from __future__ import annotations
