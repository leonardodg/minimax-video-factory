#!/usr/bin/env bash
# mcp_http_runner.sh — run the MiniMax Video Factory MCP server INSIDE the container
# over HTTP (streamable-http by default) so it can be exposed on a port / reverse-proxied
# with TLS for remote (VPS) access.
#   docker compose -f docker/docker-compose.yml exec -T comfyui bash /workspace/scripts/mcp_http_runner.sh
# Reads MCP_TRANSPORT / MCP_HOST / MCP_PORT from the container env (compose/.env).
set -euo pipefail
cd /workspace
export PYTHONPATH=/workspace/src:${PYTHONPATH:-}
export MCP_TRANSPORT="${MCP_TRANSPORT:-streamable-http}"
# nvidia-* pip libs bundled in the venv (cu12 cublas/cudnn) — required by
# ctranslate2/faster-whisper for GPU transcription (libcublas.so.12).
NVIDIA_DIR="/opt/mcp-venv/lib/python3.11/site-packages/nvidia"
export LD_LIBRARY_PATH="${NVIDIA_DIR}/cublas/lib:${NVIDIA_DIR}/cudnn/lib:${LD_LIBRARY_PATH:-}"
exec /opt/mcp-venv/bin/python -m minimax_mcp.server
