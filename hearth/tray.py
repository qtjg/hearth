"""
tray.py
System tray presence and the single-instance guard.

The Hearth mark is painted at runtime from the live Palette — no binary
assets ship with the project, and the mark renders crisply at every size.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QLockFile, QObject, QStandardPaths, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from .config import APP_NAME

log = logging.getLogger(__name__)

SOCKET_NAME = "hearth.desktop.instance"
LOCK_FILE = "hearth-instance.lock"
HANDSHAKE_TIMEOUT_MS = 500
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


# ------------------------------------------------------------------- the mark
def hearth_mark(side: int = 256) -> QPixmap:
    """A rounded hearthstone tile with a painted flame, in the live palette."""
    canvas = QPixmap(side, side)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    tile = QPainterPath()
    tile.addRoundedRect(0.0, 0.0, float(side), float(side), side * 0.26, side * 0.26)
    backdrop = QLinearGradient(0.0, 0.0, float(side), float(side))
    backdrop.setColorAt(0.0, QColor(Palette.shell_a))
    backdrop.setColorAt(1.0, QColor(Palette.void))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(backdrop)
    painter.drawPath(tile)

    # Flame: two bezier lobes meeting at a soft tip
    flame = QPainterPath()
    flame.moveTo(side * 0.50, side * 0.16)
    flame.cubicTo(side * 0.82, side * 0.40, side * 0.78, side * 0.70, side * 0.50, side * 0.84)
    flame.cubicTo(side * 0.22, side * 0.70, side * 0.18, side * 0.40, side * 0.50, side * 0.16)
    flame.closeSubpath()
    glow = QLinearGradient(0.0, float(side) * 0.84, 0.0, float(side) * 0.16)
    glow.setColorAt(0.0, QColor(Palette.accent_lo))
    glow.setColorAt(0.55, QColor(Palette.accent))
    glow.setColorAt(1.0, QColor(Palette.accent_hi))
    painter.setBrush(glow)
    painter.drawPath(flame)

    # Inner heart of the flame
    heart = QPainterPath()
    cx, cy = side * 0.50, side * 0.60
    heart.moveTo(cx, side * 0.38)
    heart.cubicTo(side * 0.66, cy, side * 0.63, side * 0.72, cx, side * 0.78)
    heart.cubicTo(side * 0.37, side * 0.72, side * 0.34, cy, cx, side * 0.38)
    heart.closeSubpath()
    painter.setBrush(QColor(Palette.text))
    painter.drawPath(heart)

    painter.end()
    return canvas


def hearth_icon() -> QIcon:
    """Multi-resolution icon built from the painted mark."""
    icon = QIcon()
    for side in ICON_SIZES:
        icon.addPixmap(hearth_mark(side))
    return icon


# ------------------------------------------------------------ single instance
class InstanceGuard(QObject):
    """Keeps one Hearth alive; a second launch nudges the first instead."""

    reveal_requested = pyqtSignal()

    def __init__(self, socket_name: str = SOCKET_NAME, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.socket_name = socket_name
        self._lock: Optional[QLockFile] = None
        self._server: Optional[QLocalServer] = None

    def claim(self) -> bool:
        """True when this process owns the instance lock."""
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
        if not folder:
            folder = "."
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = "."

        self._lock = QLockFile(str(Path(folder) / LOCK_FILE))
        self._lock.setStaleLockTime(10000)
        if not self._lock.tryLock(200):
            if self._nudge_existing():
                log.info("instance lock held elsewhere — nudging the running copy")
                return False
            log.warning("abandoned lock file from a previous crash — reclaiming")
            self._lock.removeStaleLockFile()
            if not self._lock.tryLock(200):
                log.error("unable to claim instance lock after clearing stale lock")
                return False

        QLocalServer.removeServer(self.socket_name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self.socket_name):
            log.warning("instance socket unavailable: %s", self._server.errorString())
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None

    def _nudge_existing(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self.socket_name)
        if probe.waitForConnected(HANDSHAKE_TIMEOUT_MS):
            probe.write(b"reveal")
            probe.flush()
            probe.waitForBytesWritten(HANDSHAKE_TIMEOUT_MS)
            probe.waitForDisconnected(HANDSHAKE_TIMEOUT_MS)
            probe.disconnectFromServer()
            return True
        probe.abort()
        return False

    def _on_connection(self) -> None:
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        if connection.bytesAvailable() > 0:
            self._consume(connection)
        else:
            connection.readyRead.connect(lambda: self._consume(connection))
        connection.disconnected.connect(connection.deleteLater)

    def _consume(self, connection: QLocalSocket) -> None:
        payload = bytes(connection.readAll()).strip()
        if payload == b"reveal":
            self.reveal_requested.emit()
        connection.disconnectFromServer()


# ------------------------------------------------------------------- presence
class TrayPresence(QObject):
    """Tray icon and menu. Emits intent only — the app decides what happens."""

    toggle_requested = pyqtSignal()
    back_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    reveal_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(hearth_icon(), self)
        self.icon.setToolTip(f"{APP_NAME} — warm listening, everywhere")

        parent_widget = parent if isinstance(parent, QWidget) else None
        self.menu = QMenu(parent_widget)
        self._toggle = self.menu.addAction("play / pause")
        self._back = self.menu.addAction("previous track")
        self._forward = self.menu.addAction("next track")
        self.menu.addSeparator()
        self._reveal = self.menu.addAction("show hearth")
        self.menu.addSeparator()
        self._quit = self.menu.addAction("quit")

        self._toggle.triggered.connect(self.toggle_requested)
        self._back.triggered.connect(self.back_requested)
        self._forward.triggered.connect(self.forward_requested)
        self._reveal.triggered.connect(self.reveal_requested)
        self._quit.triggered.connect(self.quit_requested)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.reveal_requested.emit()

    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon.show()
        else:
            log.info("no system tray here — the panel stands on its own")

    def hide(self) -> None:
        self.icon.hide()

    def cleanup(self) -> None:
        """Hide the tray icon to avoid ghost icons and release the menu."""
        self.icon.hide()
        if self.menu is not None:
            self.menu.close()
            self.menu.deleteLater()

    def set_playing(self, playing: bool) -> None:
        self._toggle.setText("pause" if playing else "play")
