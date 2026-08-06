#!/usr/bin/env bash
# start_comfyui.sh — build (if needed) + start ComfyUI container with GPU
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

docker compose $COMPOSE_ARGS up -d --build
echo ""
echo "ComfyUI starting at $COMFYUI_URL ..."
for i in $(seq 1 60); do
    if curl -sf --max-time 2 "$COMFYUI_URL/system_stats" >/dev/null 2>&1; then
        echo "Ready: $COMFYUI_URL/system_stats"
        exit 0
    fi
    sleep 2
done
echo "Timed out waiting for ComfyUI at $COMFYUI_URL" >&2
exit 1
