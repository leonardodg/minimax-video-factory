#!/usr/bin/env python3
"""Unit tests for AudioTranscriber.free() — releasing Whisper VRAM.

Hermetic: `free()` only touches the class-level model cache, so the tests call
it unbound against a stub instead of loading a real Whisper model. No GPU, no
faster-whisper, no network.

Run:  uv run --project . python tests/unit_transcriber.py
Exit 0 = all pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import transcriber as tr
from minimax_mcp.transcriber import AudioTranscriber


class Stub:
    """Just the three attributes free() reads to build its cache key."""

    def __init__(self, model_size="small", device="cuda", compute_type="float16"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    _model_cache = AudioTranscriber._model_cache


class Sentinel:
    """Stands in for a WhisperModel; records that it was dropped."""

    destroyed = False

    def __del__(self):
        Sentinel.destroyed = True


print("== unit_transcriber: free() drops the cached model ==")

AudioTranscriber._model_cache.clear()
AudioTranscriber._model_cache["small-cuda-float16"] = object()
AudioTranscriber._model_cache["large-v3-cuda-float16"] = object()

AudioTranscriber.free(Stub())

if "small-cuda-float16" not in AudioTranscriber._model_cache:
    ok("free() removes the entry for its own model/device/compute_type")
else:
    bad("free() left its own cache entry behind — the VRAM is still held")

if "large-v3-cuda-float16" in AudioTranscriber._model_cache:
    ok("free() leaves other cached models alone")
else:
    bad("free() cleared a cache entry belonging to a different model")

# The cache is class-level and shared, so free() must be safe to call twice --
# it runs in a `finally`, which can fire on paths where nothing was loaded.
AudioTranscriber._model_cache.clear()
try:
    AudioTranscriber.free(Stub())
    ok("free() on an empty cache is a no-op, not a KeyError")
except Exception as e:
    bad(f"free() raised on an empty cache: {e!r}")

# The point of dropping the entry: the CTranslate2 object owns its CUDA
# allocation and frees it from its destructor. If a reference survives, the
# VRAM does not come back and the whole method is theatre.
Sentinel.destroyed = False
AudioTranscriber._model_cache["small-cuda-float16"] = Sentinel()
AudioTranscriber.free(Stub())
if Sentinel.destroyed:
    ok("the cached model is actually destroyed, not merely unreferenced")
else:
    bad("something still holds the model after free() — VRAM stays allocated")

print("== unit_transcriber: free() must not pull in torch ==")

# The regression this guards: an earlier version called
# `torch.cuda.empty_cache()` here. faster-whisper allocates through
# CTranslate2, not PyTorch, so that call frees nothing it holds -- while
# `import torch` initialises a CUDA context worth a few hundred MB on the same
# 12 GB card. torch is imported nowhere else in this project, so its presence
# in sys.modules after free() means exactly one thing.
sys.modules.pop("torch", None)
AudioTranscriber._model_cache["small-cuda-float16"] = object()

# Guarded: against the version this test was written for, `import torch` here
# does not merely cost VRAM -- torch re-registers its `triton` namespace and
# raises "Only a single TORCH_LIBRARY can be used". Catch it so the guard
# reports a readable failure instead of a traceback.
imported_torch: str | None = None
try:
    AudioTranscriber.free(Stub())
except Exception as e:
    imported_torch = f"free() raised while importing torch: {str(e)[:90]}"
else:
    if "torch" in sys.modules:
        imported_torch = "free() imported torch"

if imported_torch is None:
    ok("free() does not import torch (no CUDA context on the card it frees)")
else:
    bad(
        f"{imported_torch}. faster-whisper allocates through CTranslate2, not "
        "PyTorch, so torch frees nothing it holds — while importing it costs a "
        "CUDA context of a few hundred MB on the GPU this method exists to "
        "give memory back to."
    )

print("== unit_transcriber: a failing free() never costs a transcription ==")

from minimax_mcp import ig_worker


class Exploding:
    """Transcribes fine, then blows up on cleanup."""

    def __init__(self, *a, **kw):
        pass

    def transcribe(self, path):
        return {"ok": True, "text": "transcrição cara"}

    def free(self):
        raise RuntimeError("CUDA error: driver hiccup under VRAM pressure")


real = tr.AudioTranscriber
tr.AudioTranscriber = Exploding
try:
    result = ig_worker._default_transcribe("/tmp/x.mp4")
except Exception as e:
    result = {"ok": False, "error": f"raised: {e!r}"}
finally:
    tr.AudioTranscriber = real

if result.get("ok") and result.get("text") == "transcrição cara":
    ok("a failure inside free() does not replace the transcription result")
else:
    bad(
        f"a cleanup failure destroyed a finished transcription: {result}. "
        "free() runs in a finally — it must be guarded."
    )

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
