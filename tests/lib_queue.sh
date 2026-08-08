#!/usr/bin/env bash
# tests/lib_queue.sh — shared helper: do not jump the render queue.
#
# The GPU tests submit real renders. On a self-hosted runner that GPU is
# somebody's desk machine, and a CI run that queues work while they are
# rendering pushes their job behind ours -- which is exactly how a 15-minute
# clip turned into a 30-minute wait and, once, into a queue of eleven orphans
# nobody noticed.
#
# So: wait for the queue to drain, bounded. If it drains, run. If the machine
# is genuinely busy, skip rather than compete. Skipping is honest here -- the
# render pipeline is not broken, it is occupied.
#
# Source this, then call:  wait_for_idle_queue || skip "..."

# Number of jobs ComfyUI currently has running or pending. Prints 0 when the
# server cannot be reached, so callers fall through to their own health checks
# instead of hanging here.
comfy_queue_depth() {
    local url="${COMFYUI_URL:-http://127.0.0.1:8188}"
    curl -s --max-time 5 "${url}/queue" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(0); raise SystemExit
print(len(d.get('queue_running') or []) + len(d.get('queue_pending') or []))
" 2>/dev/null || echo 0
}

# Wait until the queue is empty. Returns 0 if it became empty, 1 on timeout.
# Timeout is CI_QUEUE_WAIT_SECONDS (default 600); set it to 0 to check once and
# give up immediately.
wait_for_idle_queue() {
    local timeout="${CI_QUEUE_WAIT_SECONDS:-600}"
    local interval="${CI_QUEUE_POLL_SECONDS:-10}"
    local waited=0 depth

    depth="$(comfy_queue_depth)"
    if [ "$depth" -eq 0 ] 2>/dev/null; then
        return 0
    fi

    echo "  [info] render queue busy (${depth} job(s)); waiting up to ${timeout}s rather than queueing behind them"
    while [ "$waited" -lt "$timeout" ]; do
        sleep "$interval"
        waited=$((waited + interval))
        depth="$(comfy_queue_depth)"
        if [ "$depth" -eq 0 ] 2>/dev/null; then
            echo "  [info] queue drained after ${waited}s"
            return 0
        fi
    done
    return 1
}
