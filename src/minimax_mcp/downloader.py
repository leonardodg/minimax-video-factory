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

    def _build_ydl_opts(self, use_cookies: bool = True) -> dict[str, Any]:
        """Build yt-dlp options, optionally with browser cookie support."""
        opts: dict[str, Any] = {
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "format": self.format_spec,
            "ignoreerrors": True,
            "no_warnings": False,
            "quiet": False,
            "noprogress": False,
            # Allow fallback to other formats if preferred not available
            "format_sort": ["ext:mp4", "res:1080", "res:720", "res:480"],
        }
        if use_cookies:
            opts["cookiesfrombrowser"] = (self.browser,)
        return opts

    def download(self, url: str) -> dict[str, Any]:
        """
        Download a video from the given URL.

        Tries browser cookies first, then falls back to an anonymous download when
        the cookie DB is unavailable (e.g. container without the browser profile,
        browser running/locked, or no keyring to decrypt the cookies).

        Args:
            url: Video URL (Instagram Reel, YouTube, etc.)

        Returns:
            Dict with success status, file path, and metadata.
        """
        for use_cookies in (True, False):
            mode = f"browser cookies ({self.browser})" if use_cookies else "no cookies"
            logger.info("Downloading video from %s using %s", url, mode)

            try:
                with YoutubeDL(self._build_ydl_opts(use_cookies=use_cookies)) as ydl:
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
                msg = str(e)
                logger.exception("Download attempt failed for %s (%s)", url, mode)
                if use_cookies and self._is_cookie_error(msg):
                    logger.warning("Cookie loading failed (%s); retrying without cookies", msg)
                    continue
                return {"ok": False, "error": f"Download failed: {msg}"}

        return {"ok": False, "error": "Download failed: no usable download path"}

    @staticmethod
    def _is_cookie_error(msg: str) -> bool:
        """Heuristic: does this error mean the browser cookie source was the problem?"""
        lowered = msg.lower()
        return any(
            kw in lowered
            for kw in ("cookie", "database", "could not find browser", "keyring", "dbus")
        )


def download_video(
    url: str,
    output_dir: str | Path,
    browser: str = "chrome",
) -> dict[str, Any]:
    """Convenience function for single video download."""
    downloader = VideoDownloader(output_dir=output_dir, browser=browser)
    return downloader.download(url)