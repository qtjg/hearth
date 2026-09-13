"""Non-focus-stealing desktop toast for "now playing" moments."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from . import config
from .models import Track
from .theme import build_stylesheet
from .config import get_palette


class NowPlayingToast(QWidget):
    """A ghost of a notification: appears, whispers the track, fades away."""

    def __init__(self, palette_key: str | None = None):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(config.TOAST_WIDTH, config.TOAST_HEIGHT)
        self.setStyleSheet(build_stylesheet(get_palette(palette_key)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._title = QLabel("🔥 Hearth")
        self._title.setProperty("header", True)
        self._sub = QLabel("")
        self._sub.setProperty("dim", True)
        self._sub.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._sub)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._fade = QTimer(self)
        self._fade.timeout.connect(self._fade_tick)
        self._opacity = 1.0

    def announce(self, track: Track) -> None:
        self._sub.setText(f"▶ {track.display_name}")
        self.reposition()
        self.setWindowOpacity(1.0)
        self._opacity = 1.0
        self.show()
        self._timer.start(config.TOAST_LIFETIME_MS)

    def reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.right() - self.width() - 18,
            geo.bottom() - self.height() - 18,
        )

    def _fade_out(self) -> None:
        self._fade.start(60)

    def _fade_tick(self) -> None:
        self._opacity -= 0.08
        if self._opacity <= 0.0:
            self._fade.stop()
            self.hide()
            return
        self.setWindowOpacity(max(0.0, self._opacity))
