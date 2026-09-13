"""YouTube Music guest search with retry backoff and link parsing."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

from .config import RETRY_ATTEMPTS, RETRY_BASE_DELAY
from .models import Album, Track

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

    SEARCH_FILTERS = {"songs": "songs", "videos": "videos", "albums": "albums"}

    def __init__(self):
        self._client = None

    def _get_client(self, client_factory: Callable | None = None):
        if client_factory is not None:
            return client_factory()
        if self._client is None:
            from ytmusicapi import YTMusic  # lazy: keeps UI startup snappy

            self._client = YTMusic()
        return self._client

    def _retry(
        self,
        action: Callable,
        label: str,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        default=None,
    ):
        """Run `action` with exponential backoff. `default` on exhaustion."""
        for attempt in range(attempts):
            try:
                return action()
            except Exception as exc:  # noqa: BLE001 - network layer must not crash UI
                if attempt == attempts - 1:
                    log.warning("%s failed after %d attempts: %s", label, attempts, exc)
                    return default
                delay = base_delay * (2 ** attempt)
                log.info("%s retry %d/%d in %.1fs (%s)", label, attempt + 1, attempts, delay, exc)
                sleep(delay)
        return default

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
        return self.search_songs(
            query, limit=limit, attempts=attempts, base_delay=base_delay,
            sleep=sleep, client_factory=client_factory,
        )

    def scoped_search(
        self,
        query: str,
        scope: str = "songs",
        limit: int = 20,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> tuple[str, list]:
        """Search by scope; returns (scope, tracks|albums). Never raises."""
        if scope not in self.SEARCH_FILTERS:
            scope = "songs"
        if scope == "albums":
            return scope, self.search_albums(
                query, limit=limit, attempts=attempts, base_delay=base_delay,
                sleep=sleep, client_factory=client_factory,
            )
        if scope == "videos":
            return scope, self.search_videos(
                query, limit=limit, attempts=attempts, base_delay=base_delay,
                sleep=sleep, client_factory=client_factory,
            )
        return "songs", self.search_songs(
            query, limit=limit, attempts=attempts, base_delay=base_delay,
            sleep=sleep, client_factory=client_factory,
        )

    def search_songs(
        self,
        query: str,
        limit: int = 20,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> list[Track]:
        raw = self._retry(
            lambda: self._get_client(client_factory).search(
                query, filter="songs", limit=limit
            ),
            f"search-songs({query!r})", attempts, base_delay, sleep, default=[],
        )
        return self._map_results(raw or [])

    def search_videos(
        self,
        query: str,
        limit: int = 20,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> list[Track]:
        raw = self._retry(
            lambda: self._get_client(client_factory).search(
                query, filter="videos", limit=limit
            ),
            f"search-videos({query!r})", attempts, base_delay, sleep, default=[],
        )
        return self._map_results(raw or [])

    def search_albums(
        self,
        query: str,
        limit: int = 20,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> list[Album]:
        raw = self._retry(
            lambda: self._get_client(client_factory).search(
                query, filter="albums", limit=limit
            ),
            f"search-albums({query!r})", attempts, base_delay, sleep, default=[],
        )
        return self._map_albums(raw or [])

    def album(
        self,
        browse_id: str,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> tuple[Album, list[Track]] | None:
        """Album page: (Album, [Track]); None on failure (never raises)."""
        data = self._retry(
            lambda: self._get_client(client_factory).get_album(browseId=browse_id),
            f"album({browse_id})", attempts, base_delay, sleep,
        )
        data = data or {}
        if not data.get("title"):
            return None
        album = Album(
            browse_id=browse_id,
            title=data.get("title", "Unknown album"),
            artist=self._artist_names(data),
            year=data.get("year") or "",
            thumbnail=(data.get("thumbnails") or [{}])[-1].get("url", ""),
        )
        return album, self._map_results(data.get("tracks") or [])

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

    def lyrics(
        self,
        video_id: str,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> str | None:
        """Lyrics text for a track. None when unavailable (never raises)."""
        for attempt in range(attempts):
            try:
                data = self._get_client(client_factory).get_lyrics(video_id)
                text = (data or {}).get("lyrics") or ""
                return text.strip() or None
            except Exception as exc:  # noqa: BLE001 - network layer must not crash UI
                if attempt == attempts - 1:
                    log.info("lyrics(%s) unavailable: %s", video_id, exc)
                    return None
                sleep(base_delay * (2 ** attempt))
        return None

    def radio(
        self,
        video_id: str,
        limit: int = 25,
        attempts: int = RETRY_ATTEMPTS,
        base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable | None = None,
    ) -> list[Track]:
        """Endless-radio seed: tracks related to `video_id`. [] on failure."""
        for attempt in range(attempts):
            try:
                data = self._get_client(client_factory).get_watch_playlist(
                    videoId=video_id, radio=True, limit=limit
                )
                return self._map_results((data or {}).get("tracks") or [])
            except Exception as exc:  # noqa: BLE001
                if attempt == attempts - 1:
                    log.warning("radio(%s) failed after %d attempts: %s",
                                video_id, attempts, exc)
                    return []
                sleep(base_delay * (2 ** attempt))
        return []

    @staticmethod
    def _artist_names(item: dict) -> str:
        """Best-effort artist line across result shapes (song/video/album)."""
        listed = item.get("artists") or []
        if isinstance(listed, list) and listed:
            names = ", ".join(a.get("name", "") for a in listed if isinstance(a, dict))
            if names.strip(", "):
                return names.strip(", ")
        single = item.get("artist") or item.get("owner")
        if isinstance(single, dict) and single.get("name"):
            return single["name"]
        if isinstance(single, str) and single.strip():
            return single.strip()
        author = item.get("author")
        if isinstance(author, str) and author.strip():
            return author.strip()
        return "Unknown artist"

    @classmethod
    def _map_results(cls, results: list[dict]) -> list[Track]:
        tracks: list[Track] = []
        for item in results:
            if not item.get("videoId"):
                continue
            seconds = _duration_to_sec(item.get("duration_seconds")) or _duration_to_sec(item.get("lengthSeconds"))
            tracks.append(
                Track(
                    video_id=item["videoId"],
                    title=item.get("title", "Unknown"),
                    artist=cls._artist_names(item),
                    duration=item.get("duration") or _seconds_to_clock(seconds),
                    duration_sec=seconds,
                    thumbnail=(item.get("thumbnails") or [{}])[-1].get("url", ""),
                    playlist_id=item.get("album", {}).get("id", "") if isinstance(item.get("album"), dict) else "",
                )
            )
        return tracks

    @classmethod
    def _map_albums(cls, results: list[dict]) -> list[Album]:
        albums: list[Album] = []
        for item in results:
            browse_id = item.get("browseId") or item.get("playlistId") or ""
            if not browse_id:
                continue
            albums.append(
                Album(
                    browse_id=browse_id,
                    title=item.get("title", "Unknown album"),
                    artist=cls._artist_names(item),
                    year=item.get("year") or "",
                    thumbnail=(item.get("thumbnails") or [{}])[-1].get("url", ""),
                )
            )
        return albums

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
