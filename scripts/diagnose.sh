#!/usr/bin/env bash
# diagnose.sh — run isolated per-component checks (00..06)
# Usage: ./scripts/diagnose.sh [00|01|02|03|04|05|06]  (default: all)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$SCRIPT_DIR/../tests" && pwd)"
PASS=0; FAIL=0; FAILED_NAMES=()

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

run_test() {
    local file="$1"
    local name
    name="$(basename "$file")"
    echo ""
    yellow "========== [$name] =========="
    if bash "$file"; then
        green "[PASS] $name"
        PASS=$((PASS+1))
    else
        red "[FAIL] $name"
        FAIL=$((FAIL+1))
        FAILED_NAMES+=("$name")
    fi
}

TARGET="${1:-all}"
if [ "$TARGET" = "all" ]; then
    for f in "$TESTS_DIR"/0*.sh; do
        [ -e "$f" ] || continue
        run_test "$f"
    done
else
    for pat in "$TARGET"; do
        for f in "$TESTS_DIR"/"$pat"*.sh; do
            [ -e "$f" ] && run_test "$f"
        done
    done
fi

echo ""
echo "========================================"
green "PASS: $PASS"
red   "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    printf 'Failed: %s\n' "${FAILED_NAMES[*]}"
    exit 1
fi
echo "========================================"
