"""YouTube Music guest search with retry backoff and link parsing."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

from .config import RETRY_ATTEMPTS, RETRY_BASE_DELAY
from .models import Track

log = logging.getLogger(__name__)

_LINK_PATTERNS = (
    re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|music\.youtube\.com/watch\?(?:.*&)?v=)([\w-]{11})"),
    re.compile(r"^([\w-]{11})$"),
)


def parse_video_id(query: str) -> str | None:
    """Extract a video id from a YouTube/YT Music URL (or bare id). None if not a link."""
    q = query.strip()
    for pattern in _LINK_PATTERNS:
        m = pattern.search(q)
        if m:
            return m.group(1)
    return None


class Catalog:
    """YT Music guest-API catalogue access. Heavy client import is lazy."""

    def __init__(self):
        self._client = None

    def _get_client(self, client_factory: Callable | None = None):
        if client_factory is not None:
            return client_factory()
        if self._client is None:
            from ytmusicapi import YTMusic  # lazy: keeps UI startup snappy

            self._client = YTMusic()
        return self._client

    def search(
        self,
        query: str,
        limit: int = 20,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> list[Track]:
        """Search songs; returns [] on exhausted retries (never raises)."""
        for attempt in range(attempts):
            try:
                raw = self._get_client(client_factory).search(
                    query, filter="songs", limit=limit
                )
                return self._map_results(raw or [])
            except Exception as exc:  # noqa: BLE001 - network layer must not crash UI
                if attempt == attempts - 1:
                    log.warning("search(%r) failed after %d attempts: %s", query, attempts, exc)
                    return []
                delay = base_delay * (2 ** attempt)
                log.info("search retry %d/%d in %.1fs (%s)", attempt + 1, attempts, delay, exc)
                sleep(delay)
        return []

    def song_details(
        self,
        video_id: str,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> Track | None:
        """Fetch metadata for a single video id (e.g. from a pasted link)."""
        for attempt in range(attempts):
            try:
                info = self._get_client(client_factory).get_song(video_id)
                video = (info or {}).get("videoDetails", {})
                if not video.get("videoId"):
                    return None
                return self._map_song(video)
            except Exception as exc:  # noqa: BLE001
                if attempt == attempts - 1:
                    log.warning("song_details(%s) failed: %s", video_id, exc)
                    return None
                sleep(base_delay * (2 ** attempt))
        return None

    @staticmethod
    def _map_results(results: list[dict]) -> list[Track]:
        tracks: list[Track] = []
        for item in results:
            if not item.get("videoId"):
                continue
            artists = ", ".join(a.get("name", "") for a in item.get("artists") or [])
            tracks.append(
                Track(
                    video_id=item["videoId"],
                    title=item.get("title", "Unknown"),
                    artist=artists or "Unknown artist",
                    duration=item.get("duration") or "",
                    duration_sec=_duration_to_sec(item.get("duration_seconds")),
                    thumbnail=(item.get("thumbnails") or [{}])[-1].get("url", ""),
                    playlist_id=item.get("album", {}).get("id", "") if isinstance(item.get("album"), dict) else "",
                )
            )
        return tracks

    @staticmethod
    def _map_song(video: dict) -> Track:
        return Track(
            video_id=video["videoId"],
            title=video.get("title", "Unknown"),
            artist=video.get("author", "Unknown artist"),
            duration_sec=int(video.get("lengthSeconds") or 0),
            duration=_seconds_to_clock(int(video.get("lengthSeconds") or 0)),
            thumbnail=(video.get("thumbnail", {}).get("thumbnails") or [{}])[-1].get("url", ""),
        )


def _duration_to_sec(seconds) -> int:
    try:
        return int(seconds or 0)
    except (TypeError, ValueError):
        return 0


def _seconds_to_clock(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"
