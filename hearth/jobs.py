"""
jobs.py
Every blocking operation Hearth performs, wrapped as a QRunnable for the
thread pools. Each job owns a tiny QObject signal carrier — QRunnable cannot
declare signals itself.
"""

from __future__ import annotations

import logging
from typing import List

import requests
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from .catalog import CatalogSource
from .models import Track
from .stream import StreamResolver

log = logging.getLogger(__name__)


class _Signals(QObject):
    """Base carrier so each job subclass only declares what it needs."""


# --------------------------------------------------------------------- search
class SearchSignals(_Signals):
    done = pyqtSignal(str, list)
    failed = pyqtSignal(str, str)


class SearchJob(QRunnable):
    """Off-thread catalogue search."""

    def __init__(self, catalog: CatalogSource, query: str, limit: int = 12) -> None:
        super().__init__()
        self.catalog = catalog
        self.query = query
        self.limit = limit
        self.signals = SearchSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            results = self.catalog.search(self.query, self.limit)
            self.signals.done.emit(self.query, results)
        except Exception as exc:
            log.warning("search job failed for %r: %s", self.query, exc)
            self.signals.failed.emit(self.query, str(exc))


# ---------------------------------------------------------------------- radio
class RadioSignals(_Signals):
    ready = pyqtSignal(str, list)
    failed = pyqtSignal(str, str)


class RadioJob(QRunnable):
    """Off-thread recommendation-graph expansion."""

    def __init__(self, catalog: CatalogSource, seed_id: str, limit: int = 25) -> None:
        super().__init__()
        self.catalog = catalog
        self.seed_id = seed_id
        self.limit = limit
        self.signals = RadioSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            recommendations = self.catalog.similar(self.seed_id, self.limit)
            self.signals.ready.emit(self.seed_id, recommendations)
        except Exception as exc:
            log.debug("radio job failed for %s: %s", self.seed_id, exc)
            self.signals.failed.emit(self.seed_id, str(exc))


# ----------------------------------------------------------------------- load
class LoadSignals(_Signals):
    ready = pyqtSignal(object, str)
    failed = pyqtSignal(object, str)


class LoadJob(QRunnable):
    """Resolve the audio stream for one track; emits the Track back with its URL."""

    def __init__(self, track: Track, resolver: StreamResolver) -> None:
        super().__init__()
        self.track = track
        self.resolver = resolver
        self.signals = LoadSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            url = self.resolver.stream_url(self.track.video_id)
            if not url:
                raise RuntimeError("no playable audio stream returned")
            self.signals.ready.emit(self.track, url)
        except Exception as exc:
            log.warning("stream resolve failed for %s: %s", self.track.video_id, exc)
            self.signals.failed.emit(self.track, str(exc))


# ------------------------------------------------------------------ pasted url
class LinkSignals(_Signals):
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)


class LinkJob(QRunnable):
    """Turn an arbitrary video/song URL into a Track."""

    def __init__(self, resolver: StreamResolver, url: str) -> None:
        super().__init__()
        self.resolver = resolver
        self.url = url
        self.signals = LinkSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            track = self.resolver.describe(self.url)
            if track is None:
                raise RuntimeError("that link did not resolve to a track")
            self.signals.ready.emit(track)
        except Exception as exc:
            log.warning("link resolve failed for %r: %s", self.url, exc)
            self.signals.failed.emit(str(exc))


# -------------------------------------------------------------------- artwork
class ArtSignals(_Signals):
    arrived = pyqtSignal(str, bytes)
    failed = pyqtSignal(str, str)


class ArtJob(QRunnable):
    """Best-effort cover-art download with timeout guards."""

    def __init__(self, track_id: str, url: str, timeout: float = 6.0) -> None:
        super().__init__()
        self.track_id = track_id
        self.url = url
        self.timeout = timeout
        self.signals = ArtSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            with requests.get(self.url, timeout=self.timeout) as response:
                if response.status_code == 200 and response.content:
                    self.signals.arrived.emit(self.track_id, response.content)
                else:
                    self.signals.failed.emit(self.track_id, f"HTTP {response.status_code}")
        except Exception as exc:
            log.debug("artwork fetch failed for %s: %s", self.track_id, exc)
            self.signals.failed.emit(self.track_id, str(exc))
