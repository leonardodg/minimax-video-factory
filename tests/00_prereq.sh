#!/usr/bin/env bash
# tests/00_prereq.sh — host prerequisites: disk, RAM, VRAM, docker, toolkit, uv, network
# Isolated check #0. Exit 0 = all good.
set -u
FAIL=0
check() {  # check <label> <command...>
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  [ok]   $label"
    else
        echo "  [MISS] $label"
        FAIL=$((FAIL+1))
    fi
}

echo "== Host prerequisites =="

# ---- Disk space on / (models partition) ----
ROOT_FREE=$(df -B1 / | awk 'NR==2 {print $4}')
ROOT_FREE_GB=$((ROOT_FREE / 1024 / 1024 / 1024))
echo "  [info] Free disk on / : ${ROOT_FREE_GB} GB"
if [ "$ROOT_FREE_GB" -ge 45 ]; then
    echo "  [ok]   >= 45 GB free on /"
else
    echo "  [MISS] < 45 GB free on / (need ~45 GB for models + image)"
    FAIL=$((FAIL+1))
fi

# ---- RAM ----
MEM_FREE=$(free -g | awk '/^Mem:/ {print $7}')
echo "  [info] Free RAM: ${MEM_FREE} GB"
if [ "$MEM_FREE" -ge 12 ]; then
    echo "  [ok]   >= 12 GB free RAM"
else
    echo "  [MISS] < 12 GB free RAM"
    FAIL=$((FAIL+1))
fi

# ---- VRAM ----
if command -v nvidia-smi >/dev/null 2>&1; then
    VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d ' ')
    echo "  [info] VRAM: ${VRAM} MB"
    if [ "$VRAM" -ge 12000 ] 2>/dev/null; then
        echo "  [ok]   >= 12 GB VRAM class"
    else
        echo "  [MISS] < 12 GB VRAM"
        FAIL=$((FAIL+1))
    fi
else
    echo "  [MISS] nvidia-smi not found (no NVIDIA GPU)"
    FAIL=$((FAIL+1))
fi

# ---- Docker ----
check "docker binary"      command -v docker
check "docker daemon up"   docker info
check "compose plugin"     docker compose version
check "nvidia toolkit"     command -v nvidia-container-toolkit

# ---- Tools ----
# uv is OPTIONAL on the host since the dockerized stack runs the MCP server in the
# image (only needed for host-side dev / fastmcp client tests).
if command -v uv >/dev/null 2>&1; then
    echo "  [ok]   uv (optional, host dev only)"
else
    echo "  [info] uv not found (optional — dockerized stack uses in-image venv)"
fi
check "curl"      command -v curl
check "ffmpeg"    command -v ffmpeg
check "jq"        command -v jq
check "python3"   command -v python3

# ---- Network to HuggingFace ----
if curl -sfI --max-time 10 "https://huggingface.co" >/dev/null 2>&1; then
    echo "  [ok]   network -> huggingface.co"
else
    echo "  [MISS] cannot reach huggingface.co"
    FAIL=$((FAIL+1))
fi

exit "$FAIL"
