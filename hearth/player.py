"""Audio core: pure queue engine + lazy QMediaPlayer backend."""

from __future__ import annotations

import logging
import random

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from . import config
from .models import Track

log = logging.getLogger(__name__)


class QueueEngine:
    """Pure queue logic: history, upcoming, shuffle, repeat. Fully testable."""

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()
        self.history: list[Track] = []
        self.upcoming: list[Track] = []
        self.current: Track | None = None
        self.repeat: str = config.REPEAT_OFF

    def clear(self) -> None:
        self.history.clear()
        self.upcoming.clear()
        self.current = None

    def start_queue(self, tracks: list[Track], start: int = 0) -> Track | None:
        """Replace the queue and start at index `start`."""
        if not tracks or not (0 <= start < len(tracks)):
            return None
        self.clear()
        self.current = tracks[start]
        self.upcoming = list(tracks[start + 1:])
        return self.current

    def play_now(self, track: Track) -> Track:
        """Play immediately; the previous track goes to history."""
        if self.current is not None:
            self.history.append(self.current)
        self.current = track
        return track

    def enqueue(self, track: Track) -> None:
        self.upcoming.append(track)

    def peek_next(self) -> Track | None:
        if self.repeat == config.REPEAT_ONE:
            return self.current
        return self.upcoming[0] if self.upcoming else None

    def advance(self) -> Track | None:
        """Move to the next track honoring repeat modes. None = queue done."""
        if self.repeat == config.REPEAT_ONE and self.current is not None:
            return self.current
        if self.current is not None:
            self.history.append(self.current)
        if not self.upcoming:
            if self.repeat == config.REPEAT_ALL and self.history:
                # Restart the queue in play order (oldest first), so the
                # first thing you heard is the first thing you hear again.
                self.upcoming = list(self.history)
                self.history = []
            else:
                self.current = None
                return None
        self.current = self.upcoming.pop(0)
        return self.current

    def go_back(self) -> Track | None:
        if not self.history:
            return self.current
        if self.current is not None:
            self.upcoming.insert(0, self.current)
        self.current = self.history.pop()
        return self.current

    def shuffle(self) -> None:
        """Non-destructively shuffle the upcoming tracks (history untouched)."""
        self._rng.shuffle(self.upcoming)

    def set_order(self, upcoming: list[Track]) -> None:
        """Replace the upcoming order exactly as given (drag & drop result)."""
        self.upcoming = list(upcoming)


