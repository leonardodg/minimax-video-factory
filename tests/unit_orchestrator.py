#!/usr/bin/env python3
"""Pure-logic unit tests for the audiovisual studio orchestrator — no GPU, no
ComfyUI, no network, no faster-whisper.

Run: uv run --directory . python tests/unit_orchestrator.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp.orchestrator import AudiovisualStudio


def make_studio(tmp: Path) -> object:
    """Build an AudiovisualStudio with downloader/transcriber mocked out."""

    dl = mock.MagicMock()
    dl.download.return_value = {"ok": True, "filepath": str(tmp / "video.mp4")}
    tr = mock.MagicMock()
    tr.transcribe.return_value = {
        "ok": True,
        "text": "conteudo de teste",
        "segments": [{"start": 0.0, "end": 1.0, "text": "conteudo"}],
        "language": "pt",
    }

    studio = AudiovisualStudio.__new__(AudiovisualStudio)
    studio.downloads_dir = tmp
    studio.downloader = dl
    studio.transcriber = tr
    return studio


print("== unit_orchestrator: run_full_pipeline save_only=True ==")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    studio = make_studio(tmp)
    result = studio.run_full_pipeline(url="https://example.com/v", save_only=True, output_dir=tmp)
    if result.get("ok") and result.get("transcription_file") and result.get("prompt_file"):
        ok("save_only=True returns ok with saved files")
    else:
        bad(f"save_only=True result = {result!r}")

print("== unit_orchestrator: run_full_pipeline save_only=False (video generation) ==")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    studio = make_studio(tmp)

    gen = mock.MagicMock()
    gen.return_value = {
        "ok": True,
        "output_path": str(tmp / "out" / "scene.mp4"),
        "prompt_id": "abc-123",
        "seed": 4242,
    }
    studio.generate_video = gen

    result = studio.run_full_pipeline(
        url="https://example.com/v", save_only=False, output_dir=tmp
    )
    if result.get("ok") and result.get("output_video") and result.get("prompt_id"):
        ok("save_only=False calls generate_video and returns the video")
        if gen.call_count == 1:
            ok("generate_video called exactly once")
        else:
            bad(f"generate_video call_count = {gen.call_count}, expected 1")
        call_args = gen.call_args
        if call_args is not None and "prompt" in call_args.kwargs:
            ok("generate_video called with the cinematic prompt kwarg")
        else:
            bad(f"generate_video called with unexpected args: {call_args!r}")
    else:
        bad(f"save_only=False result = {result!r} (gen_result is undefined -> NameError)")

    gen_fail = mock.MagicMock()
    gen_fail.return_value = {"ok": False, "error": "render timeout"}
    studio.generate_video = gen_fail
    result = studio.run_full_pipeline(
        url="https://example.com/v", save_only=False, output_dir=tmp
    )
    if not result.get("ok") and result.get("stage") == "generate":
        ok("generate failure surfaces stage='generate' with the error")
    else:
        bad(f"generate failure result = {result!r}")

print("== unit_orchestrator: create_cinematic_prompt templates ==")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    studio = make_studio(tmp)
    for style, keyword in (("cinematic", "Cinematic"), ("educational", "Educational"), ("social", "social media reel"), ("bogus", "Cinematic")):
        p = studio.create_cinematic_prompt("algum conteudo", style=style)
        if keyword in p and "algum conteudo" in p:
            ok(f"create_cinematic_prompt('{style}') uses the {keyword} template")
        else:
            bad(f"create_cinematic_prompt('{style}') = {p[:120]!r}")

print("== unit_orchestrator: pipeline fails fast on bad stages ==")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    studio = make_studio(tmp)
    studio.downloader.download.return_value = {"ok": False, "error": "download blocked"}
    result = studio.run_full_pipeline(url="https://example.com/v", save_only=True, output_dir=tmp)
    if not result.get("ok") and result.get("stage") == "download":
        ok("download failure short-circuits with stage='download'")
    else:
        bad(f"download failure result = {result!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
