#!/usr/bin/env bash
# install_custom_nodes.sh — install/update the ComfyUI custom node packs the
# MiniMax-H3 Turbo + AcademiaSD all-in-one workflows need.
#
# Clones into $CUSTOM_NODES_DIR on the HOST (bind-mounted read-write over
# /comfy/ComfyUI/custom_nodes by docker/docker-compose.yml), then installs each
# pack's Python requirements INSIDE the running container, where ComfyUI's
# interpreter lives.
#
# Why the host dir at all: without the mount, custom_nodes sits inside the image
# and every `docker compose build` wipes every installed node.
#
# Usage:
#   scripts/install_custom_nodes.sh            # clone/update + install deps
#   scripts/install_custom_nodes.sh --no-deps  # clone/update only
#   scripts/install_custom_nodes.sh --deps-only
#
# Afterwards, recreate the container so the mount and the nodes take effect:
#   docker compose -f docker/docker-compose.yml --project-directory . up -d
set -uo pipefail

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

CUSTOM_NODES_DIR="${CUSTOM_NODES_DIR:-/opt/minimax/custom_nodes}"
COMFY_CONTAINER="${COMFY_CONTAINER:-minimax-comfyui}"

DO_CLONE=1
DO_DEPS=1
case "${1:-}" in
  --no-deps)   DO_DEPS=0 ;;
  --deps-only) DO_CLONE=0 ;;
  "")          ;;
  *) echo "uso: $0 [--no-deps|--deps-only]" >&2; exit 2 ;;
esac

# Pack list. MiniMax-H3-Turbo is the only one strictly required for turbo
# rendering; the rest are what AcademiaSD's all-in-one workflow wires together.
#   rgthree-comfy ............ Fast Groups Bypasser, Image Comparer
#   ComfyUI-Impact-Pack ...... ImpactSwitch (the T2V/I2V/Ref2V mode switch)
#   VideoHelperSuite ......... VHS_VideoCombine, VHS_LoadVideo, VHS_LoadAudioUpload
#   Frame-Interpolation ...... RIFE VFI (interpolates 24 -> 48 fps)
#   KJNodes .................. ModelPreviewOverrideKJ (TAE preview), the two Sage
#                              Attention patch nodes
#   ComfyUI-Easy-Use ......... easy cleanGpuUsed / clearCacheAll / showAnything
#   comfyui_AcademiaSD ....... the AcademiaSD_* nodes and the workflows themselves
REPOS=(
  "https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo"
  "https://github.com/AcademiaSD/comfyui_AcademiaSD"
  "https://github.com/rgthree/rgthree-comfy"
  "https://github.com/ltdrdata/ComfyUI-Impact-Pack"
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
  "https://github.com/Fannovel16/ComfyUI-Frame-Interpolation"
  "https://github.com/kijai/ComfyUI-KJNodes"
  "https://github.com/yolain/ComfyUI-Easy-Use"
)

fail=0

if [ "$DO_CLONE" = 1 ]; then
  mkdir -p "$CUSTOM_NODES_DIR"

  # Seed from the image on first run: ComfyUI ships websocket_image_save.py in
  # custom_nodes, and mounting an empty dir over it would hide it.
  if [ ! -e "$CUSTOM_NODES_DIR/websocket_image_save.py" ]; then
    echo "==> semeando $CUSTOM_NODES_DIR a partir da imagem"
    docker cp "$COMFY_CONTAINER:/comfy/ComfyUI/custom_nodes/." "$CUSTOM_NODES_DIR/" \
      || echo "    (container fora do ar; siga, mas confira o seed depois)"
  fi

  for repo in "${REPOS[@]}"; do
    name="$(basename "$repo")"
    dest="$CUSTOM_NODES_DIR/$name"
    if [ -d "$dest/.git" ]; then
      echo "==> atualizando $name"
      git -C "$dest" pull --ff-only -q || { echo "    FALHOU o pull de $name"; fail=1; }
    else
      echo "==> clonando $name"
      git clone --depth 1 -q "$repo" "$dest" || { echo "    FALHOU o clone de $name"; fail=1; }
    fi
  done
fi

if [ "$DO_DEPS" = 1 ]; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$COMFY_CONTAINER"; then
    echo "!! container '$COMFY_CONTAINER' não está de pé — suba-o e rode: $0 --deps-only" >&2
    exit 1
  fi
  # ComfyUI runs on the image's conda python, NOT the /opt/mcp-venv used by the
  # MCP server. Installing into the wrong one leaves the nodes importable-but-broken.
  echo "==> instalando dependências no python do ComfyUI (dentro do container)"
  docker exec "$COMFY_CONTAINER" bash -lc '
    set -uo pipefail
    PY=/opt/conda/bin/python
    rc=0
    for req in /comfy/ComfyUI/custom_nodes/*/requirements.txt; do
      [ -e "$req" ] || continue
      pack=$(basename "$(dirname "$req")")
      # Impact-Pack pulls SAM2 from git (heavy, and only its segmentation nodes
      # need it). The all-in-one uses ImpactSwitch, which does not. Skip the git
      # dependency and install the rest.
      echo "--- $pack"
      grep -v "^git+" "$req" | grep -v "^\s*$" > /tmp/req.txt
      $PY -m pip install --no-cache-dir -q -r /tmp/req.txt || { echo "    FALHOU: $pack"; rc=1; }
    done
    # Frame-Interpolation ships requirements-with-cupy.txt / -no-cupy.txt instead
    # of requirements.txt. cupy-wheel compiles against the local CUDA and is only
    # needed by a few VFI models; RIFE runs without it.
    fi_dir=/comfy/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation
    if [ -f "$fi_dir/requirements-no-cupy.txt" ]; then
      echo "--- ComfyUI-Frame-Interpolation (sem cupy)"
      $PY -m pip install --no-cache-dir -q -r "$fi_dir/requirements-no-cupy.txt" \
        || { echo "    FALHOU: Frame-Interpolation"; rc=1; }
    fi
    exit $rc
  ' || fail=1
fi

echo
echo "=== pacotes em $CUSTOM_NODES_DIR ==="
ls -1 "$CUSTOM_NODES_DIR"
if [ "$fail" = 0 ]; then
  echo "custom nodes prontos"
else
  echo "custom nodes TERMINARAM COM FALHA — leia o log acima"
  exit 1
fi
