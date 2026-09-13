"""
catalog.py
Read-only access to the public YouTube Music catalogue: free-text search and
the watch-playlist recommendation graph that keeps the queue endless.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from ytmusicapi import YTMusic

from .models import Track

log = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    operation: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 0.6,
    operation_name: str = "request",
    **kwargs: Any,
) -> T:
    """Run a network-bound callable with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                log.warning(
                    "%s attempt %d/%d failed: %s — retrying in %.1fs",
                    operation_name, attempt, max_attempts, exc, delay,
                )
                time.sleep(delay)
            else:
                log.error("%s failed after %d attempts: %s", operation_name, max_attempts, exc)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{operation_name} failed without exception")


def artist_line(item: Dict[str, Any]) -> str:
    """Normalize ytmusicapi's artist shapes into one display string."""
    raw = item.get("artists") or item.get("author") or []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        names = [
            entry.get("name")
            for entry in raw
            if isinstance(entry, dict) and entry.get("name")
        ]
        if names:
            return ", ".join(names)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "unknown artist"


def artwork_url(item: Dict[str, Any]) -> str:
    """Pick the highest-resolution thumbnail available on the item."""
    raw = item.get("thumbnails") or item.get("thumbnail") or []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list) and raw:
        valid = [e for e in raw if isinstance(e, dict) and e.get("url")]
        if valid:
            def area(e: Dict[str, Any]) -> int:
                try:
                    return int(e.get("width") or 0) * int(e.get("height") or 0)
                except (TypeError, ValueError):
                    return 0
            valid.sort(key=area)
            return valid[-1].get("url") or ""
    return ""


def build_track(item: Any, duration_key: str = "duration") -> Optional[Track]:
    """Map a raw catalogue dict to a Track, or None when unusable."""
    if not isinstance(item, dict):
        return None
    video_id = item.get("videoId")
    if not video_id:
        return None
    return Track(
        video_id=str(video_id),
        title=str(item.get("title") or "untitled"),
        artist=artist_line(item),
        duration=str(item.get(duration_key) or ""),
        artwork_url=artwork_url(item),
    )


class CatalogSource:
    """Wraps the guest (no-login) YouTube Music client with resilient retries."""

    def __init__(self) -> None:
        self.api = YTMusic()
        log.info("catalogue client ready")

    def search(self, query: str, limit: int = 12) -> List[Track]:
        """Free-text song search. Raises after persistent failure."""
        query = (query or "").strip()
        if not query:
            return []
        raw = with_retry(
            lambda: self.api.search(query, filter="songs", limit=limit),
            max_attempts=3, base_delay=0.5, operation_name=f"search({query!r})",
        )
        found = [t for t in (build_track(i) for i in raw or []) if t]
        log.info("search %r -> %d track(s)", query, len(found))
        return found

    def similar(self, seed_id: str, limit: int = 25) -> List[Track]:
        """Look-alike tracks around a seed. Best effort: returns [] on failure."""
        related: List[Track] = []
        seen = {seed_id}
        try:
            watch = with_retry(
                lambda: self.api.get_watch_playlist(videoId=seed_id, limit=limit),
                max_attempts=2, base_delay=0.6, operation_name=f"radio({seed_id})",
            )
        except Exception as exc:
            log.warning("radio lookup failed for %s: %s", seed_id, exc)
            return related
        for item in watch.get("tracks") or []:
            track = build_track(item, duration_key="length")
            if not track or track.video_id in seen:
                continue
            seen.add(track.video_id)
            related.append(track)
        return related
