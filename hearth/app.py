"""Application lifecycle: wiring, persistence, hotkeys, logging."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config
from .catalog import Catalog
from .hotkeys import effective_chords
from .jobs import AlbumJob, LoadJob, LyricsJob, RadioJob, ScopedSearchJob, SearchJob
from .models import Track
from .panel import FloatingPanel
from .player import PlaybackCore
from .storage import HearthStore
from .toast import NowPlayingToast
from .tray import HearthTray, InstanceGuard
from .window import MainWindow

log = logging.getLogger(__name__)

# Module-level registry of in-flight QRunnables. Python must keep each job
# wrapper (and its signal carrier) alive until the pool thread finishes
# run() — an instance-level ref dies with the Hearth object, but a worker
# thread can outlive it and would emit into a deleted carrier.
_INFLIGHT: set = set()


def data_dir() -> Path:
    """Per-OS app data directory (Linux: ~/.local/share/Hearth)."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "hearth.log",
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUPS,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


class Hearth:
    """Owns every component; one instance per process."""

    def __init__(
        self,
        argv: list[str] | None = None,
        settings_path: str | None = None,
        data_directory: Path | None = None,
        single_instance: bool = True,
        enable_streaming: bool = True,
        ui_mode: str | None = None,
    ):
        # Qt allows exactly one QApplication per process — reuse it if the
        # host already created one (tests, embeddings, launcher wrappers).
        self.qapp = QApplication.instance() or QApplication(
            argv if argv is not None else ["hearth"]
        )
        self.qapp.setApplicationName(config.APP_NAME)
        self.qapp.setOrganizationName(config.ORG_NAME)
        self.qapp.setQuitOnLastWindowClosed(False)
        self._enable_streaming = enable_streaming
        flags = " ".join(argv or [])
        if ui_mode is not None:
            self.ui_mode = ui_mode
        elif "--ribbon" in flags:
            self.ui_mode = "ribbon"
        else:
            self.ui_mode = "window"

        self._dir = data_directory or data_dir()
        setup_logging(self._dir)
        self.settings = (
            QSettings(settings_path, QSettings.Format.IniFormat)
            if settings_path else QSettings(config.ORG_NAME, config.APP_NAME)
        )
        self.store = HearthStore(self._dir / "hearth.db")
        self.catalog = Catalog()
        self._lyrics_cache: dict[str, str | None] = {}
        # In-flight jobs are tracked in the module-level _INFLIGHT registry
        # so they survive even if this Hearth object is torn down early.

        self.guard = InstanceGuard() if single_instance else None
        if self.guard is not None and not self.guard.is_primary:
            log.info("Hearth already running — forwarded 'show' and exiting")
            self.store.close()
            return

        palette_key = self.settings.value("theme", config.DEFAULT_PALETTE)

        # Core + UI (panel stays built for ribbon mode; window is the default)
        self.core = PlaybackCore(self.qapp)
        self.panel = FloatingPanel(palette_key)
        self.toast = NowPlayingToast(palette_key)
        self.window = MainWindow(palette_key, store=self.store)
        self.tray: HearthTray | None = None

        self._restore_settings()
        self._wire_panel()
        self._wire_window()
        self._wire_core()
        self._install_hotkeys()
        self._build_tray()
        self._restore_session()
        if self.ui_mode == "window":
            self.panel.hide()
        else:
            self.window.hide()

    # --- wiring ---

    def _wire_panel(self) -> None:
        p = self.panel
        p.search_submitted.connect(self._run_search)
        p.track_picked.connect(self._pick_track)
        p.play_pause_requested.connect(self.core.toggle)
        p.next_requested.connect(self.core.next)
        p.prev_requested.connect(self.core.previous)
        p.shuffle_requested.connect(self.core.shuffle)
        p.repeat_requested.connect(self._cycle_repeat)
        p.volume_changed.connect(self.core.set_volume)
        p.seek_requested.connect(self.core.seek)

    def _wire_window(self) -> None:
        w = self.window
        w.search_submitted.connect(self._run_search)
        w.search_scoped.connect(self._run_scoped_search)
        w.album_opened.connect(self._open_album)
        w.playlist_picked.connect(self._play_list)
        w.play_next_requested.connect(self._play_next)
        w.enqueue_requested.connect(self._enqueue)
        w.pin_toggled.connect(self._toggle_pin)
        w.queue_remove_requested.connect(self._remove_from_queue)
        w.queue_reorder_requested.connect(self._reorder_queue)
        w.queue_jump_requested.connect(self._jump_to_queue_index)
        w.queue_clear_requested.connect(self._clear_queue)
        w.mute_toggled.connect(self._toggle_mute)
        w.radio_requested.connect(self._start_radio)
        w.rate_cycled.connect(self._cycle_rate)
        w.sleep_requested.connect(self._set_sleep)
        w.home_refresh_requested.connect(self._refresh_home)
        w.library_refresh_requested.connect(self._refresh_library)
        w.play_pause_requested.connect(self.core.toggle)
        w.next_requested.connect(self.core.next)
        w.prev_requested.connect(self.core.previous)
        w.shuffle_requested.connect(self.core.shuffle)
        w.repeat_requested.connect(self._cycle_repeat)
        w.volume_changed.connect(self.core.set_volume)
        w.seek_requested.connect(self.core.seek)
        w.refresh_playlists()

    def _wire_core(self) -> None:
        self.core.track_changed.connect(self._on_track_changed)
        self.core.state_changed.connect(self.panel.set_playing)
        self.core.state_changed.connect(self.window.set_playing)
        self.core.position_changed.connect(self.panel.set_position)
        self.core.position_changed.connect(self.window.set_position)
        self.core.duration_changed.connect(self.panel.set_duration)
        self.core.duration_changed.connect(self.window.set_duration)
        self.core.status.connect(self.panel.set_status)
        self.core.queue_changed.connect(self._on_queue_changed)
        self.core.repeat_changed.connect(lambda m: self._persist())
        self.core.rate_changed.connect(lambda r: self._persist())
        self.core.queue_dry.connect(self._on_queue_dry)
        self.core.rate_changed.connect(
            lambda r: self.window.player_bar.set_speed_label(r)
        )

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("No system tray on this desktop — skipping tray icon")
            return
        actions = {
            "play": self._make_action("Play / Pause", self.core.toggle),
            "next": self._make_action("Next", self.core.next),
            "prev": self._make_action("Previous", self.core.previous),
            "show": self._make_action("Show Hearth", self._summon),
        }
        sleep_menu = QMenu("⏾ Sleep timer")
        for label, minutes in (("Off", 0), ("15 minutes", 15),
                               ("30 minutes", 30), ("45 minutes", 45), ("60 minutes", 60)):
            act = QAction(label, sleep_menu)
            act.triggered.connect(
                lambda _checked, m=minutes: self.core.set_sleep_timer(m or None)
            )
            sleep_menu.addAction(act)
        self.tray = HearthTray(actions, menus=[sleep_menu], parent=self.qapp)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _make_action(self, text: str, callback) -> QAction:
        act = QAction(text)
        act.triggered.connect(callback)
        return act

    def _install_hotkeys(self) -> None:
        saved = self.settings.value("hotkeys", {}) or {}
        surface = self.window if self.ui_mode == "window" else self.panel
        for action, chord in effective_chords(saved).items():
            shortcut = QShortcut(QKeySequence(chord), surface)
            shortcut.activated.connect({
                "play_pause": self.core.toggle,
                "next_track": self.core.next,
                "prev_track": self.core.previous,
                "toggle_panel": self._toggle_surface,
                "focus_search": self._focus_search,
            }[action])

    # --- actions ---

    @property
    def surface(self):
        """The active UI surface (main window by default, ribbon legacy)."""
        return self.window if self.ui_mode == "window" else self.panel

    def _run_search(self, query: str) -> None:
        self.surface.set_status("Searching…")
        job = SearchJob(self.catalog, query)
        job.signals.finished.connect(self._show_search_results)
        job.signals.failed.connect(lambda msg: self.surface.set_status(f"Search failed: {msg}"))
        self._launch(job)

    def _run_scoped_search(self, query: str, scope: str) -> None:
        """Songs / Videos / Albums scopes from the search-page chips."""
        if scope == "songs":
            self._run_search(query)
            return
        self.surface.set_status(f"Searching {scope}…")
        job = ScopedSearchJob(self.catalog, query, scope=scope)
        job.signals.finished.connect(self._show_scoped_results)
        job.signals.failed.connect(lambda msg: self.surface.set_status(f"Search failed: {msg}"))
        self._launch(job)

    def _show_scoped_results(self, payload) -> None:
        scope, results = payload
        if scope == "albums":
            self.window.show_album_results(results)
            self.surface.set_status(f"{len(results)} albums" if results else "No albums found")
            return
        self._show_search_results(results)

    def _open_album(self, album) -> None:
        """Album drill-down: fetch the full track list, then open its page."""
        self.surface.set_status(f"Opening {album.title}…")
        job = AlbumJob(self.catalog, album.browse_id)
        job.signals.finished.connect(self._on_album_ready)
        job.signals.failed.connect(
            lambda bid: self.surface.set_status("Could not open that album")
        )
        self._launch(job)

    def _on_album_ready(self, payload) -> None:
        album, tracks = payload
        self.window.open_album(album, tracks)
        self.surface.set_status(f"{album.title} — {len(tracks)} tracks")

    def _show_search_results(self, tracks: list[Track]) -> None:
        self.window.show_search_results(tracks)
        self.panel.show_results(tracks)
        if self.ui_mode == "window":
            self.window.show_view("search")
            self.surface.set_status(f"{len(tracks)} results" if tracks else "No results")

    def _play_list(self, tracks: list[Track], start: int = 0) -> None:
        if not tracks:
            return
        start = max(0, min(int(start), len(tracks) - 1))
        self.core.start_queue(list(tracks), start)

    def _pick_track(self, track: Track) -> None:
        self.core.play_track(track)

    def _play_next(self, track: Track) -> None:
        self.core.engine.upcoming.insert(0, track)
        self.core.queue_changed.emit()

    def _enqueue(self, track: Track) -> None:
        self.core.enqueue(track)

    def _remove_from_queue(self, index: int) -> None:
        upcoming = self.core.engine.upcoming
        if 0 <= index < len(upcoming):
            upcoming.pop(index)
            self.core.queue_changed.emit()

    def _reorder_queue(self, upcoming: list[Track]) -> None:
        """Apply the drag & drop order from the queue dock."""
        self.core.engine.set_order(list(upcoming))
        self.core.queue_changed.emit()

    def _jump_to_queue_index(self, index: int) -> None:
        """Double-click / 'Play now' in the queue: promote that track."""
        upcoming = self.core.engine.upcoming
        if not (0 <= index < len(upcoming)):
            return
        track = upcoming.pop(index)
        self.core.play_track(track)

    def _clear_queue(self) -> None:
        self.core.engine.upcoming.clear()
        self.core.queue_changed.emit()
        self.surface.set_status("Queue cleared")

    _pre_mute_volume: float | None = None

    def _toggle_mute(self) -> None:
        if self.core.volume > 0.0:
            self._pre_mute_volume = self.core.volume
            self.core.set_volume(0.0)
            self.window.set_volume(0.0)
            self.surface.set_status("Muted")
        else:
            restore = self._pre_mute_volume or 0.8
            self.core.set_volume(restore)
            self.window.set_volume(restore)
            self.surface.set_status("Unmuted")

    def _toggle_pin(self, track: Track) -> None:
        if self.store.is_pinned(track.video_id):
            self.store.unpin(track.video_id)
            self.surface.set_status(f"Unpinned: {track.title}")
        else:
            self.store.pin(track)
            self.surface.set_status(f"Pinned: {track.title}")
        self.window.set_pinned(self.store.is_pinned(track.video_id))
        self._refresh_library()

    def _refresh_home(self) -> None:
        self.window.set_recent(self.store.history(12))
        self.window.set_favorites(self.store.favorites()[:12])
        self.window.set_top_tracks(self.store.top_tracks(config.TOP_TRACKS_LIMIT))
        if not self._enable_streaming:
            return  # unit tests: no network shelves
        for query in config.QUICK_PICKS:
            job = SearchJob(self.catalog, query, limit=8)
            job.signals.finished.connect(
                lambda tracks, q=query: self.window.set_home_shelf(
                    "Quick picks", tracks
                ) if tracks else None
            )
            self._launch(job)

    def _refresh_library(self) -> None:
        self.window.set_favorites(self.store.favorites()[:12])
        self.window.set_recent(self.store.history(12))
        self.window.refresh_playlists()

    def _on_queue_changed(self) -> None:
        self.window.set_queue(
            list(self.core.engine.upcoming), self.core.engine.current
        )

    def _on_track_changed(self, track: Track | None) -> None:
        self.panel.set_track(track)
        self.window.set_track(track)
        self.window.set_pinned(
            self.store.is_pinned(track.video_id) if track is not None else False
        )
        self.store.log_play(track)
        self._persist()
        if track is None:
            return
        self.toast.announce(track)
        if not self._enable_streaming:
            return  # test mode: keep the playback pool out of unit tests
        self._fetch_lyrics(track)
        job = LoadJob(track)
        job.signals.finished.connect(
            lambda payload: self.core.set_stream(payload[2], payload[0], payload[1])
        )
        job.signals.failed.connect(
            lambda title: self.surface.set_status(f"Could not resolve: {title}")
        )
        self._launch(job)

    def _launch(self, job) -> None:
        """Start a QRunnable, keeping it referenced until it completes.

        The module-level registry keeps the wrapper (and its signal
        carrier) alive even if the Hearth object itself is torn down
        while a worker thread is still inside run().
        """
        _INFLIGHT.add(job)
        job.signals.finished.connect(lambda *_: _INFLIGHT.discard(job))
        job.signals.failed.connect(lambda *_: _INFLIGHT.discard(job))
        QThreadPool.globalInstance().start(job)

    def _cycle_repeat(self) -> None:
        mode = self.core.cycle_repeat()
        self.panel.set_status(f"Repeat: {mode}")

    def _cycle_rate(self) -> None:
        rate = self.core.next_rate()
        self.surface.set_status(f"Speed {rate:g}x")

    def _set_sleep(self, minutes: int) -> None:
        self.core.set_sleep_timer(minutes or None)
        self.window.player_bar.set_sleep_label(minutes or None)

    # --- radio / autoplay ---

    def _start_radio(self, track: Track | None = None) -> None:
        seed = track or self.core.engine.current
        if seed is None:
            self.surface.set_status("Play something first, then start radio")
            return
        if not self._enable_streaming:
            self.surface.set_status(f"Radio from: {seed.title} (test mode)")
            return
        self.surface.set_status(f"Starting radio from {seed.title}…")
        job = RadioJob(self.catalog, seed.video_id)
        job.signals.finished.connect(self._on_radio_ready)
        job.signals.failed.connect(
            lambda title: self.surface.set_status(f"Radio failed: {title}")
        )
        self._launch(job)

    def _on_radio_ready(self, payload) -> None:
        seed_id, tracks = payload
        fresh: list[Track] = []
        seen = {seed_id}
        for track in tracks:
            if track.video_id in seen:
                continue
            seen.add(track.video_id)
            fresh.append(track)
        if not fresh:
            self.surface.set_status("Radio came back empty — try another seed")
            return
        seed = self.core.engine.current
        if seed is not None and seed.video_id == seed_id:
            queue = [seed, *fresh]
        else:
            queue = fresh
        self.core.start_queue(queue, 0)
        self.surface.set_status(f"Radio: {len(queue)} tracks queued")

    def _on_queue_dry(self, track: Track) -> None:
        """Autoplay: the queue ran out — extend it with a radio seed."""
        if not self._enable_streaming:
            return  # unit tests: keep the playback pool out
        if track is None:
            return
        job = RadioJob(self.catalog, track.video_id)
        job.signals.finished.connect(self._on_autoplay_ready)
        job.signals.failed.connect(
            lambda title: self.surface.set_status(f"Radio failed: {title}")
        )
        self._launch(job)

    def _on_autoplay_ready(self, payload) -> None:
        seed_id, tracks = payload
        engine = self.core.engine
        current = engine.current
        moved_on = current is not None and current.video_id != seed_id
        if moved_on:
            return  # the listener picked something else while we were fetching
        seen = {seed_id} | {t.video_id for t in engine.upcoming} | {
            t.video_id for t in engine.history
        }
        fresh = [t for t in tracks if t.video_id not in seen]
        if not fresh:
            self.core.stop()
            self.core.status.emit("Radio: nothing new found")
            return
        engine.upcoming.extend(fresh)
        self.core.queue_changed.emit()
        self.core.next()  # keep the music going without a hiccup

    # --- lyrics ---

    def _fetch_lyrics(self, track: Track) -> None:
        if track.video_id in self._lyrics_cache:
            self.window.now_view.set_lyrics(track.video_id, self._lyrics_cache[track.video_id])
            return
        if len(self._lyrics_cache) > 200:
            self._lyrics_cache.clear()
        self.window.now_view.set_lyrics_loading()
        job = LyricsJob(self.catalog, track.video_id)
        job.signals.finished.connect(self._on_lyrics_ready)
        self._launch(job)

    def _on_lyrics_ready(self, payload) -> None:
        video_id, text = payload
        self._lyrics_cache[video_id] = text
        self.window.now_view.set_lyrics(video_id, text)

    def _summon(self) -> None:
        if self.ui_mode == "window":
            self.window.summon()
            return
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _toggle_surface(self) -> None:
        if self.ui_mode == "window":
            self.window.setVisible(not self.window.isVisible())
        else:
            self.panel.toggleExpand()

    def _focus_search(self) -> None:
        if self.ui_mode == "window":
            self._summon()
            self.window.focus_search()
            return
        self._summon()
        if not self.panel.expanded:
            self.panel.setExpanded()
        self.panel._search.setFocus()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.surface.setVisible(not self.surface.isVisible())

    # --- persistence ---

    def _restore_settings(self) -> None:
        self.core.set_volume(float(self.settings.value("volume", 0.8)))
        self.panel.set_volume(self.core.volume)
        rate = float(self.settings.value("rate", 1.0))
        self.core.set_rate(rate)
        self.window.player_bar.set_speed_label(self.core.rate)
        repeat = str(self.settings.value("repeat", config.REPEAT_OFF))
        if repeat in config.REPEAT_MODES:
            self.core.set_repeat(repeat)
        autoplay = self.settings.value("autoplay", config.AUTOPLAY_DEFAULT)
        self.core.set_autoplay(
            autoplay in (True, "true", "True", "1", 1)
            if isinstance(autoplay, (str, int)) else bool(autoplay)
        )

    def _restore_session(self) -> None:
        pos = self.settings.value("geometry/pos")
        if pos is not None:
            self.panel.move(pos)
        size = self.settings.value("window/size")
        if size is not None:
            self.window.resize(size)
        win_pos = self.settings.value("window/pos")
        if win_pos is not None:
            self.window.move(win_pos)
        favorites = self.store.favorites()
        if favorites:
            self.surface.set_status(f"{len(favorites)} favorites pinned")
        self._refresh_home()
        self._refresh_library()

    def _persist(self) -> None:
        self.settings.setValue("volume", self.core.volume)
        self.settings.setValue("rate", self.core.rate)
        self.settings.setValue("repeat", self.core.engine.repeat)
        self.settings.setValue("autoplay", self.core.autoplay)
        self.settings.setValue("theme", self.panel._palette.key)
        self.settings.setValue("geometry/pos", self.panel.pos())
        self.settings.setValue("window/size", self.window.size())
        self.settings.setValue("window/pos", self.window.pos())

    def shutdown(self) -> None:
        # Let in-flight jobs land while their recipients are still alive.
        QThreadPool.globalInstance().waitForDone(5000)
        self._persist()
        self.store.close()

    # --- run ---

    def run(self) -> int:
        if self.guard is not None and not self.guard.is_primary:
            return 0
        if self.ui_mode == "window":
            self.window.show()
        else:
            self.panel.show()
        code = self.qapp.exec()
        self.shutdown()
        return code


def main() -> int:
    hearth = Hearth(single_instance="--no-single-instance" not in sys.argv)
    return hearth.run()
