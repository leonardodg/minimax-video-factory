#!/usr/bin/env bash
# mcp_runner.sh — run the MiniMax Video Factory MCP server INSIDE the container.
# Host-side entry:  docker compose -f docker/docker-compose.yml exec -T comfyui bash /workspace/scripts/mcp_runner.sh
# Uses the in-image venv (/opt/mcp-venv, built by the Dockerfile); /workspace is
# the live bind-mount of the repo (env vars come from docker-compose.yml).
set -euo pipefail
cd /workspace
export PYTHONPATH=/workspace/src:${PYTHONPATH:-}
export MCP_TRANSPORT=stdio
exec /opt/mcp-venv/bin/python -m minimax_mcp.server
