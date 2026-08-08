"""Orchestrator for the full audiovisual studio pipeline: URL → download → transcribe → prompt → video."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from minimax_mcp.core import (
    submit_scene_core,
    wait_for_video_core,
)
from minimax_mcp.downloader import VideoDownloader
from minimax_mcp.transcriber import AudioTranscriber

logger = logging.getLogger(__name__)


class AudiovisualStudio:
    """Full pipeline: URL → download → transcribe → prompt → generate video."""

    def __init__(
        self,
        downloads_dir: str | Path,
        whisper_model: str = "small",
        whisper_device: str = "cuda",
        browser: str = "chrome",
    ):
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)


        self.downloader = VideoDownloader(output_dir=self.downloads_dir, browser=browser)
        self.transcriber = AudioTranscriber(
            model_size=whisper_model, device=whisper_device
        )

    def download_video(self, url: str) -> dict[str, Any]:
        """Download video from URL."""
        return self.downloader.download(url)

    def transcribe_video(self, video_path: str | Path) -> dict[str, Any]:
        """Transcribe video audio to text with timestamps."""
        return self.transcriber.transcribe(video_path)

    def create_cinematic_prompt(self, transcription: str, style: str = "cinematic") -> str:
        """
        Convert transcription into a cinematic MiniMax H3 prompt.
        In production, this would call an LLM. Here we use a template.
        """
        content = transcription[:2000]

        prompt_templates = {
            "cinematic": (
                "Professional cinematic video based on the following content: {content}\n\n"
                "Shot: Cinematic wide shot establishing scene, smooth camera movement, "
                "depth of field, golden hour lighting. "
                "Camera: Slow dolly in, 35mm lens, subtle parallax. "
                "Audio: Immersive ambient soundscape, subtle foley, emotional score. "
                "Duration: 10 seconds."
            ),
            "educational": (
                "Educational explainer video visualizing: {content}\n\n"
                "Shot: Clean animation style, kinetic typography, infographics, "
                "smooth transitions, modern UI aesthetic. "
                "Camera: Static with animated elements, 16:9 safe area. "
                "Audio: Clear narration-friendly ambient, subtle UI sounds. "
                "Duration: 15 seconds."
            ),
            "social": (
                "Vertical social media reel (9:16) for: {content}\n\n"
                "Shot: Fast-paced cuts, dynamic text overlays, trending transitions, "
                "vibrant colors, hook in first 3 seconds. "
                "Camera: Handheld feel, quick zoom, whip pans. "
                "Audio: Upbeat background music, sync points, sound design. "
                "Duration: 8 seconds."
            ),
        }

        template = prompt_templates.get(style, prompt_templates["cinematic"])
        return template.format(content=content)

    def generate_video(
        self,
        prompt: str,
        duration: float = 10.0,
        width: int = 1024,
        height: int = 576,
        seed: int | None = None,
        first_frame: str | None = None,
        filename_prefix: str = "studio/",
    ) -> dict[str, Any]:
        """Generate video using the existing MiniMax H3 pipeline."""
        import logging
        logger = logging.getLogger(__name__)

        logger.info("Generating video: %s...", prompt[:80])

        try:
            result = submit_scene_core(
                prompt=prompt,
                duration=duration,
                width=width,
                height=height,
                seed=seed,
                filename_prefix=filename_prefix,
                first_frame=first_frame,
            )
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error", "Submit failed")}

            prompt_id = result["prompt_id"]
            logger.info("Submitted prompt_id=%s, waiting for render...", prompt_id)

            import asyncio
            wait_result = asyncio.run(wait_for_video_core(prompt_id, timeout=1800))
            if not wait_result.get("ok"):
                return {"ok": False, "error": wait_result.get("error", "Render timeout")}

            return {
                "ok": True,
                "output_path": wait_result.get("output_path"),
                "prompt_id": prompt_id,
                "seed": result.get("seed"),
            }

        except Exception as e:
            logging.getLogger(__name__).exception("Video generation failed")
            return {"ok": False, "error": f"Generation failed: {e!s}"}

    def save_transcription_and_prompt(
        self,
        transcription: str,
        cinematic_prompt: str,
        output_dir: str | Path,
        url: str,
    ) -> dict[str, Any]:
        """Save transcription and prompt to output directory instead of generating video."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Save transcription
        transcription_file = output_dir / f"transcription_{timestamp}.txt"
        transcription_file.write_text(
            f"Source URL: {url}\n\n"
            f"Transcription:\n{transcription}\n",
            encoding="utf-8"
        )

        # Save prompt
        prompt_file = output_dir / f"prompt_{timestamp}.txt"
        prompt_file.write_text(
            f"Source URL: {url}\n\n"
            f"Generated Prompt:\n{cinematic_prompt}\n",
            encoding="utf-8"
        )

        return {
            "ok": True,
            "transcription_file": str(transcription_file),
            "prompt_file": str(prompt_file),
        }

    def run_full_pipeline(
        self,
        url: str,
        style: str = "cinematic",
        duration: float = 10.0,
        width: int = 1024,
        height: int = 576,
        save_only: bool = False,
        output_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        Run the complete pipeline: URL → download → transcribe → prompt → video.

        Args:
            url: Video URL to process
            style: Prompt style (cinematic, educational, social)
            duration: Generated clip duration in seconds
            width: Output width
            height: Output height
            save_only: If True, skip video generation and only save transcription + prompt
            output_dir: Directory to save transcription and prompt (default: downloads_dir)

        Returns dict with all intermediate results and final video path (or saved files).
        """
        logger = logging.getLogger(__name__)
        logger.info("=== Starting full pipeline for %s ===", url)

        output_dir = Path(output_dir) if output_dir else self.downloads_dir

        # 1. Download
        logger.info("Step 1/5: Downloading video...")
        dl_result = self.download_video(url)
        if not dl_result.get("ok"):
            return {"ok": False, "stage": "download", "error": dl_result.get("error")}
        video_path = dl_result["filepath"]
        logger.info("Downloaded to: %s", video_path)

        # 2. Transcribe
        logger.info("Step 2/5: Transcribing audio...")
        tr_result = self.transcriber.transcribe(video_path)
        if not tr_result.get("ok"):
            return {"ok": False, "stage": "transcribe", "error": tr_result.get("error")}
        transcription = tr_result["text"]
        logger.info("Transcription length: %d chars", len(transcription))

        # 3. Create cinematic prompt
        logger.info("Step 3/5: Creating cinematic prompt...")
        cinematic_prompt = self.create_cinematic_prompt(transcription, style=style)
        logger.info("Prompt created (%d chars)", len(cinematic_prompt))

        # 4. Save transcription and prompt
        logger.info("Step 4/5: Saving transcription and prompt...")
        save_result = self.save_transcription_and_prompt(
            transcription=transcription,
            cinematic_prompt=cinematic_prompt,
            output_dir=output_dir,
            url=url,
        )

        if save_only:
            logger.info("=== Pipeline completed (save_only mode) ===")
            return {
                "ok": True,
                "url": url,
                "downloaded_file": video_path,
                "transcription": transcription,
                "transcription_segments": tr_result.get("segments", []),
                "cinematic_prompt": cinematic_prompt,
                "transcription_file": save_result.get("transcription_file"),
                "prompt_file": save_result.get("prompt_file"),
            }

        # 5. Generate video
        logger.info("Step 5/5: Generating video...")
        gen_result = self.generate_video(
            prompt=cinematic_prompt,
            duration=duration,
            width=width,
            height=height,
        )
        logger.info("Generation result: %s", gen_result)

        if not gen_result.get("ok"):
            return {"ok": False, "stage": "generate", "error": gen_result.get("error")}

        logger.info("=== Pipeline completed successfully ===")
        return {
            "ok": True,
            "url": url,
            "downloaded_file": video_path,
            "transcription": transcription,
            "transcription_segments": tr_result.get("segments", []),
            "cinematic_prompt": cinematic_prompt,
            "output_video": gen_result.get("output_path"),
            "prompt_id": gen_result.get("prompt_id"),
            "seed": gen_result.get("seed"),
        }


def run_studio_pipeline(
    url: str,
    downloads_dir: str | Path,
    style: str = "cinematic",
    duration: float = 10.0,
    width: int = 1024,
    height: int = 576,
    whisper_model: str = "small",
    whisper_device: str = "cuda",
    browser: str = "chrome",
    save_only: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Convenience function for one-shot pipeline execution."""
    studio = AudiovisualStudio(
        downloads_dir=downloads_dir,
        whisper_model=whisper_model,
        whisper_device=whisper_device,
        browser=browser,
    )
    return studio.run_full_pipeline(
        url=url,
        style=style,
        duration=duration,
        width=width,
        height=height,
        save_only=save_only,
        output_dir=output_dir,
    )