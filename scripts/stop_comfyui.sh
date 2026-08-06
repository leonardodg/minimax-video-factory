#!/usr/bin/env bash
# stop_comfyui.sh — stop the ComfyUI container (keeps image/models)
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

docker compose $COMPOSE_ARGS down
