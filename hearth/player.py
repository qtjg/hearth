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

    MAX_ERROR_SKIPS = 3   # mid-play deaths in a row before we give up

    track_changed = pyqtSignal(object)          # Track | None
    state_changed = pyqtSignal(bool)            # playing
    position_changed = pyqtSignal(int)          # ms
    duration_changed = pyqtSignal(int)          # ms
    queue_changed = pyqtSignal()
    repeat_changed = pyqtSignal(str)
    rate_changed = pyqtSignal(float)
    queue_dry = pyqtSignal(object)                # last track before the queue ran dry
    stream_lost = pyqtSignal(object, int)         # (track, resume_ms) — mid-song death
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

        # --- stream self-healing state (see config STREAM_*) ---
        self._playing = False            # mirrors the backend, minus the Qt enum
        self._last_pos_ms = 0            # last position we actually observed
        self._stream_anchor_ms = 0       # position this stream was joined at
        self._stall_polls = 0            # consecutive polls with a frozen position
        self._retries = 0                # rejoin attempts spent on the current track
        self._recovered_id: str | None = None   # which track the budget belongs to
        self._end_of_media = None        # Qt enum, resolved with the backend
        self._error_streak = 0
        self._recover_armed = True   # one error-skip per track that actually played

        # --- restored-session state (queue persistence, v0.7.0) ---
        self._resume_pending: Track | None = None   # waiting for the first play
        self._resume_ms = 0                         # where the song was left
        self._armed_resume_ms = 0                   # consumed by the next set_stream

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
            self._player.playbackStateChanged.connect(self._on_playback_state)
            self._player.mediaStatusChanged.connect(self._on_media_status)
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
        self._error_streak = 0   # user-driven movement: fresh faith in the backend
        self._resume_pending = None
        self._resume_ms = 0
        self.engine.play_now(track)
        self.track_changed.emit(track)
        self.queue_changed.emit()

    def start_queue(self, tracks: list[Track], start: int = 0) -> None:
        self._error_streak = 0
        self._resume_pending = None
        self._resume_ms = 0
        first = self.engine.start_queue(tracks, start)
        self.queue_changed.emit()
        if first is not None:
            self.track_changed.emit(first)

    def enqueue(self, track: Track) -> None:
        self.engine.enqueue(track)
        self.queue_changed.emit()

    def restore_queue(
        self,
        current: Track | None,
        history: list[Track] | None = None,
        upcoming: list[Track] | None = None,
        resume_ms: int = 0,
    ) -> None:
        """Rebuild the last session's queue without making a sound.

        The queue comes back exactly as it was left. No track_changed is
        emitted, so nothing resolves, nothing plays — pressing play
        resumes the current track at `resume_ms` instead of starting cold.
        """
        self.engine.clear()
        self.engine.history = list(history or [])
        self.engine.current = current
        self.engine.upcoming = list(upcoming or [])
        self._resume_pending = current
        self._resume_ms = max(0, int(resume_ms))
        self.queue_changed.emit()

    def toggle(self) -> None:
        if self._resume_pending is not None:
            # A restored session waiting for its first play: resolve the
            # stream and let set_stream() rejoin at the saved position.
            track = self._resume_pending
            self._armed_resume_ms = self._resume_ms
            self._resume_pending = None
            self._resume_ms = 0
            self.track_changed.emit(track)
            return
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
        self._error_streak = 0
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

    @property
    def position_ms(self) -> int:
        """Best-known position: the live backend if present, else observed."""
        if self._player is not None:
            try:
                return int(self._player.position())
            except (RuntimeError, AttributeError):
                pass
        return self._last_pos_ms

    @property
    def session_position_ms(self) -> int:
        """Where a restored session would resume; the live position otherwise."""
        if self._resume_pending is not None:
            return self._resume_ms
        return self.position_ms

    def _effective_resume(self, resume_ms: int) -> int:
        """Explicit resume wins; else a restored-session resume, once."""
        explicit = max(0, int(resume_ms))
        if explicit:
            return explicit
        armed, self._armed_resume_ms = self._armed_resume_ms, 0
        return max(0, int(armed))

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

    def set_stream(
        self,
        track: Track,
        url: str,
        loudness_db: float | None = None,
        resume_ms: int = 0,
    ) -> None:
        """Load a resolved stream URL and start playing (LoadJob callback).

        `resume_ms` rejoins a track that died mid-song: the position it
        stopped at, minus a small backstep so a truncating stream can't
        tip us straight back into end-of-media.
        """
        if not self._ensure_backend():
            return
        if self.engine.current is not None and self.engine.current.video_id != track.video_id:
            return  # user moved on while we were resolving
        if self._recovered_id != track.video_id:
            self._recovered_id = track.video_id
            self._retries = 0  # a fresh track gets a fresh budget
        self.apply_normalization(loudness_db)
        from PyQt6.QtCore import QUrl

        rejoin_ms = self._effective_resume(resume_ms)
        rejoin = max(0, rejoin_ms - config.STREAM_RESUME_BACKSTEP_MS) if rejoin_ms else 0
        self._player.setSource(QUrl(url))
        self._player.setPlaybackRate(self._rate)
        self._player.play()
        if rejoin:
            self._player.setPosition(rejoin)
        self._poll.start()
        self._playing = True  # the backend signal confirms or corrects
        self._last_pos_ms = rejoin
        self._stream_anchor_ms = rejoin
        self._stall_polls = 0
        self.state_changed.emit(True)

    def _try_rejoin(self, track: Track, reason: str) -> bool:
        """Ask for a freshly resolved URL and rejoin this very song.

        Budget-guarded (config STREAM_*): the budget renews once the
        stream has played healthily for a while, so one flaky minute
        can't strand the session — but a truly dead track falls through
        to the error-skip path after a few honest tries.
        """
        if self._last_pos_ms - self._stream_anchor_ms >= config.STREAM_RECOVERY_RESET_MS:
            self._retries = 0   # it genuinely played — this is a new mishap
        if self._recovered_id != track.video_id:
            self._recovered_id = track.video_id
            self._retries = 0
        if self._retries >= config.STREAM_MAX_RECOVERIES:
            return False
        self._retries += 1
        self.status.emit(f"Stream {reason} — picking it back up…")
        self.stream_lost.emit(track, int(self._last_pos_ms))
        return True

    def _on_playback_state(self, state) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer

        self._note_playing(state == QMediaPlayer.PlaybackState.PlayingState)

    def _note_playing(self, playing: bool) -> None:
        self._playing = playing
        if playing:
            self._recover_armed = True   # audio actually flowed — re-arm the skip guard
        self.state_changed.emit(playing)

    def _on_media_status(self, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer

        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        self._on_end_of_media()

    def _on_end_of_media(self) -> None:
        """Track finished naturally — roll straight into the next one.

        The v0.2.0 rewrite of the audio core dropped the v0.1.0
        EndOfMedia relay: tracks ended and playback went silent instead
        of advancing. This restores it (repeat modes and autoplay are
        already handled by next() and the queue_dry -> radio refill
        chain in the app layer).
        """
        log.debug("track finished — rolling into the next one")
        self._error_streak = 0   # a natural finish proves the pipeline is healthy
        self.next()

    def _on_error(self, err, err_str: str) -> None:
        log.warning("player error: %s", err_str)
        self.state_changed.emit(False)
        current = self.engine.current
        if current is None:
            self.status.emit(f"Playback error: {err_str}")
            return
        # The song was audibly underway: rejoin it with a fresh URL and
        # pick up where it stopped, instead of losing it to a skip.
        if self._last_pos_ms > 0 and self._try_rejoin(current, "dropped"):
            return
        if not self._recover_armed or self._error_streak >= self.MAX_ERROR_SKIPS:
            self.stop()
            self.status.emit("Playback stopped — too many errors in a row")
            return
        self._recover_armed = False
        self._error_streak += 1
        log.warning("recovering from player error — skipping %s", current.title)
        self.status.emit("Skipping past the bad stream…")
        self.next()

    def _emit_position(self) -> None:
        if self._player is None:
            return
        pos = self._player.position()
        if self._playing and pos == self._last_pos_ms:
            # "Playing" but going nowhere: the stream died without ever
            # raising an error. Give the watchdog a few polls, then rejoin.
            self._stall_polls += 1
            if self._stall_polls >= config.STALL_POLLS:
                self._stall_polls = 0
                current = self.engine.current
                if current is not None:
                    self._try_rejoin(current, "stalled")
        else:
            self._stall_polls = 0
            self._last_pos_ms = pos
        self.position_changed.emit(pos)
