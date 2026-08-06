"""Video downloader using yt-dlp with browser cookie support."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloads videos from Instagram, YouTube, and other platforms using yt-dlp."""

    def __init__(
        self,
        output_dir: str | Path,
        browser: str = "chrome",
        format_spec: str = "best[ext=mp4]/best",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.browser = browser
        self.format_spec = format_spec

    def _build_ydl_opts(self) -> dict[str, Any]:
        """Build yt-dlp options with browser cookie support."""
        return {
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "format": self.format_spec,
            "cookiesfrombrowser": (self.browser,),
            "ignoreerrors": True,
            "no_warnings": False,
            "quiet": False,
            "noprogress": False,
            # Allow fallback to other formats if preferred not available
            "format_sort": ["ext:mp4", "res:1080", "res:720", "res:480"],
        }

    def download(self, url: str) -> dict[str, Any]:
        """
        Download a video from the given URL.

        Args:
            url: Video URL (Instagram Reel, YouTube, etc.)

        Returns:
            Dict with success status, file path, and metadata.
        """
        logger.info("Downloading video from %s using browser cookies (%s)", url, self.browser)

        ydl_opts = self._build_ydl_opts()

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return {"ok": False, "error": "Failed to extract video info"}

                filepath = ydl.prepare_filename(info)
                if not os.path.exists(filepath):
                    # Try to find the actual file (yt-dlp sometimes changes extension)
                    base = os.path.splitext(filepath)[0]
                    for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                        cand = base + ext
                        if os.path.exists(cand):
                            filepath = cand
                            break

                if not os.path.exists(filepath):
                    return {"ok": False, "error": f"Downloaded file not found: {filepath}"}

                return {
                    "ok": True,
                    "filepath": filepath,
                    "title": info.get("title", "unknown"),
                    "duration": info.get("duration"),
                    "uploader": info.get("uploader"),
                    "webpage_url": info.get("webpage_url", url),
                }

        except Exception as e:
            logger.exception("Download failed for %s", url)
            return {"ok": False, "error": f"Download failed: {str(e)}"}


def download_video(
    url: str,
    output_dir: str | Path,
    browser: str = "chrome",
) -> dict[str, Any]:
    """Convenience function for single video download."""
    downloader = VideoDownloader(output_dir=output_dir, browser=browser)
    return downloader.download(url)