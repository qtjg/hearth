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
from .jobs import LoadJob, SearchJob
from .models import Track
from .panel import FloatingPanel
from .player import PlaybackCore
from .storage import HearthStore
from .toast import NowPlayingToast
from .tray import HearthTray, InstanceGuard

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

        self._dir = data_directory or data_dir()
        setup_logging(self._dir)
        self.settings = (
            QSettings(settings_path, QSettings.Format.IniFormat)
            if settings_path else QSettings(config.ORG_NAME, config.APP_NAME)
        )
        self.store = HearthStore(self._dir / "hearth.db")
        self.catalog = Catalog()
        # In-flight QRunnables: the pool owns the C++ side, but Python must
        # keep the wrapper (and its signal carrier) alive until the job lands.
        self._jobs: list = []

        self.guard = InstanceGuard() if single_instance else None
        if self.guard is not None and not self.guard.is_primary:
            log.info("Hearth already running — forwarded 'show' and exiting")
            self.store.close()
            return

        # Core + UI
        self.core = PlaybackCore(self.qapp)
        self.panel = FloatingPanel(self.settings.value("theme", config.DEFAULT_PALETTE))
        self.toast = NowPlayingToast(self.settings.value("theme", config.DEFAULT_PALETTE))
        self.tray: HearthTray | None = None

        self._restore_settings()
        self._wire_panel()
        self._wire_core()
        self._install_hotkeys()
        self._build_tray()
        self._restore_session()

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

    def _wire_core(self) -> None:
        self.core.track_changed.connect(self._on_track_changed)
        self.core.state_changed.connect(self.panel.set_playing)
        self.core.position_changed.connect(self.panel.set_position)
        self.core.duration_changed.connect(self.panel.set_duration)
        self.core.status.connect(self.panel.set_status)
        self.core.repeat_changed.connect(lambda m: self._persist())
        self.core.rate_changed.connect(lambda r: self._persist())

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
        for action, chord in effective_chords(saved).items():
            shortcut = QShortcut(QKeySequence(chord), self.panel)
            shortcut.activated.connect({
                "play_pause": self.core.toggle,
                "next_track": self.core.next,
                "prev_track": self.core.previous,
                "toggle_panel": self.panel.toggleExpand,
                "focus_search": self._focus_search,
            }[action])

    # --- actions ---

    def _run_search(self, query: str) -> None:
        self.panel.set_status("Searching…")
        job = SearchJob(self.catalog, query)
        job.signals.finished.connect(self.panel.show_results)
        job.signals.failed.connect(lambda msg: self.panel.set_status(f"Search failed: {msg}"))
        self._jobs.append(job)
        QThreadPool.globalInstance().start(job)

    def _pick_track(self, track: Track) -> None:
        self.core.play_track(track)

    def _on_track_changed(self, track: Track | None) -> None:
        self.panel.set_track(track)
        self.store.log_play(track)
        self._persist()
        if track is None:
            return
        self.toast.announce(track)
        if not self._enable_streaming:
            return  # test mode: keep the playback pool out of unit tests
        job = LoadJob(track)
        job.signals.finished.connect(
            lambda payload: self.core.set_stream(payload[2], payload[0], payload[1])
        )
        job.signals.failed.connect(
            lambda title: self.panel.set_status(f"Could not resolve: {title}")
        )
        self._jobs.append(job)
        QThreadPool.globalInstance().start(job)

    def _cycle_repeat(self) -> None:
        mode = self.core.cycle_repeat()
        self.panel.set_status(f"Repeat: {mode}")

    def _summon(self) -> None:
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _focus_search(self) -> None:
        self._summon()
        if not self.panel.expanded:
            self.panel.setExpanded()
        self.panel._search.setFocus()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.panel.setVisible(not self.panel.isVisible())

    # --- persistence ---

    def _restore_settings(self) -> None:
        self.core.set_volume(float(self.settings.value("volume", 0.8)))
        self.panel.set_volume(self.core.volume)
        rate = float(self.settings.value("rate", 1.0))
        self.core.set_rate(rate)
        repeat = str(self.settings.value("repeat", config.REPEAT_OFF))
        if repeat in config.REPEAT_MODES:
            self.core.set_repeat(repeat)

    def _restore_session(self) -> None:
        pos = self.settings.value("geometry/pos")
        if pos is not None:
            self.panel.move(pos)
        favorites = self.store.favorites()
        if favorites:
            self.panel.set_status(f"{len(favorites)} favorites pinned")

    def _persist(self) -> None:
        self.settings.setValue("volume", self.core.volume)
        self.settings.setValue("rate", self.core.rate)
        self.settings.setValue("repeat", self.core.engine.repeat)
        self.settings.setValue("theme", self.panel._palette.key)
        self.settings.setValue("geometry/pos", self.panel.pos())

    def shutdown(self) -> None:
        # Let in-flight jobs land while their recipients are still alive.
        QThreadPool.globalInstance().waitForDone(5000)
        self._jobs.clear()
        self._persist()
        self.store.close()

    # --- run ---

    def run(self) -> int:
        if self.guard is not None and not self.guard.is_primary:
            return 0
        self.panel.show()
        code = self.qapp.exec()
        self.shutdown()
        return code


def main() -> int:
    hearth = Hearth(single_instance="--no-single-instance" not in sys.argv)
    return hearth.run()
