#!/usr/bin/env bash
# tests/01_docker.sh — Docker image pulled, ComfyUI container running, GPU visible inside
set -u
FAIL=0

# Project config (shared with scripts) — source defaults
if [ -f "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh"
fi
COMFY_CONTAINER="${COMFY_CONTAINER:-minimax-comfyui}"
IMAGE_NAME="${IMAGE_NAME:-pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime}"

echo "== Docker + GPU =="

if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "  [ok]   base image present: $IMAGE_NAME"
else
    echo "  [MISS] base image not pulled: $IMAGE_NAME"
    FAIL=$((FAIL+1))
fi

if docker inspect "$COMFY_CONTAINER" >/dev/null 2>&1; then
    STATE=$(docker inspect -f '{{.State.Status}}' "$COMFY_CONTAINER")
    if [ "$STATE" = "running" ]; then
        echo "  [ok]   container '$COMFY_CONTAINER' running"
    else
        echo "  [MISS] container '$COMFY_CONTAINER' state=$STATE (not running)"
        FAIL=$((FAIL+1))
    fi
else
    echo "  [MISS] container '$COMFY_CONTAINER' does not exist — run: ./scripts/start_comfyui.sh"
    FAIL=$((FAIL+1))
fi

# GPU visible inside container
if GPUS=$(docker exec "$COMFY_CONTAINER" nvidia-smi -L 2>/dev/null); then
    echo "  [ok]   GPU inside container:"
    echo "$GPUS" | sed 's/^/        /'
else
    echo "  [MISS] nvidia-smi failed inside container (GPU not passed through?)"
    FAIL=$((FAIL+1))
fi

exit "$FAIL"
