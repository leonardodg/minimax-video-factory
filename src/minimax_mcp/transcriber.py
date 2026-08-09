"""Audio transcriber using faster-whisper (local, GPU-accelerated)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore


class AudioTranscriber:
    """Transcribes audio from video files using faster-whisper (local, GPU)."""

    _model_cache: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        download_root: str | Path | None = None,
    ):
        """
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3)
            device: cuda or cpu
            compute_type: float16 (GPU), int8 (CPU), float32
            download_root: Where to cache downloaded models
        """
        if WhisperModel is None:
            raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = Path(download_root) if download_root else None

    def _get_model(self) -> Any:
        """Get or create cached WhisperModel instance."""
        cache_key = f"{self.model_size}-{self.device}-{self.compute_type}"
        if cache_key not in self._model_cache:
            logger.info("Loading Whisper model: %s on %s (%s)", self.model_size, self.device, self.compute_type)
            kwargs = {
                "device": self.device,
                "compute_type": self.compute_type,
            }
            if self.download_root:
                kwargs["download_root"] = str(self.download_root)
            try:
                self._model_cache[cache_key] = WhisperModel(self.model_size, **kwargs)
            except RuntimeError as e:
                # A busy card is not a reason to refuse to transcribe. The GPU
                # is routinely occupied here -- by a render, or by Ollama, which
                # holds ~10 GB after any knowledge-base call -- and the CPU can
                # do this job, just slower. Only fall back for memory, since
                # other RuntimeErrors mean something actually broke.
                if self.device == "cpu" or "out of memory" not in str(e).lower():
                    raise
                logger.warning(
                    "Whisper could not load on %s (%s). Falling back to CPU/int8 -- "
                    "slower, but the GPU is occupied.", self.device, e,
                )
                kwargs["device"] = "cpu"
                kwargs["compute_type"] = "int8"
                self._model_cache[cache_key] = WhisperModel(self.model_size, **kwargs)
        return self._model_cache[cache_key]

    def transcribe(
        self,
        video_path: str | Path,
        language: str = "pt",
        beam_size: int = 5,
        vad_filter: bool = True,
        word_timestamps: bool = False,
    ) -> dict[str, Any]:
        """
        Transcribe audio from a video file.

        Args:
            video_path: Path to video/audio file
            language: Language code (pt for Portuguese)
            beam_size: Beam size for decoding
            vad_filter: Use voice activity detection
            word_timestamps: Include word-level timestamps

        Returns:
            Dict with transcription text, segments, and metadata.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return {"ok": False, "error": f"File not found: {video_path}"}

        logger.info("Transcribing %s with %s model", video_path, self.model_size)

        try:
            model = self._get_model()
            segments, info = model.transcribe(
                str(video_path),
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )

            segments_list = []
            full_text = []
            for seg in segments:
                segment_data = {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                }
                if word_timestamps and seg.words:
                    segment_data["words"] = [
                        {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                        for w in seg.words
                    ]
                segments_list.append(segment_data)
                full_text.append(f"[{seg.start:.2f}s - {seg.end:.2f}s] {seg.text.strip()}")

            return {
                "ok": True,
                "text": "\n".join(full_text),
                "segments": segments_list,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
            }

        except Exception as e:
            logger.exception("Transcription failed for %s", video_path)
            return {"ok": False, "error": f"Transcription failed: {e!s}"}

    def free(self) -> None:
        """Unload the cached Whisper model and release the VRAM it occupies.

        The model lives in a class-level cache so repeated transcriptions skip
        the load; but a loaded whisper keeps its weights resident on the GPU,
        which can starve Ollama (lfm2:24b needs ~6 GB) on the same 12 GB card.
        Call this between the Whisper step and the LLM step in a long pipeline.
        """
        cache_key = f"{self.model_size}-{self.device}-{self.compute_type}"
        if cache_key in self._model_cache:
            try:
                del self._model_cache[cache_key]
            except Exception:
                pass
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def transcribe_video(
    video_path: str | Path,
    model_size: str = "small",
    device: str = "cuda",
    language: str = "pt",
) -> dict[str, Any]:
    """Convenience function for single transcription."""
    transcriber = AudioTranscriber(model_size=model_size, device=device)
    return transcriber.transcribe(video_path, language=language)