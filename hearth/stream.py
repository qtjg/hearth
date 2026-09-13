"""
stream.py
Resolves a track id (or a pasted link) into a direct HTTPS audio URL with
yt-dlp. Nothing is written to disk — only the resolved URL is consumed.

Format strategy is deliberately cross-platform: AAC in an MP4 (m4a) container
decodes cleanly on Windows Media Foundation, GStreamer (Linux) and
AVFoundation (macOS) alike, so it is preferred over WebM/Opus everywhere.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import yt_dlp

from .models import Track

log = logging.getLogger(__name__)

WATCH_URL = "https://www.youtube.com/watch?v={0}"

# Extractor refusals a retry cannot cure (auth/age gates, removed videos).
PERMANENT_FAILURE_MARKERS = (
    "sign in to confirm your age",
    "sign in to confirm you're not a bot",
    "sign in to confirm you\u2019re not a bot",
    "this video is age-restricted",
    "video unavailable",
    "private video",
    "members-only",
)


def is_permanent_failure(exc: BaseException) -> bool:
    """True when retrying the extractor cannot possibly help."""
    text = str(exc).lower()
    return any(marker in text for marker in PERMANENT_FAILURE_MARKERS)


BASE_OPTIONS: Dict[str, Any] = {
    "format": "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
    # Internal retries disabled on purpose: probe() already applies exponential
    # backoff, and stacking both multiplies into dozens of dead-air attempts.
    "retries": 0,
    "extractor_retries": 0,
    "socket_timeout": 15,
}


def rank_format(fmt: Dict[str, Any]) -> tuple:
    """Sort key: m4a first, then unknown containers, WebM/Opus last resort."""
    ext = str(fmt.get("ext") or "").lower()
    acodec = str(fmt.get("acodec") or "").lower()
    is_aac = ext == "m4a" or acodec.startswith("mp4a")
    is_webm = ext == "webm" or acodec.startswith("opus")
    try:
        abr = float(fmt.get("abr") or 0)
    except (TypeError, ValueError):
        abr = 0.0
    return (
        0 if is_aac else (2 if is_webm else 1),
        -abr,
    )


class StreamResolver:
    """Thin yt-dlp wrapper with retry backoff. Calls are synchronous — jobs run off-thread."""

    def __init__(self, overrides: Optional[Dict[str, Any]] = None) -> None:
        self.options = dict(BASE_OPTIONS)
        if overrides:
            self.options.update(overrides)

    def probe(self, target: str, max_attempts: int = 3) -> Dict[str, Any]:
        """Extract info with exponential backoff; bail instantly on permanent refusals."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                with yt_dlp.YoutubeDL(self.options) as ydl:
                    data = ydl.extract_info(target, download=False)
                    if isinstance(data, dict):
                        return data
                    raise RuntimeError("unexpected extractor response")
            except Exception as exc:
                last_exc = exc
                if is_permanent_failure(exc):
                    log.warning("probe %r blocked permanently: %s", target, exc)
                    raise
                if attempt < max_attempts:
                    delay = 0.5 * (2 ** (attempt - 1))
                    log.warning(
                        "probe %r attempt %d/%d failed: %s — retrying in %.1fs",
                        target, attempt, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    log.error("probe %r failed after %d attempts: %s", target, max_attempts, exc)
        if last_exc is not None:
            raise last_exc
        return {}

    def stream_url(self, video_id: str) -> Optional[str]:
        """Best usable audio URL for a track id, or None when nothing plays."""
        if not video_id:
            return None
        try:
            info = self.probe(WATCH_URL.format(video_id))
        except Exception as exc:
            log.error("stream_url failed for %s: %s", video_id, exc)
            return None

        formats = [
            fmt for fmt in (info.get("formats") or [])
            if isinstance(fmt, dict) and fmt.get("acodec") not in (None, "none") and fmt.get("url")
        ]
        if not formats:
            direct = info.get("url")
            return direct if isinstance(direct, str) and direct else None
        formats.sort(key=rank_format)
        return formats[0]["url"]

    def describe(self, url: str) -> Optional[Track]:
        """Turn a pasted link into a Track so it enters the normal queue."""
        if not url or not url.strip():
            return None
        try:
            info = self.probe(url.strip())
        except Exception as exc:
            log.error("describe failed for %r: %s", url, exc)
            return None
        video_id = info.get("id")
        if not video_id:
            return None
        return Track(
            video_id=str(video_id),
            title=str(info.get("title") or "untitled"),
            artist=str(info.get("uploader") or info.get("channel") or "youtube"),
            duration=str(info.get("duration_string") or ""),
            artwork_url=str(info.get("thumbnail") or ""),
        )
