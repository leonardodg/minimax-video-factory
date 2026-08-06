#!/usr/bin/env bash
# config.sh — shared environment for all scripts, tests and the Docker stack.
# Loads .env (project root) and exports normalized variables. Override any value
# by setting it in .env or in the calling shell.
#
# Loaded with: source scripts/config.sh   (uses BASH_SOURCE location)

CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$CONFIG_DIR/.." && pwd)"

# --- load .env (project root) if present ---
# Parse line-by-line (not `source`): values may contain spaces/`--` flags, and
# docker compose reads the same file with the same semantics (whole line = value).
if [ -f "$PROJECT_ROOT/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#"${line%%[![:space:]]*}"}"     # trim leading whitespace
        [ -z "$line" ] && continue
        case "$line" in \#*) continue ;; esac        # skip comments
        case "$line" in
            *=*)
                key="${line%%=*}"
                value="${line#*=}"
                value="${value%"${value##*[![:space:]]}"}"  # trim trailing ws
                # strip matching surrounding quotes, if any
                case "$value" in
                    \"*\") value="${value%\"}"; value="${value#\"}" ;;
                    \'*\') value="${value%\'}"; value="${value#\'}" ;;
                esac
                export "$key=$value"
                ;;
        esac
    done < "$PROJECT_ROOT/.env"
fi

# --- ComfyUI ---
export COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"
export COMFYUI_PORT="${COMFYUI_PORT:-8188}"
export COMFY_CONTAINER="${COMFY_CONTAINER:-minimax-comfyui}"
export COMFY_IMAGE="${COMFY_IMAGE:-minimax-comfyui:local}"
export COMFYUI_TAG="${COMFYUI_TAG:-v0.30.2}"
export COMFYUI_EXTRA_ARGS="${COMFYUI_EXTRA_ARGS:---lowvram --fast-disk --disable-pinned-memory}"

# --- Models directory ---
# Prefer /opt/minimax/models (documented); fall back to a writable path on the /
# partition if /opt is not user-writable (no sudo in non-interactive shells).
# Override freely via MODELS_DIR in .env — disk space is often the constraint.
if [ -z "${MODELS_DIR:-}" ]; then
    if [ -w /opt/minimax/models ]; then
        export MODELS_DIR="/opt/minimax/models"
    else
        export MODELS_DIR="/var/tmp/minimax/models"
        echo "[config] /opt/minimax/models not writable; using $MODELS_DIR" >&2
    fi
fi

# --- Output / input dirs ---
export OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/output}"
export INPUT_DIR="${INPUT_DIR:-$PROJECT_ROOT/input}"
export OUTPUT_PREFIX="${OUTPUT_PREFIX:-video/factory}"

# --- Model set (supports bigger variants; sizes optional -> size checks skipped) ---
export MODEL_REPO_INT4="${MODEL_REPO_INT4:-Merserk/MiniMax-H3-INT4-ConvRot}"
export MODEL_REPO_COMFY="${MODEL_REPO_COMFY:-Comfy-Org/MiniMax-H3}"
export MODEL_DIFFUSION="${MODEL_DIFFUSION:-minimax_h3_fl2va_pruned_int4_convrot.safetensors}"
export MODEL_TEXT_ENCODER="${MODEL_TEXT_ENCODER:-qwen3vl_32b_minimax_h3_int4_convrot.safetensors}"
export MODEL_VIDEO_VAE="${MODEL_VIDEO_VAE:-minimax_h3_video_vae_fp16.safetensors}"
export MODEL_AUDIO_VAE="${MODEL_AUDIO_VAE:-minimax_h3_audio_vae_fp32.safetensors}"
# expected byte sizes (empty = skip size check)
export MODEL_DIFFUSION_BYTES="${MODEL_DIFFUSION_BYTES:-}"
export MODEL_TEXT_ENCODER_BYTES="${MODEL_TEXT_ENCODER_BYTES:-}"
export MODEL_VIDEO_VAE_BYTES="${MODEL_VIDEO_VAE_BYTES:-}"
export MODEL_AUDIO_VAE_BYTES="${MODEL_AUDIO_VAE_BYTES:-}"

# --- Workflows / MCP ---
export WORKFLOW="${WORKFLOW:-$PROJECT_ROOT/workflows/minimax_h3_t2v_api.json}"
export COMFYUI_OUTPUT="${COMFYUI_OUTPUT:-$OUTPUT_DIR}"   # host-visible output dir

# --- Docker Hub ---
export DOCKER_HUB_USER="${DOCKER_HUB_USER:-leonardodg}"
export DOCKER_HUB_REPO="${DOCKER_HUB_REPO:-minimax-video-factory}"

# --- Derived ---
export COMFYUI_COMPOSE_FILE="${COMFYUI_COMPOSE_FILE:-$PROJECT_ROOT/docker/docker-compose.yml}"
export COMFYUI_URL="http://127.0.0.1:${COMFYUI_PORT}"
# docker compose must read the project-root .env (not docker/.env) and resolve
# relative paths against the project root. Single source of compose args for all scripts.
export COMPOSE_ARGS="--project-directory $PROJECT_ROOT --env-file $PROJECT_ROOT/.env -f $COMFYUI_COMPOSE_FILE"
export MCP_TRANSPORT="${MCP_TRANSPORT:-stdio}"    # stdio | http | streamable-http | sse
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8848}"
