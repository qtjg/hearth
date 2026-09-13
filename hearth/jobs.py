"""QRunnable workers on isolated thread pools (search vs load never queue together)."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from .catalog import Catalog
from .models import Track
from .stream import resolve_stream_url

log = logging.getLogger(__name__)


class _SignalCarrier(QObject):
    finished = pyqtSignal(object)   # list[Track] or (url, loudness)
    failed = pyqtSignal(str)

    def emit_safe(self, signal, payload) -> None:
        """Emit defensively: the recipient may have closed before we finished."""
        try:
            signal.emit(payload)
        except RuntimeError:
            log.debug("signal carrier gone — recipient closed before job finished")


class SearchJob(QRunnable):
    """Runs on the background pool — heavy catalogue queries (songs)."""

    def __init__(self, catalog: Catalog, query: str, limit: int = 20):
        super().__init__()
        self.setAutoDelete(False)  # lifetime managed by Hearth._jobs, not the pool
        self.signals = _SignalCarrier()
        self.catalog = catalog
        self.query = query
        self.limit = limit

    def run(self) -> None:  # noqa: D102 - QRunnable entry
        from .catalog import parse_video_id

        video_id = parse_video_id(self.query)
        if video_id:
            track = self.catalog.song_details(video_id)
            self.signals.emit_safe(self.signals.finished, [track] if track else [])
        else:
            self.signals.emit_safe(self.signals.finished,
                                   self.catalog.search(self.query, limit=self.limit))


class ScopedSearchJob(QRunnable):
    """Search with a scope tag; emits (scope, tracks|albums)."""

    def __init__(self, catalog: Catalog, query: str, scope: str = "songs",
                 limit: int = 20):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _SignalCarrier()
        self.catalog = catalog
        self.query = query
        self.scope = scope
        self.limit = limit

    def run(self) -> None:  # noqa: D102
        from .catalog import parse_video_id

        video_id = parse_video_id(self.query)
        if video_id:
            track = self.catalog.song_details(video_id)
            self.signals.emit_safe(self.signals.finished,
                                   ("songs", [track] if track else []))
        else:
            self.signals.emit_safe(
                self.signals.finished,
                self.catalog.scoped_search(self.query, scope=self.scope,
                                           limit=self.limit),
            )


class AlbumJob(QRunnable):
    """Opens an album page; emits (Album, [Track])."""

    def __init__(self, catalog: Catalog, browse_id: str):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _SignalCarrier()
        self.catalog = catalog
        self.browse_id = browse_id

    def run(self) -> None:  # noqa: D102
        payload = self.catalog.album(self.browse_id)
        if payload is not None:
            self.signals.emit_safe(self.signals.finished, payload)
        else:
            self.signals.emit_safe(self.signals.failed, self.browse_id)


class LoadJob(QRunnable):
    """Runs on the dedicated playback pool — stream resolution never waits on anything."""

    def __init__(self, track: Track):
        super().__init__()
        self.setAutoDelete(False)  # lifetime managed by Hearth._jobs, not the pool
        self.signals = _SignalCarrier()
        self.track = track

    def run(self) -> None:  # noqa: D102
        url, loudness = resolve_stream_url(
            f"https://www.youtube.com/watch?v={self.track.video_id}"
        )
        if url:
            self.signals.emit_safe(self.signals.finished, (url, loudness, self.track))
        else:
            self.signals.emit_safe(self.signals.failed, self.track.title)


class LyricsJob(QRunnable):
    """Fetches lyrics for the current track off the main thread."""

    def __init__(self, catalog: Catalog, video_id: str):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _SignalCarrier()
        self.catalog = catalog
        self.video_id = video_id

    def run(self) -> None:  # noqa: D102
        text = self.catalog.lyrics(self.video_id)
        self.signals.emit_safe(self.signals.finished, (self.video_id, text))


class RadioJob(QRunnable):
    """Seeds an endless-radio queue from one track off the main thread."""

    def __init__(self, catalog: Catalog, video_id: str, limit: int = 25):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _SignalCarrier()
        self.catalog = catalog
        self.video_id = video_id
        self.limit = limit

    def run(self) -> None:  # noqa: D102
        from . import config

        tracks = self.catalog.radio(self.video_id, limit=self.limit or config.RADIO_LIMIT)
        self.signals.emit_safe(self.signals.finished, (self.video_id, tracks))
