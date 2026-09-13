"""
player.py
PlaybackCore owns the queue, the media player and the thread pools.

Flow for one track:
    play(track)  ->  LoadJob (dedicated playback pool)  ->  setSource + play
                 \->  RadioJob (background pool)        ->  queue grows behind it

Stream resolution and queue building run on isolated pools so audio starts the
moment the stream URL lands, never queued behind recommendations or artwork.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import QObject, QThreadPool, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from .catalog import CatalogSource
from .config import MAX_RATE, MIN_RATE, RADIO_DEPTH, RATE_STEPS, REPEAT_MODES, SEEK_MS_BACKSTEP
from .jobs import LinkJob, LoadJob, RadioJob
from .models import Track
from .stream import StreamResolver

log = logging.getLogger(__name__)

MAX_AUTO_SKIP = 3   # consecutive dead tracks before we stop advancing
MAX_QUEUE_SIZE = 200


def clamp_rate(value: float, fallback: float = 1.0) -> float:
    """Coerce any incoming rate into [MIN_RATE, MAX_RATE], rejecting NaN."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return fallback
    if rate != rate:  # NaN
        return fallback
    return max(MIN_RATE, min(MAX_RATE, rate))


def next_repeat_mode(mode: str) -> str:
    """off -> all -> one -> off, tolerating unknown input."""
    order = list(REPEAT_MODES)
    try:
        idx = order.index(mode)
    except ValueError:
        return order[0]
    return order[(idx + 1) % len(order)]


