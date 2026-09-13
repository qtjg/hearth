"""
app.py
Entry point. Builds the pieces, restores the last session, wires the tray,
and hands control to Qt.

The panel owns layout. The core owns playback. This module owns the glue and
nothing else.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSettings, QStandardPaths
from PyQt6.QtWidgets import QApplication

from .catalog import CatalogSource
from .config import (
    APP_NAME,
    APP_TAGLINE,
    DEFAULT_VOLUME,
    ORG_NAME,
    SETTINGS_ENDLESS,
    SETTINGS_EXPANDED,
    SETTINGS_POS_X,
    SETTINGS_POS_Y,
    SETTINGS_RATE,
    SETTINGS_REPEAT,
    SETTINGS_THEME,
    SETTINGS_VOLUME,
    Palette,
)
from .panel import FloatingPanel
from .player import PlaybackCore, clamp_rate
from .storage import DB_FILENAME, HearthStorage
from .stream import StreamResolver
from .tray import InstanceGuard, TrayPresence, hearth_icon

log = logging.getLogger(__name__)

PLACEHOLDER_X = 24
PLACEHOLDER_Y = 24
LOG_FILENAME = "hearth.log"
MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3


# ------------------------------------------------------------------- coercion
def _as_int(raw: Any, fallback: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _as_bool(raw: Any, fallback: bool) -> bool:
    if raw is None:
        return fallback
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return fallback


# -------------------------------------------------------------------- logging
def _configure_logging(log_dir: Path) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(".")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(
            RotatingFileHandler(
                log_dir / LOG_FILENAME,
                maxBytes=MAX_LOG_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        )
    except OSError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


# --------------------------------------------------------------------- persistence
def _restore_session(panel: FloatingPanel, core: PlaybackCore, settings: QSettings) -> None:
    """Restore window geometry and persisted audio state from the last run."""
    screen = QApplication.primaryScreen()
    if screen is not None:
        bounds = screen.availableGeometry()
        fallback_x = max(PLACEHOLDER_X, bounds.right() - panel.width() - 24)
        fallback_y = max(PLACEHOLDER_Y, bounds.bottom() - panel.height() - 24)
    else:
        fallback_x, fallback_y = PLACEHOLDER_X, PLACEHOLDER_Y

    panel.place(
        _as_int(settings.value(SETTINGS_POS_X), fallback_x),
        _as_int(settings.value(SETTINGS_POS_Y), fallback_y),
    )
    panel.restore_ui_state()

    # Repeat mode + playback rate persist too (silent restore, no notices)
    core.restore_session(
        str(settings.value(SETTINGS_REPEAT, "off")),
        clamp_rate(settings.value(SETTINGS_RATE, 1.0)),
    )

    if _as_bool(settings.value(SETTINGS_EXPANDED), False):
        panel._apply_size(True)


def _persist(panel: FloatingPanel, core: PlaybackCore, settings: QSettings) -> None:
    """Persist session values on exit."""
    x, y = panel.current_position()
    settings.setValue(SETTINGS_POS_X, x)
    settings.setValue(SETTINGS_POS_Y, y)
    settings.setValue(SETTINGS_EXPANDED, panel.is_expanded())
    settings.setValue(SETTINGS_VOLUME, _as_int(panel.volume.value(), DEFAULT_VOLUME))
    settings.setValue(SETTINGS_ENDLESS, core.auto_queue)
    settings.setValue(SETTINGS_REPEAT, core.repeat_mode)
    settings.setValue(SETTINGS_RATE, core.playback_rate)
    settings.setValue(SETTINGS_THEME, Palette.current_theme)
    settings.sync()


def _wire_tray(
    tray: TrayPresence,
    panel: FloatingPanel,
    core: PlaybackCore,
    app: QApplication,
) -> None:
    tray.toggle_requested.connect(core.toggle)
    tray.forward_requested.connect(core.forward)
    tray.back_requested.connect(core.back)
    tray.reveal_requested.connect(panel.showNormal)
    tray.quit_requested.connect(app.quit)
    core.playing_changed.connect(tray.set_playing)
    panel.closed.connect(app.quit)


# ----------------------------------------------------------------------- main
def main() -> int:
    """Main application lifecycle runner."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(hearth_icon())
    app.setQuitOnLastWindowClosed(False)

    data_dir = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        or "."
    )
    _configure_logging(data_dir)
    log.info("%s %s starting — %s", APP_NAME, "0.1.0", APP_TAGLINE)

    guard = InstanceGuard()
    if not guard.claim():
        log.info("another instance is already running — waking the existing window")
        return 0

    settings = QSettings(ORG_NAME, APP_NAME)
    storage = HearthStorage(data_dir / DB_FILENAME)

    catalog = CatalogSource()
    resolver = StreamResolver()
    core = PlaybackCore(catalog, resolver)
    panel = FloatingPanel(core, storage, settings)
    tray = TrayPresence()

    _restore_session(panel, core, settings)
    _wire_tray(tray, panel, core, app)
    guard.reveal_requested.connect(panel.showNormal)

    app.aboutToQuit.connect(lambda: _persist(panel, core, settings))
    app.aboutToQuit.connect(guard.release)
    app.aboutToQuit.connect(tray.cleanup)
    app.aboutToQuit.connect(storage.close)

    panel.show()
    tray.show()

    return app.exec()
