# ComfyUI with MiniMax H3 (native since 0.30.0) — pinned reproducible image
# Base: official PyTorch CUDA runtime (torch + CUDA bundled)
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Pin ComfyUI at a release with native MiniMax H3 support (>= 0.30.0)
ARG COMFYUI_TAG=v0.30.2
# Tag list: see https://github.com/comfyanonymous/ComfyUI/tags (0.3.x). Fall back to master if tag missing.
# For a fully pinned build, set COMFYUI_TAG to a known-good tag; otherwise use master.

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /comfy

# Install runtime helpers
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ffmpeg libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI (pin to tag if it exists, else master)
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git ComfyUI \
 && (cd ComfyUI && git fetch --depth 1 origin tag "$COMFYUI_TAG" 2>/dev/null \
     && git checkout -q "$COMFYUI_TAG" || true) \
 && (cd ComfyUI && git rev-parse --short HEAD)

# Install ComfyUI requirements (torch already present from base image)
RUN pip install --no-cache-dir -r ComfyUI/requirements.txt

# Upgrade PyTorch to >= 2.8 so ComfyUI uses DynamicVRAM instead of the legacy
# ModelPatcher ("VRAM estimates may be unreliable"). Without it, --lowvram does
# not patch models on 12 GB VRAM and sampling OOMs (Qwen3VL-32B + INT4 UNet).
# torch >= 2.8 has no cu124 wheel; cu128 wheels bundle their own CUDA libs via
# pip nvidia-* deps and the host driver supports CUDA 12.8.
# torchvision/torchaudio are pinned to the same 2.8.0 release train (an unpinned
# install grabs 2.13 which needs torch>=2.13 -> torchaudio abi3 loader fails).
RUN pip install --no-cache-dir "torch==2.8.0" "torchvision==0.23.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cu128

# --- MCP server inside the image (no host uv/Python needed) ---
# Install uv, copy the project into the image and create a dedicated venv at
# /opt/mcp-venv. At runtime the compose file bind-mounts the live repo to
# /workspace (read-only) so `docker compose exec` runs this venv's uv directly.
RUN pip install --no-cache-dir uv
COPY pyproject.toml /workspace/pyproject.toml
COPY src /workspace/src
COPY workflows /workspace/workflows
COPY scripts /workspace/scripts
ENV UV_PROJECT_ENVIRONMENT=/opt/mcp-venv
RUN cd /workspace && uv sync --no-dev
# nvidia cu12 libs (cublas/cudnn) for ctranslate2/faster-whisper GPU transcription —
# the venv's torch is cu13 (latest), but ctranslate2 needs libcublas.so.12.
RUN /opt/conda/bin/uv pip install --python /opt/mcp-venv/bin/python --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12
ENV LD_LIBRARY_PATH="/opt/mcp-venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/mcp-venv/lib/python3.11/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}"

WORKDIR /comfy/ComfyUI

# Entrypoint: launch with flags tuned for low-VRAM / limited-RAM machines.
#   --fast-disk            move weights into page cache (critical on 16-32 GB RAM)
#   --disable-pinned-memory  work around pinned-memory regression in 0.30.x
#   --lowvram              aggressive offload (12 GB VRAM: Qwen3VL-32B + diffusion exceed 12 GB)
#   --listen 127.0.0.1     local only (fronted by docker port mapping)
EXPOSE 8188
# Listen on all interfaces *inside the container* (0.0.0.0). The compose file
# maps the port to 127.0.0.1 on the host, so the API stays local to the host.
# (--listen 127.0.0.1 inside a container breaks docker-proxy port publishing.)
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--lowvram", "--fast-disk", "--disable-pinned-memory"]
