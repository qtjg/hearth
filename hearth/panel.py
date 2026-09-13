"""
panel.py
The floating Hearth surface: a compact ribbon that blooms into a full panel.

Frameless, translucent, always-on-top, draggable anywhere. All styling comes
from theme.panel_stylesheet() against the live palette.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import QPoint, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .catalog import CatalogSource
from .config import (
    ART_RIBBON,
    EXPANDED_HEIGHT,
    PANEL_WIDTH,
    Palette,
    RIBBON_HEIGHT,
    SEARCH_DEBOUNCE_MS,
    SETTINGS_ENDLESS,
    SETTINGS_THEME,
    SETTINGS_VOLUME,
    SHELL_MARGIN,
)
from .jobs import ArtJob, SearchJob
from .models import Track
from .player import PlaybackCore
from .storage import HearthStorage
from .theme import panel_stylesheet
from .utils import clock, looks_like_link, pretty_count

log = logging.getLogger(__name__)

TAB_QUEUE = "queue"
TAB_FAVORITES = "favorites"
TAB_HISTORY = "history"

TRACK_ROLE = Qt.ItemDataRole.UserRole


class FloatingPanel(QWidget):
    """Ribbon + expanded player, owned by nothing but the desktop."""

    closed = pyqtSignal()

    def __init__(
        self,
        core: PlaybackCore,
        storage: Optional[HearthStorage],
        settings: QSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.storage = storage
        self.settings = settings

        self._drag_offset: Optional[QPoint] = None
        self._active_tab = TAB_QUEUE
        self._active_search: Optional[str] = None
        self._scrubbing = False
        self._art_cache: dict[str, QPixmap] = {}
        self._art_pending: set[str] = set()
        self._art_for: Optional[str] = None

        self.setWindowTitle("Hearth")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(panel_stylesheet())

        self._build()
        self._wire()
        self._apply_size(False)

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHELL_MARGIN, SHELL_MARGIN, SHELL_MARGIN, SHELL_MARGIN)

        self.shell = QFrame(self)
        self.shell.setObjectName("HearthShell")
        outer.addWidget(self.shell)

        layout = QVBoxLayout(self.shell)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        # --- ribbon row (always visible)
        ribbon = QHBoxLayout()
        ribbon.setSpacing(8)

        self.art = QLabel(self.shell)
        self.art.setFixedSize(ART_RIBBON, ART_RIBBON)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet(
            f"background: {Palette.surface}; border: 1px solid {Palette.line}; border-radius: 8px;"
        )
        ribbon.addWidget(self.art)

        words = QVBoxLayout()
        words.setSpacing(0)
        self.title = QLabel("hearth is warm", self.shell)
        self.title.setObjectName("RibbonTitle")
        self.artist = QLabel("search for something to play", self.shell)
        self.artist.setObjectName("RibbonArtist")
        words.addWidget(self.title)
        words.addWidget(self.artist)
        ribbon.addLayout(words, 1)

        self.btn_prev = QPushButton("⏮", self.shell)
        self.btn_prev.setFixedWidth(34)
        self.btn_play = QPushButton("▶", self.shell)
        self.btn_play.setFixedWidth(34)
        self.btn_next = QPushButton("⏭", self.shell)
        self.btn_next.setFixedWidth(34)
        self.btn_expand = QPushButton("▴", self.shell)
        self.btn_expand.setFixedWidth(28)
        for b in (self.btn_prev, self.btn_play, self.btn_next, self.btn_expand):
            ribbon.addWidget(b)
        layout.addLayout(ribbon)

        # --- status chip
        self.status = QLabel("ready", self.shell)
        self.status.setObjectName("StatusChip")
        layout.addWidget(self.status)
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(lambda: self._set_status("ready"))

        # --- expanded body
        self.body = QWidget(self.shell)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        search_row = QHBoxLayout()
        self.field = QLineEdit(self.body)
        self.field.setObjectName("SearchField")
        self.field.setPlaceholderText("song name, or paste a link…")
        self.btn_find = QPushButton("🔍", self.body)
        self.btn_find.setFixedWidth(40)
        search_row.addWidget(self.field, 1)
        search_row.addWidget(self.btn_find)
        body_layout.addLayout(search_row)

        tabs_row = QHBoxLayout()
        self.tab_queue = QPushButton("Queue", self.body)
        self.tab_queue.setCheckable(True)
        self.tab_favorites = QPushButton("Favorites", self.body)
        self.tab_favorites.setCheckable(True)
        self.tab_history = QPushButton("History", self.body)
        self.tab_history.setCheckable(True)
        for i, b in enumerate((self.tab_queue, self.tab_favorites, self.tab_history)):
            tabs_row.addWidget(b)
            b.clicked.connect(lambda _=False, idx=i: self._switch_tab(
                (TAB_QUEUE, TAB_FAVORITES, TAB_HISTORY)[idx]))
        tabs_row.addStretch(1)
        body_layout.addLayout(tabs_row)

        self.list = QListWidget(self.body)
        self.list.setObjectName("TrackList")
        body_layout.addWidget(self.list, 1)

        # transport row
        transport = QHBoxLayout()
        self.time_elapsed = QLabel("0:00", self.body)
        self.time_elapsed.setObjectName("TimeLabel")
        self.seek = QSlider(Qt.Orientation.Horizontal, self.body)
        self.seek.setRange(0, 0)
        self.time_total = QLabel("0:00", self.body)
        self.time_total.setObjectName("TimeLabel")
        transport.addWidget(self.time_elapsed)
        transport.addWidget(self.seek, 1)
        transport.addWidget(self.time_total)
        body_layout.addLayout(transport)

        # volume + modes row
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.btn_fav = QPushButton("♡", self.body)
        self.btn_fav.setFixedWidth(34)
        self.btn_repeat = QPushButton("↻ off", self.body)
        self.btn_rate = QPushButton("1.0x", self.body)
        self.btn_theme = QPushButton("🎨", self.body)
        self.btn_theme.setFixedWidth(34)
        self.vol_icon = QLabel("🔉", self.body)
        self.volume = QSlider(Qt.Orientation.Horizontal, self.body)
        self.volume.setRange(0, 100)
        self.btn_collapse = QPushButton("▾", self.body)
        self.btn_collapse.setFixedWidth(28)
        controls.addWidget(self.btn_fav)
        controls.addWidget(self.btn_repeat)
        controls.addWidget(self.btn_rate)
        controls.addWidget(self.btn_theme)
        controls.addStretch(1)
        controls.addWidget(self.vol_icon)
        controls.addWidget(self.volume, 1)
        controls.addWidget(self.btn_collapse)
        body_layout.addLayout(controls)

        layout.addWidget(self.body)
        self.body.setVisible(False)

    # ------------------------------------------------------------------- wire
    def _wire(self) -> None:
        core = self.core
        core.track_changed.connect(self._on_track)
        core.queue_changed.connect(self._on_queue_changed)
        core.cursor_changed.connect(self._on_cursor)
        core.playing_changed.connect(self._on_playing)
        core.progress_changed.connect(self._on_progress)
        core.length_changed.connect(self._on_length)
        core.loading_changed.connect(lambda loading: self._set_status("loading" if loading else "ready"))
        core.notice.connect(self._set_status)
        core.repeat_mode_changed.connect(self._on_repeat)
        core.rate_changed.connect(lambda rate: self.btn_rate.setText(f"{rate:g}x"))

        self.btn_play.clicked.connect(core.toggle)
        self.btn_prev.clicked.connect(core.back)
        self.btn_next.clicked.connect(core.forward)
        self.btn_expand.clicked.connect(lambda: self._apply_size(True))
        self.btn_collapse.clicked.connect(lambda: self._apply_size(False))

        self.btn_find.clicked.connect(self._on_find)
        self.field.returnPressed.connect(self._on_find)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._on_debounced_search)
        self.field.textChanged.connect(self._on_field_changed)

        self.list.itemClicked.connect(self._on_row_clicked)

        self.seek.sliderMoved.connect(self._on_scrub)
        self.seek.sliderReleased.connect(self._on_scrub_done)
        self.volume.valueChanged.connect(lambda v: core.set_volume(v))
        self.btn_repeat.clicked.connect(core.cycle_repeat_mode)
        self.btn_rate.clicked.connect(core.cycle_playback_rate)
        self.btn_fav.clicked.connect(self._toggle_favorite)
        self.btn_theme.clicked.connect(self._open_theme_menu)

    # ------------------------------------------------------------------ layout
    def _apply_size(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.btn_expand.setText("▾" if expanded else "▴")
        self.setFixedSize(PANEL_WIDTH, EXPANDED_HEIGHT if expanded else RIBBON_HEIGHT)
        self.settings.setValue("window/expanded", expanded)

    def is_expanded(self) -> bool:
        # isHidden() is explicit-visibility and independent of the top-level
        # window's shown state, so it works headless too.
        return not self.body.isHidden()

    # ------------------------------------------------------------------ search
    def _on_field_changed(self, text: str) -> None:
        raw = text.strip()
        if len(raw) >= 3 and not looks_like_link(raw):
            self._debounce.start()
        else:
            self._debounce.stop()

    def _on_debounced_search(self) -> None:
        text = self.field.text().strip()
        if len(text) >= 3 and not looks_like_link(text):
            self._execute_search(text)

    def _on_find(self) -> None:
        self._debounce.stop()
        text = self.field.text().strip()
        if not text:
            return
        if looks_like_link(text):
            self.core.open_link(text)
            self.field.clear()
            return
        self._execute_search(text)

    def _execute_search(self, query: str) -> None:
        self._set_status("searching")
        self._active_search = query
        job = SearchJob(self.core.catalog, query, 12)
        job.signals.done.connect(self._on_search_done)
        job.signals.failed.connect(self._on_search_failed)
        self.core.pool.start(job)

    def _on_search_done(self, query: str, tracks: List[Track]) -> None:
        if self._active_search != query:
            return  # stale results from an older query
        if not tracks:
            self._set_status("nothing found")
            return
        if self.field.text().strip() == query:
            self.field.clear()
        self._switch_tab(TAB_QUEUE)
        self.core.adopt(tracks, 0)
        self._set_status(pretty_count(len(tracks), "result"))

    def _on_search_failed(self, query: str, message: str) -> None:
        if self._active_search != query:
            return
        self._set_status("search failed")
        log.warning("search %r failed: %s", query, message)

    # --------------------------------------------------------------------- tabs
    def _switch_tab(self, tab: str) -> None:
        self._active_tab = tab
        self.tab_queue.setChecked(tab == TAB_QUEUE)
        self.tab_favorites.setChecked(tab == TAB_FAVORITES)
        self.tab_history.setChecked(tab == TAB_HISTORY)
        if tab == TAB_FAVORITES and self.storage:
            self._render(self.storage.get_favorites(), empty="nothing favorited yet — tap ♡")
        elif tab == TAB_HISTORY and self.storage:
            self._render(self.storage.get_history(50), empty="nothing played yet")
        else:
            self._render(self.core.queue, active=self.core.cursor, empty="queue is empty — search something warm")

    def _on_queue_changed(self, tracks: List[Track]) -> None:
        if self._active_tab == TAB_QUEUE:
            self._render(tracks, active=self.core.cursor, empty="queue is empty — search something warm")

    def _render(self, tracks: List[Track], active: int = -1, empty: str = "") -> None:
        self.list.clear()
        if not tracks:
            item = QListWidgetItem(empty or "nothing here")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
            return
        for index, track in enumerate(tracks):
            label = f"{index + 1}.  {track.title}  —  {track.byline}"
            if track.duration:
                label += f"   [{track.duration}]"
            item = QListWidgetItem(label)
            item.setData(TRACK_ROLE, index)
            if index == active:
                item.setText(f"▶  {track.title}  —  {track.byline}")
                item.setSelected(True)
            self.list.addItem(item)

    def _on_row_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(TRACK_ROLE)
        if isinstance(index, int):
            self.core.play_at(index)

    def _on_cursor(self, index: int) -> None:
        if self._active_tab == TAB_QUEUE and 0 <= index < self.list.count():
            self.list.item(index).setSelected(True)

    # ----------------------------------------------------------------- now playing
    def _on_track(self, track: Optional[Track]) -> None:
        if not track:
            return
        self.title.setText(track.title if len(track.title) <= 34 else track.title[:33] + "…")
        self.artist.setText(track.byline if len(track.byline) <= 44 else track.byline[:43] + "…")

        if self.storage:
            self.storage.record_history(track)
            self._refresh_fav_button(track.video_id)

        self.seek.setRange(0, 0)
        self.seek.setValue(0)
        self.time_elapsed.setText("0:00")
        self.time_total.setText("0:00")

        self._art_for = track.video_id
        cached = self._art_cache.get(track.video_id)
        if cached is not None:
            self._show_art(cached)
        elif track.artwork_url:
            self._request_art(track)

        if self._active_tab == TAB_FAVORITES and self.storage:
            self._switch_tab(TAB_FAVORITES)

    def _refresh_fav_button(self, video_id: str) -> None:
        fav = self.storage.is_favorite(video_id) if self.storage else False
        self.btn_fav.setText("♥" if fav else "♡")

    def _toggle_favorite(self) -> None:
        if not self.storage:
            self._set_status("storage unavailable")
            return
        track = self.core.current
        if not track:
            return
        if self.storage.is_favorite(track.video_id):
            self.storage.remove_favorite(track.video_id)
            self._set_status("removed from favorites")
        else:
            self.storage.add_favorite(track)
            self._set_status("favorited ♥")
        self._refresh_fav_button(track.video_id)

    # ---------------------------------------------------------------------- art
    def _request_art(self, track: Track) -> None:
        if track.video_id in self._art_pending:
            return
        self._art_pending.add(track.video_id)
        job = ArtJob(track.video_id, track.artwork_url)
        job.signals.arrived.connect(self._on_art)
        job.signals.failed.connect(lambda tid, _m: self._art_pending.discard(tid))
        self.core.pool.start(job)

    def _on_art(self, track_id: str, payload: bytes) -> None:
        self._art_pending.discard(track_id)
        source = QPixmap()
        if not source.loadFromData(payload):
            return
        if len(self._art_cache) >= 64:
            self._art_cache.pop(next(iter(self._art_cache)))
        self._art_cache[track_id] = source
        if self._art_for == track_id:
            self._show_art(source)

    def _show_art(self, source: QPixmap) -> None:
        side = ART_RIBBON - 2
        scaled = source.scaled(
            side, side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - side) // 2)
        y = max(0, (scaled.height() - side) // 2)
        self.art.setPixmap(scaled.copy(x, y, side, side))

    # ---------------------------------------------------------------- transport
    def _on_playing(self, playing: bool) -> None:
        self.btn_play.setText("⏸" if playing else "▶")

    def _on_progress(self, position: int) -> None:
        if self._scrubbing:
            return
        self.seek.setValue(position)
        self.time_elapsed.setText(clock(position))

    def _on_length(self, duration: int) -> None:
        self.seek.setRange(0, max(0, duration))
        self.time_total.setText(clock(duration))

    def _on_scrub(self, position: int) -> None:
        self._scrubbing = True
        self.time_elapsed.setText(clock(position))

    def _on_scrub_done(self) -> None:
        self._scrubbing = False
        self.core.seek(self.seek.value())

    def _on_repeat(self, mode: str) -> None:
        self.btn_repeat.setText(f"↻ {mode}")
        self.btn_repeat.setChecked(mode != "off")

    # -------------------------------------------------------------------- theme
    def _open_theme_menu(self) -> None:
        menu = QMenu(self)
        for name in Palette.list_themes():
            action = menu.addAction(("● " if name == Palette.current_theme else "○ ") + name)
            action.triggered.connect(lambda _=False, n=name: self._apply_theme(n))
        menu.exec(self.btn_theme.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4)))

    def _apply_theme(self, name: str) -> None:
        Palette.apply_theme(name)
        self.settings.setValue(SETTINGS_THEME, name)
        self.setStyleSheet(panel_stylesheet())
        self._set_status(f"theme: {name}")

    # ------------------------------------------------------------------ misc ui
    def _set_status(self, message: str) -> None:
        self.status.setText(message)
        if message != "ready":
            self._notice_timer.start(4000)

    def restore_ui_state(self) -> None:
        """Apply persisted volume/theme. Called by app after construction."""
        volume = self.settings.value(SETTINGS_VOLUME, 78)
        try:
            self.volume.setValue(max(0, min(100, int(volume))))
        except (TypeError, ValueError):
            self.volume.setValue(78)
        theme = str(self.settings.value(SETTINGS_THEME, "Ember"))
        if theme in Palette.THEMES:
            Palette.apply_theme(theme)
            self.setStyleSheet(panel_stylesheet())
        endless = str(self.settings.value(SETTINGS_ENDLESS, "true")).lower() in ("true", "1", "yes")
        self.core.set_auto_queue(endless)

    # --------------------------------------------------------------------- drag
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None

    def place(self, x: int, y: int) -> None:
        self.move(x, y)

    def current_position(self) -> tuple[int, int]:
        return self.x(), self.y()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)
