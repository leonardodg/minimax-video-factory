#!/usr/bin/env bash
# tests/03_models.sh — model files present with expected sizes in the right dirs.
# Reads the configured model set from .env (via config.sh) so it also validates
# bigger variants (MODEL_DIFFUSION / MODEL_TEXT_ENCODER / *_BYTES overrides).
set -u
FAIL=0
if [ -f "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh"
fi

echo "== Models ($MODELS_DIR) =="

# Configured model set (name -> expected bytes; empty = skip size check)
declare -A EXPECTED=(
    ["diffusion_models/$MODEL_DIFFUSION"]=$MODEL_DIFFUSION_BYTES
    ["text_encoders/$MODEL_TEXT_ENCODER"]=$MODEL_TEXT_ENCODER_BYTES
    ["vae/$MODEL_VIDEO_VAE"]=$MODEL_VIDEO_VAE_BYTES
    ["vae/$MODEL_AUDIO_VAE"]=$MODEL_AUDIO_VAE_BYTES
)

for rel in "${!EXPECTED[@]}"; do
    f="$MODELS_DIR/$rel"
    if [ -f "$f" ]; then
        size=$(stat -c %s "$f")
        exp=${EXPECTED[$rel]}
        if [ -z "$exp" ]; then
            echo "  [ok]   $rel ($(numfmt --to=iec "$size" 2>/dev/null || echo "$size B")) [size unchecked]"
            continue
        fi
        # allow +/- 2% size tolerance (block-size rounding)
        lo=$(( exp * 98 / 100 )); hi=$(( exp * 102 / 100 ))
        if [ "$size" -ge "$lo" ] && [ "$size" -le "$hi" ]; then
            echo "  [ok]   $rel ($(numfmt --to=iec "$size" 2>/dev/null || echo "$size B"))"
        else
            echo "  [BAD]  $rel size=$size (expected ~$exp) — corrupt/incomplete, re-run download_models.sh"
            FAIL=$((FAIL+1))
        fi
    else
        echo "  [MISS] $rel not found"
        FAIL=$((FAIL+1))
    fi
done

exit "$FAIL"
