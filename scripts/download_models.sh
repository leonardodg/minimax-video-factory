#!/usr/bin/env bash
# download_models.sh — download the MiniMax H3 model set (INT4 pruned by default,
# or a bigger variant via .env overrides: MODEL_DIFFUSION, MODEL_TEXT_ENCODER, *_BYTES).
# Public HF repos (gated:false). Total ~32 GB for INT4.
# Saves into: $MODELS_DIR (set MODELS_DIR in .env for disk-space control) under
# diffusion_models/, text_encoders/, vae/. Resumes partial downloads and skips
# files whose size already matches.
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

HF_BASE="https://huggingface.co"
MODELS_DIR="${MODELS_DIR:-/opt/minimax/models}"

# subdir | remote repo | remote path | local filename | expected bytes (empty=skip size check)
# Remote paths verified via https://huggingface.co/api/models/<repo>?blobs=true
# NOTE: the VAEs live in a vae/ subfolder on Comfy-Org/MiniMax-H3 (a bare filename 404s).
FILES=(
  "diffusion_models|$MODEL_REPO_INT4|$MODEL_DIFFUSION|$MODEL_DIFFUSION|$MODEL_DIFFUSION_BYTES"
  "text_encoders|$MODEL_REPO_INT4|$MODEL_TEXT_ENCODER|$MODEL_TEXT_ENCODER|$MODEL_TEXT_ENCODER_BYTES"
  "vae|$MODEL_REPO_COMFY|vae/$MODEL_VIDEO_VAE|$MODEL_VIDEO_VAE|$MODEL_VIDEO_VAE_BYTES"
  "vae|$MODEL_REPO_COMFY|vae/$MODEL_AUDIO_VAE|$MODEL_AUDIO_VAE|$MODEL_AUDIO_VAE_BYTES"
)

mkdir -p "$MODELS_DIR"/{diffusion_models,text_encoders,vae}

for entry in "${FILES[@]}"; do
  subdir="${entry%%|*}"
  rest="${entry#*|}"
  repo="${rest%%|*}"
  rest2="${rest#*|}"
  remote="${rest2%%|*}"
  rest3="${rest2#*|}"
  fname="${rest3%%|*}"
  expect="${rest3##*|}"
  outdir="$MODELS_DIR/$subdir"
  url="$HF_BASE/$repo/resolve/main/$remote?download=true"
  out="$outdir/$fname"
  mkdir -p "$outdir"

  # Only skip when the existing file already has the expected size (resume otherwise).
  # When no expected size is configured, skip an existing non-empty file.
  if [ -f "$out" ]; then
    have=$(stat -c%s "$out" 2>/dev/null || echo 0)
    if [ -n "$expect" ] && [ "$have" -ge "$expect" ]; then
      echo "[skip] $fname already complete ($(du -h "$out" | cut -f1))"
      continue
    fi
    if [ -z "$expect" ] && [ "$have" -gt 0 ]; then
      echo "[skip] $fname exists ($(du -h "$out" | cut -f1)); no size configured, assuming OK"
      continue
    fi
    echo "[resume] $fname at $have/${expect:-unknown} bytes"
  fi

  echo "[get]  $url"
  curl -fL --retry 3 --retry-delay 5 -C - -o "$out" "$url"
  echo "[done] $out ($(du -h "$out" | cut -f1))"
done

echo ""
echo "Download complete. Verify with: ./scripts/diagnose.sh 03"
