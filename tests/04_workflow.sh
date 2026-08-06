#!/usr/bin/env bash
# tests/04_workflow.sh — API-format workflow JSON valid; node class_types resolve against /object_info
set -u
FAIL=0
if [ -f "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh"
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="${WORKFLOW:-$ROOT/workflows/minimax_h3_t2v_api.json}"
COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"

echo "== Workflow API format =="

if [ ! -f "$WORKFLOW" ]; then
    echo "  [MISS] $WORKFLOW not found"
    exit 1
fi

if jq -e . "$WORKFLOW" >/dev/null 2>&1; then
    echo "  [ok]   JSON parses"
else
    echo "  [MISS] invalid JSON"
    exit 1
fi

# Every node must have class_type + inputs
NODES=$(jq -r 'to_entries[] | "\(.key)\t\(.value.class_type)\t\(.value.inputs != null)"' "$WORKFLOW")
echo "  [info] node count: $(jq 'length' "$WORKFLOW")"
BAD=$(echo "$NODES" | awk -F'\t' '$3 != "true" {print $1" ("$2")"}')
if [ -n "$BAD" ]; then
    echo "  [MISS] nodes without inputs: $BAD"
    FAIL=$((FAIL+1))
fi

# class_types must exist in object_info
OI=$(curl -sf --max-time 20 "$COMFYUI_URL/object_info") || OI=""
if [ -n "$OI" ]; then
    while IFS=$'\t' read -r id ct _; do
        if ! echo "$OI" | jq -e --arg ct "$ct" 'has($ct)' >/dev/null 2>&1; then
            echo "  [MISS] class_type '$ct' (node $id) not in object_info"
            FAIL=$((FAIL+1))
        fi
    done <<< "$NODES"
    [ "$FAIL" -eq 0 ] && echo "  [ok]   all class_types resolve against ComfyUI"
else
    echo "  [WARN] object_info unreachable; skipped class_type validation (ComfyUI not up?)"
fi

exit "$FAIL"
