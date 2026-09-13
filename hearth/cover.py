"""Cover art tiles: painted flame fallback + lazy async album art."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QLabel

from .config import Palette

log = logging.getLogger(__name__)

_COVER_TIMEOUT_MS = 8000


def paint_mark(palette: Palette, side: int = 168, char: str = "🔥") -> QPixmap:
    """The Hearth mark at any size: flame glyph on a shell-gradient tile."""
    pixmap = QPixmap(side, side)
    backdrop = QLinearGradient(0.0, 0.0, 0.0, float(side))
    backdrop.setColorAt(0.0, QColor(palette.surface))
    backdrop.setColorAt(1.0, QColor(palette.surface_alt))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(pixmap.rect(), backdrop)
    tile = QPainterPath()
    radius = side * 0.12
    tile.addRoundedRect(0.0, 0.0, float(side), float(side), radius, radius)
    painter.setPen(QColor(palette.hairline))
    painter.drawPath(tile)
    painter.setPen(QColor(palette.accent))
    font = QFont()
    font.setPixelSize(max(12, int(side * 0.62)))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0084, char)  # AlignCenter
    painter.end()
    return pixmap


class CoverTile(QLabel):
    """A square cover: painted mark first, album art once it downloads."""

    def __init__(self, palette: Palette, side: int = 168, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._side = side
        self._nam: QNetworkAccessManager | None = None
        self._reply: QNetworkReply | None = None
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._abort)
        self.setFixedSize(side, side)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("tile", True)
        self.set_mark()

    # --- content ---

    def set_mark(self) -> None:
        self._set_pixmap(paint_mark(self._palette, self._side))

    def set_track_cover(self, url: str) -> None:
        if not url:
            self.set_mark()
            return
        if self._nam is None:
            self._nam = QNetworkAccessManager(self)
        if self._reply is not None:
            self._reply.abort()
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(_COVER_TIMEOUT_MS)
        self._reply = self._nam.get(request)
        self._reply.finished.connect(self._on_cover)
        self._timeout.start(_COVER_TIMEOUT_MS)

    # --- internals ---

    def _set_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self._side, self._side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def _abort(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    def _on_cover(self) -> None:
        self._timeout.stop()
        reply, self._reply = self._reply, None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return  # keep the painted mark; offline is a first-class state
            data = reply.readAll()
            art = QPixmap()
            if not art.loadFromData(bytes(data)):
                return
            self._set_pixmap(art)
        finally:
            reply.deleteLater()

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        if self.pixmap() is None:
            self.set_mark()