class PlaybackCore(QObject):
    """Wires QueueEngine to Qt Multimedia.

    Stream resolution happens OUTSIDE this class (LoadJob on a dedicated
    pool) so audio decoding never queues behind heavy work. Once a URL is
    resolved, call set_stream() to load and play.
    """

    track_changed = pyqtSignal(object)          # Track | None
    state_changed = pyqtSignal(bool)            # playing
    position_changed = pyqtSignal(int)          # ms
    duration_changed = pyqtSignal(int)          # ms
    queue_changed = pyqtSignal()
    repeat_changed = pyqtSignal(str)
    rate_changed = pyqtSignal(float)
    queue_dry = pyqtSignal(object)                # last track before the queue ran dry
    status = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.engine = QueueEngine()
        self.autoplay: bool = config.AUTOPLAY_DEFAULT
        self._volume = 0.8
        self._rate = 1.0
        self._player = None
        self._audio_out = None
        self._sleep_timer: QTimer | None = None
        self._fade_timer: QTimer | None = None
        self._fade_step = 0
        self._pre_fade_volume = self._volume

        self._poll = QTimer(self)
        self._poll.setInterval(config.SEEK_POLL_MS)
        self._poll.timeout.connect(self._emit_position)

    # --- backend (lazy so headless/CI never touches multimedia) ---

    def _ensure_backend(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._audio_out = QAudioOutput()
            self._audio_out.setVolume(self._volume)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.playbackStateChanged.connect(
                lambda s: self.state_changed.emit(s == QMediaPlayer.PlaybackState.PlayingState)
            )
            self._player.errorOccurred.connect(self._on_error)
            self._player.durationChanged.connect(self.duration_changed.emit)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("audio backend unavailable: %s", exc)
            self.status.emit("Audio backend unavailable")
            return False

    # --- playback ---

    def play_track(self, track: Track) -> None:
        """Mark a track current; the app resolves its stream, then calls set_stream()."""
        self.engine.play_now(track)
        self.track_changed.emit(track)
        self.queue_changed.emit()

    def start_queue(self, tracks: list[Track], start: int = 0) -> None:
        first = self.engine.start_queue(tracks, start)
        self.queue_changed.emit()
        if first is not None:
            self.track_changed.emit(first)

    def enqueue(self, track: Track) -> None:
        self.engine.enqueue(track)
        self.queue_changed.emit()

    def toggle(self) -> None:
        if not self._ensure_backend():
            return
        from PyQt6.QtMultimedia import QMediaPlayer

        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def next(self) -> None:
        last = self.engine.current
        track = self.engine.advance()
        self.queue_changed.emit()
        if track is None:
            if self.autoplay and last is not None:
                # Spotify-style autoplay: the queue ran dry, ask for a radio
                # refill around the last track instead of stopping cold.
                self.status.emit("Queue empty — extending radio…")
                self.queue_dry.emit(last)
                return
            self.stop()
            self.status.emit("Queue finished")
            return
        self.track_changed.emit(track)

    def previous(self) -> None:
        track = self.engine.go_back()
        self.queue_changed.emit()
        if track is not None:
            self.track_changed.emit(track)

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        self.state_changed.emit(False)

    def shuffle(self) -> None:
        self.engine.shuffle()
        self.queue_changed.emit()

    def set_repeat(self, mode: str) -> None:
        if mode not in config.REPEAT_MODES:
            return
        self.engine.repeat = mode
        self.repeat_changed.emit(mode)

    def set_autoplay(self, enabled: bool) -> None:
        self.autoplay = bool(enabled)

    def cycle_repeat(self) -> str:
        order = list(config.REPEAT_MODES)
        nxt = order[(order.index(self.engine.repeat) + 1) % len(order)]
        self.set_repeat(nxt)
        return nxt

    def next_rate(self) -> float:
        rates = list(config.PLAYBACK_RATES)
        idx = rates.index(self._rate) if self._rate in rates else rates.index(1.0)
        self.set_rate(rates[(idx + 1) % len(rates)])
        return self._rate

    def set_rate(self, rate: float) -> None:
        rate = max(0.5, min(2.5, float(rate)))
        self._rate = rate
        if self._player is not None:
            self._player.setPlaybackRate(rate)
        self.rate_changed.emit(rate)

    # --- volume / seek ---

    def set_volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))
        if self._audio_out is not None:
            self._audio_out.setVolume(self._volume)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def rate(self) -> float:
        return self._rate

    def seek(self, position_ms: int) -> None:
        if self._player is not None:
            self._player.setPosition(int(position_ms))

    def apply_normalization(self, loudness_db: float | None) -> float:
        """Scale audio output by the track's loudness gain (returns gain dB)."""
        from .stream import normalization_gain

        gain = normalization_gain(loudness_db)
        if self._audio_out is not None and gain != 0.0:
            self._audio_out.setVolume(self._volume * (10 ** (gain / 20)))
        return gain

    # --- sleep timer with gentle fade ---

    def set_sleep_timer(self, minutes: int | None) -> None:
        if self._sleep_timer is not None:
            self._sleep_timer.stop()
            self._sleep_timer = None
        if self._fade_timer is not None:
            self._fade_timer.stop()
            self._fade_timer = None
            self.set_volume(self._pre_fade_volume)
        if not minutes:
            self.status.emit("Sleep timer cancelled")
            return
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._begin_fade)
        self._sleep_timer.start(int(minutes) * 60_000)
        self.status.emit(f"Sleeping in {minutes} min")

    def _begin_fade(self) -> None:
        self._pre_fade_volume = self._volume
        self._fade_step = 0
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(max(1, config.FADE_INTERVAL_MS // config.FADE_STEPS))
        self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_timer.start()

    def _fade_tick(self) -> None:
        self._fade_step += 1
        if self._fade_step >= config.FADE_STEPS:
            if self._fade_timer is not None:
                self._fade_timer.stop()
                self._fade_timer = None
            self.stop()
            self.set_volume(self._pre_fade_volume)
            self.status.emit("Sleep timer: paused")
            return
        factor = 1.0 - (self._fade_step / config.FADE_STEPS)
        self.set_volume(self._pre_fade_volume * factor)

    # --- internals ---

    def set_stream(self, track: Track, url: str, loudness_db: float | None = None) -> None:
        """Load a resolved stream URL and start playing (called from LoadJob callback)."""
        if not self._ensure_backend():
            return
        if self.engine.current is not None and self.engine.current.video_id != track.video_id:
            return  # user moved on while we were resolving
        self.apply_normalization(loudness_db)
        from PyQt6.QtCore import QUrl

        self._player.setSource(QUrl(url))
        self._player.setPlaybackRate(self._rate)
        self._player.play()
        self._poll.start()
        self.state_changed.emit(True)

    def _on_error(self, err, err_str: str) -> None:
        log.warning("player error: %s", err_str)
        self.status.emit(f"Playback error: {err_str}")
        self.state_changed.emit(False)

    def _emit_position(self) -> None:
        if self._player is not None:
            self.position_changed.emit(self._player.position())
