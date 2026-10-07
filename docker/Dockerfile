# ComfyUI with MiniMax H3 (native since 0.30.0) — pinned reproducible image
# Base: official PyTorch CUDA runtime (torch + CUDA bundled)
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Pin ComfyUI at a release with native MiniMax H3 support (>= 0.30.0)
ARG COMFYUI_TAG=v0.39.1
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

# --- Python deps of the custom node packs ---
# These MUST be in the image, not installed at runtime. custom_nodes is a bind
# mount so the node *code* survives, but `pip install` inside a running
# container writes to the container's writable layer -- which `docker compose
# up -d` throws away on every recreate. Measured 2026-08-11: installing the deps
# at runtime took ComfyUI from 1143 to 1587 nodes; the next recreate (to add an
# unrelated mount) put it straight back to 1143, with Impact-Pack,
# VideoHelperSuite and Easy-Use all failing on `No module named 'cv2'`.
#
# One opencv variant only. The packs ask for three (opencv-python,
# opencv-python-headless, opencv-contrib-python) and they all install the same
# `cv2` module over each other. contrib is the superset, and the non-headless
# build is fine here because libgl1/libglib2.0-0 are installed above.
#
# Union of: ComfyUI-Impact-Pack, ComfyUI-VideoHelperSuite, ComfyUI-KJNodes,
# ComfyUI-Easy-Use, ComfyUI-Frame-Interpolation. Deliberately WITHOUT:
#   - the git+ SAM2 dependency of Impact-Pack (heavy; only its segmentation
#     nodes need it, and the H3 workflows use ImpactSwitch, which does not)
#   - cupy-wheel from Frame-Interpolation (compiles against local CUDA; RIFE,
#     the only VFI model these workflows use, runs without it)
#   - torch/torchvision, which several packs list unpinned and which must stay
#     exactly at the versions pinned above
RUN pip install --no-cache-dir \
      opencv-contrib-python imageio-ffmpeg \
      diffusers accelerate lark onnxruntime sentencepiece spandrel peft \
      "clip_interrogator>=0.6.0" \
      segment-anything scikit-image piexif transformers scipy dill matplotlib \
      color-matcher mss "pillow>=10.3.0" \
      einops kornia tqdm

# --- MCP server inside the image (no host uv/Python needed) ---
# Install uv, copy the project into the image and create a dedicated venv at
# /opt/mcp-venv. At runtime the compose file bind-mounts the live repo to
# /workspace (read-only) so `docker compose exec` runs this venv's uv directly.
RUN pip install --no-cache-dir uv
# uv.lock IN the image + --frozen: the venv must match the tested lock exactly
# (av==18.1.0 pin, fastmcp 4.0.11) instead of re-resolving floating ranges at
# every build. Needs uv >= 0.12 for lock revision 5 (Dockerfile installs latest
# uv unpinned, so OK). Decision recorded in docs/HANDOFF.md (review Task 2).
COPY pyproject.toml uv.lock /workspace/
COPY src /workspace/src
COPY workflows /workspace/workflows
COPY scripts /workspace/scripts
ENV UV_PROJECT_ENVIRONMENT=/opt/mcp-venv
RUN cd /workspace && uv sync --no-dev --frozen
# nvidia cu12 libs (cublas/cudnn) for ctranslate2/faster-whisper GPU transcription —
# the venv's torch is cu13 (latest), but ctranslate2 needs libcublas.so.12.
# CAUTION: these wheels are NOT in uv.lock — any `uv sync`/`uv run` re-run
# inside the container (UV_PROJECT_ENVIRONMENT=/opt/mcp-venv) prunes them and
# breaks GPU transcription. Use `uv run --no-sync` if you must run uv there.
RUN /opt/conda/bin/uv pip install --python /opt/mcp-venv/bin/python --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12
ENV LD_LIBRARY_PATH="/opt/mcp-venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/mcp-venv/lib/python3.11/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}"

WORKDIR /comfy/ComfyUI

# Entrypoint: launch with flags tuned for low-VRAM / limited-RAM machines.
#   --fast-disk            move weights into page cache (critical on 16-32 GB RAM)
#   --disable-pinned-memory  workaround for a pinned-memory regression seen on
#                            0.30.x; kept on 0.39.1 after the v0.39.1 upgrade
#                            (2026-10-07) rendered fine with it on -- removing
#                            it hasn't been tested, so it stays until someone
#                            verifies it's no longer needed.
#   --lowvram              aggressive offload (12 GB VRAM: Qwen3VL-32B + diffusion exceed 12 GB)
#   --listen 127.0.0.1     local only (fronted by docker port mapping)
EXPOSE 8188
# Listen on all interfaces *inside the container* (0.0.0.0). The compose file
# maps the port to 127.0.0.1 on the host, so the API stays local to the host.
# (--listen 127.0.0.1 inside a container breaks docker-proxy port publishing.)
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--lowvram", "--fast-disk", "--disable-pinned-memory"]
