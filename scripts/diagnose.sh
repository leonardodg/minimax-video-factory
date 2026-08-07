#!/usr/bin/env bash
# diagnose.sh — run isolated per-component checks (00..06)
# Usage: ./scripts/diagnose.sh [00|01|02|03|04|05|06]  (default: all)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$SCRIPT_DIR/../tests" && pwd)"
PASS=0; FAIL=0; SKIP=0; FAILED_NAMES=(); SKIPPED_NAMES=()

# A test exits 78 (EX_CONFIG) when its backing service is absent. That is
# neither a pass nor a failure: counting it as PASS would hide a regression
# behind a green tick, counting it as FAIL would cry wolf on every machine
# that simply does not run Postgres.

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

run_test() {
    local file="$1"
    local name
    name="$(basename "$file")"
    echo ""
    yellow "========== [$name] =========="
    local rc=0
    bash "$file" || rc=$?
    if [ "$rc" -eq 0 ]; then
        green "[PASS] $name"
        PASS=$((PASS+1))
    elif [ "$rc" -eq 78 ]; then
        yellow "[SKIP] $name"
        SKIP=$((SKIP+1))
        SKIPPED_NAMES+=("$name")
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
if [ "$SKIP" -gt 0 ]; then
    yellow "SKIP: $SKIP"
    printf 'Skipped: %s\n' "${SKIPPED_NAMES[*]}"
fi
red   "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    printf 'Failed: %s\n' "${FAILED_NAMES[*]}"
    exit 1
fi
echo "========================================"
