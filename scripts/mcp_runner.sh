#!/usr/bin/env bash
# mcp_runner.sh — run the MiniMax Video Factory MCP server INSIDE the container.
# Host-side entry:  docker compose -f docker/docker-compose.yml exec -T comfyui bash /workspace/scripts/mcp_runner.sh
# Uses the in-image venv (/opt/mcp-venv, built by the Dockerfile); /workspace is
# the live bind-mount of the repo (env vars come from docker-compose.yml).
set -euo pipefail
cd /workspace
export PYTHONPATH=/workspace/src:${PYTHONPATH:-}
export MCP_TRANSPORT=stdio
# nvidia-* pip libs bundled in the venv (cu12 cublas/cudnn) — required by
# ctranslate2/faster-whisper for GPU transcription (libcublas.so.12).
NVIDIA_DIR="/opt/mcp-venv/lib/python3.11/site-packages/nvidia"
export LD_LIBRARY_PATH="${NVIDIA_DIR}/cublas/lib:${NVIDIA_DIR}/cudnn/lib:${LD_LIBRARY_PATH:-}"
exec /opt/mcp-venv/bin/python -m minimax_mcp.server