class PlaybackCore(QObject):
    """Core engine controlling audio playback, thread pools, and the queue."""

    track_changed = pyqtSignal(object)      # Track now loading / playing
    cursor_changed = pyqtSignal(int)        # index inside the queue
    queue_changed = pyqtSignal(list)        # whole queue replaced or extended
    playing_changed = pyqtSignal(bool)
    progress_changed = pyqtSignal(int)      # ms
    length_changed = pyqtSignal(int)        # ms
    loading_changed = pyqtSignal(bool)
    notice = pyqtSignal(str)                # short human line for the status chip
    repeat_mode_changed = pyqtSignal(str)   # 'off', 'all', 'one'
    rate_changed = pyqtSignal(float)

    def __init__(
        self,
        catalog: CatalogSource,
        resolver: StreamResolver,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.resolver = resolver

        # Dedicated pool for stream resolution so audio never queues behind radio/art
        self.playback_pool = QThreadPool(self)
        self.playback_pool.setMaxThreadCount(2)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(6)

        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)

        self.queue: List[Track] = []
        self.cursor = -1
        self.auto_queue = True
        self.repeat_mode: str = "off"
        self.playback_rate: float = 1.0

        self._wanted: Optional[str] = None
        self._failed_id: Optional[str] = None
        self._error_streak = 0
        self._extending = False
        self._advance_after_extend = False
        self._radio_seed: Optional[str] = None

        self.player.positionChanged.connect(self._relay_progress)
        self.player.durationChanged.connect(self._relay_length)
        self.player.playbackStateChanged.connect(self._relay_state)
        self.player.mediaStatusChanged.connect(self._relay_media_status)
        self.player.errorOccurred.connect(self._relay_error)

    # ------------------------------------------------------------------ state
    @property
    def current(self) -> Optional[Track]:
        """Track under the cursor, if any."""
        if 0 <= self.cursor < len(self.queue):
            return self.queue[self.cursor]
        return None

    def index_of(self, video_id: str) -> int:
        for index, track in enumerate(self.queue):
            if track.video_id == video_id:
                return index
        return -1

    @property
    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ------------------------------------------------------------------- queue
    def adopt(self, tracks: List[Track], start: int = 0) -> None:
        """Replace the queue wholesale (search results / pasted link) and play."""
        if not tracks:
            return
        start = max(0, min(start, len(tracks) - 1))
        self.queue = list(tracks)
        self.cursor = start
        self.queue_changed.emit(self.queue)
        self.cursor_changed.emit(start)
        self.play(self.queue[start], expand=True)

    def play(self, track: Optional[Track], expand: Optional[bool] = None) -> None:
        """Queue and begin stream resolution for a track."""
        if track is None:
            return
        if expand is None:
            expand = self.auto_queue

        slot = self.index_of(track.video_id)
        if slot < 0:
            self.queue = [track]
            self.cursor = 0
            self.queue_changed.emit(self.queue)
            self.cursor_changed.emit(0)
        elif slot != self.cursor:
            self.cursor = slot
            self.cursor_changed.emit(slot)

        self._wanted = track.video_id
        self._failed_id = None  # allow manual retries of failed tracks
        self.loading_changed.emit(True)
        self.track_changed.emit(track)

        # Never pool.clear() here: deleting an in-flight job's signal carrier
        # mid-emit wedges the loading state. Stale results are dropped by the
        # _wanted identity check in the slots instead.
        self._start_load(track)
        if expand:
            self._start_radio(track.video_id)

    def play_at(self, index: int) -> None:
        if not 0 <= index < len(self.queue):
            return
        self.cursor = index
        self.cursor_changed.emit(index)
        self.play(self.queue[index], expand=False)

    # --------------------------------------------------------------- transport
    def pause(self) -> None:
        self.player.pause()

    def resume(self) -> None:
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            if self.current is not None:
                self.play(self.current, expand=False)
            elif self.queue:
                self.play_at(0)

    def toggle(self) -> None:
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        else:
            if self.current is not None:
                self.play(self.current, expand=False)
            elif self.queue:
                self.play_at(0)

    def forward(self, force: bool = False) -> None:
        """Next track, honoring repeat modes; fetch more at the tail."""
        if not force and self.repeat_mode == "one" and self.current is not None:
            self.player.setPosition(0)
            self.player.play()
            return
        if self.cursor + 1 < len(self.queue):
            self.play_at(self.cursor + 1)
            return
        if self.repeat_mode == "all" and self.queue:
            self.play_at(0)
            return
        if not self.queue or self._extending:
            return
        # Tail of the queue: ask the recommendation graph for more, then advance.
        self._extending = True
        self._advance_after_extend = True
        self.notice.emit("finding more like this")
        self._start_radio(self.queue[-1].video_id, force=True)

    def back(self) -> None:
        """Previous track, or restart the current one if we're deep into it."""
        if self.player.position() > SEEK_MS_BACKSTEP:
            self.player.setPosition(0)
            return
        if self.cursor > 0:
            self.play_at(self.cursor - 1)
        elif self.repeat_mode == "all" and self.queue:
            self.play_at(len(self.queue) - 1)
        else:
            self.player.setPosition(0)

    def seek(self, position_ms: int) -> None:
        self.player.setPosition(max(0, int(position_ms)))

    # ------------------------------------------------------------ modes & tuning
    def set_repeat_mode(self, mode: str) -> None:
        mode = mode if mode in REPEAT_MODES else "off"
        self.repeat_mode = mode
        self.repeat_mode_changed.emit(mode)
        self.notice.emit(f"repeat {mode}")

    def cycle_repeat_mode(self) -> str:
        mode = next_repeat_mode(self.repeat_mode)
        self.set_repeat_mode(mode)
        return mode

    def set_playback_rate(self, rate: float) -> None:
        self.playback_rate = clamp_rate(rate)
        self.player.setPlaybackRate(self.playback_rate)
        self.rate_changed.emit(self.playback_rate)
        self.notice.emit(f"speed {self.playback_rate:g}x")

    def cycle_playback_rate(self) -> float:
        """Step through RATE_STEPS, resetting to 1.0 from unknown rates."""
        try:
            idx = RATE_STEPS.index(self.playback_rate)
        except ValueError:
            idx = -1
        self.set_playback_rate(RATE_STEPS[(idx + 1) % len(RATE_STEPS)])
        return self.playback_rate

    def set_volume(self, percent: int) -> None:
        self.output.setVolume(max(0, min(100, int(percent))) / 100.0)

    def set_auto_queue(self, enabled: bool) -> None:
        self.auto_queue = bool(enabled)

    def restore_session(self, repeat_mode: str, rate: float) -> None:
        """Silently restore persisted state at boot (no status notices)."""
        if repeat_mode in REPEAT_MODES:
            self.repeat_mode = repeat_mode
            self.repeat_mode_changed.emit(self.repeat_mode)
        self.playback_rate = clamp_rate(rate)
        self.player.setPlaybackRate(self.playback_rate)
        self.rate_changed.emit(self.playback_rate)

    # ------------------------------------------------------------------ link open
    def open_link(self, url: str) -> None:
        """Resolve a pasted URL into a Track, then play it like anything else."""
        self.notice.emit("reading that link")
        job = LinkJob(self.resolver, url)
        job.signals.ready.connect(self._on_link_track)
        job.signals.failed.connect(self._on_link_failed)
        self.pool.start(job)

    # ------------------------------------------------------------------- loading
    def _start_load(self, track: Track) -> None:
        job = LoadJob(track, self.resolver)
        job.signals.ready.connect(self._on_stream_ready)
        job.signals.failed.connect(self._on_stream_failed)
        self.playback_pool.start(job)

    def _start_radio(self, seed_id: str, force: bool = False) -> None:
        if not force and self._radio_seed == seed_id:
            return
        self._radio_seed = seed_id
        job = RadioJob(self.catalog, seed_id, RADIO_DEPTH)
        job.signals.ready.connect(self._on_radio_ready)
        job.signals.failed.connect(self._on_radio_failed)
        self.pool.start(job)

    # ---------------------------------------------------------------------- slots
    def _on_stream_ready(self, track: Track, url: str) -> None:
        if track.video_id != self._wanted:
            return  # the user already moved on
        track.stream_url = url
        self._failed_id = None
        self.player.setSource(QUrl(url))
        self.player.play()
        self.loading_changed.emit(False)

    def _on_stream_failed(self, track: Track, message: str) -> None:
        if track.video_id != self._wanted:
            return
        self.loading_changed.emit(False)
        self.notice.emit("skipping unavailable track")
        log.warning("playback aborted for %s: %s", track.video_id, message)
        self._error_streak += 1
        if self._error_streak <= MAX_AUTO_SKIP and self.cursor + 1 < len(self.queue):
            self.forward(force=True)
            return
        self._error_streak = 0

    def _on_radio_ready(self, seed_id: str, tracks: list) -> None:
        self._extending = False
        if seed_id != self._radio_seed:
            self._advance_after_extend = False
            return
        current = self.current
        if current is None or current.video_id != seed_id or not tracks:
            self._advance_after_extend = False
            return
        known = {t.video_id for t in self.queue}
        fresh = [t for t in tracks if t.video_id not in known]
        if fresh:
            self.queue.extend(fresh)
            if len(self.queue) > MAX_QUEUE_SIZE and self.cursor > 10:
                trim = self.cursor - 5
                self.queue = self.queue[trim:]
                self.cursor -= trim
                self.cursor_changed.emit(self.cursor)
            self.queue_changed.emit(self.queue)
        if self._advance_after_extend:
            self._advance_after_extend = False
            if self.cursor + 1 < len(self.queue):
                self.play_at(self.cursor + 1)

    def _on_radio_failed(self, seed_id: str, message: str) -> None:
        self._extending = False
        self._advance_after_extend = False
        log.debug("radio unavailable for %s: %s", seed_id, message)

    def _on_link_track(self, track: Track) -> None:
        self.adopt([track], 0)

    def _on_link_failed(self, message: str) -> None:
        self.notice.emit("that link didn't work")
        log.warning("link playback failed: %s", message)

    # --------------------------------------------------------------- media relays
    def _relay_progress(self, position_ms: int) -> None:
        self.progress_changed.emit(int(position_ms))

    def _relay_length(self, duration_ms: int) -> None:
        self.length_changed.emit(int(duration_ms))

    def _relay_state(self, state: QMediaPlayer.PlaybackState) -> None:
        # Only a track that truly reaches PlayingState clears the skip budget —
        # resetting on stream-ready would defeat MAX_AUTO_SKIP entirely.
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._error_streak = 0
        self.playing_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _relay_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        log.debug("track finished — rolling into the next one")
        if self.repeat_mode == "one" and self.current is not None:
            self.player.setPosition(0)
            self.player.play()
            return
        if self.repeat_mode == "all" and self.cursor + 1 >= len(self.queue) and self.queue:
            self.play_at(0)
            return
        self.forward(force=True)

    def _relay_error(self, error: QMediaPlayer.Error, message: str) -> None:
        # Guard on track identity: every resolve mints a fresh signed URL, so a
        # URL comparison never matches and the backend would walk the queue.
        if self._wanted is not None and self._failed_id == self._wanted:
            return  # already handled this track's failure
        self._failed_id = self._wanted
        log.warning("media player error (%s): %s", error, message)
        self.player.stop()
        self.loading_changed.emit(False)
        self._error_streak += 1
        if self._error_streak <= MAX_AUTO_SKIP and self.cursor + 1 < len(self.queue):
            self.notice.emit("skipping a dead track")
            self.forward(force=True)
            return
        self._error_streak = 0
        if self.queue:
            self.notice.emit("playback hiccup")
