#!/usr/bin/env bash
# publish_image.sh — build the dockerized stack (ComfyUI + in-image MCP) and push
# it to Docker Hub so users only need `docker pull` + a .env + models dir.
#
#   DOCKER_HUB_USER=leonardodg  (in .env / config.sh)
#   DOCKER_HUB_REPO=minimax-video-factory
#
# Usage: ./scripts/publish_image.sh [TAG]   (default tag = latest)
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

TAG="${1:-latest}"
NAME="$DOCKER_HUB_USER/$DOCKER_HUB_REPO:$TAG"

echo "== Building $COMFY_IMAGE (local test build) =="
docker build -t "$COMFY_IMAGE" \
  --build-arg COMFYUI_TAG="$COMFYUI_TAG" \
  -f "$PROJECT_ROOT/docker/Dockerfile" "$PROJECT_ROOT"

echo "== Tagging $NAME =="
docker tag "$COMFY_IMAGE" "$NAME"

echo "== Pushing $NAME =="
docker push "$NAME"

echo ""
echo "Done. Users pull with:  docker pull $NAME"
echo "Then follow docs/INSTALLATION.md (compose file uses .env: COMFY_IMAGE=$NAME)."
