#!/usr/bin/env bash
# tests/02_comfyui_api.sh — ComfyUI HTTP API healthy, version >= 0.30.0, H3 node present
set -u
FAIL=0
if [ -f "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh"
fi
COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"

echo "== ComfyUI API ($COMFYUI_URL) =="

# /system_stats
STATS=$(curl -sf --max-time 10 "$COMFYUI_URL/system_stats") || STATS=""
if [ -n "$STATS" ]; then
    echo "  [ok]   GET /system_stats reachable"
    VERSION=$(echo "$STATS" | jq -r '.system.comfyui_version // "unknown"' 2>/dev/null)
    echo "  [info] ComfyUI version: $VERSION"
    # Version check: extract numeric major.minor
    MAJOR=$(echo "$VERSION" | cut -d. -f1)
    MINOR=$(echo "$VERSION" | cut -d. -f2)
    VER_OK=1
    case "${MAJOR:-}" in
        ''|*[!0-9]*) VER_OK=0 ;;
        0) [ "${MINOR:-0}" -ge 30 ] || VER_OK=0 ;;
        [1-9]*) : ;;
        *) VER_OK=0 ;;
    esac
    if [ "$VER_OK" -eq 1 ]; then
        echo "  [ok]   version >= 0.30.0"
    elif [ "$VERSION" = "unknown" ]; then
        echo "  [WARN] could not parse version"
    else
        echo "  [MISS] version < 0.30.0 (MiniMax H3 needs >= 0.30.0)"
        FAIL=$((FAIL+1))
    fi
    DEVICES=$(echo "$STATS" | jq -c '.devices[]? | {name, vram_total}' 2>/dev/null)
    echo "  [info] devices: $DEVICES"
    echo "$STATS" | jq -e '.devices[0].name' >/dev/null 2>&1 && echo "  [ok]   GPU device exposed" || { echo "  [MISS] no GPU device in system_stats"; FAIL=$((FAIL+1)); }
else
    echo "  [MISS] /system_stats unreachable — ComfyUI not up at $COMFYUI_URL"
    FAIL=$((FAIL+1))
fi

# /object_info contains the MiniMax H3 node class
OI=$(curl -sf --max-time 20 "$COMFYUI_URL/object_info") || OI=""
if [ -n "$OI" ]; then
    echo "  [ok]   GET /object_info reachable"
    if echo "$OI" | jq -e 'has("4c314f31-ecda-4b08-ae98-faaba1bf613f")' >/dev/null 2>&1; then
        echo "  [ok]   MiniMax H3 T2V node present"
    elif echo "$OI" | jq -e 'keys | map(select(test("minimax"; "i"))) | length > 0' >/dev/null 2>&1; then
        echo "  [ok]   MiniMax H3 node present (variant name)"
        echo "$OI" | jq -r 'keys | map(select(test("minimax"; "i"))) | join(", ")' | sed 's/^/        nodes: /'
    else
        echo "  [MISS] MiniMax H3 node NOT found in object_info"
        FAIL=$((FAIL+1))
    fi
else
    echo "  [MISS] /object_info unreachable"
    FAIL=$((FAIL+1))
fi

exit "$FAIL"
