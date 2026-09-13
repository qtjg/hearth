"""The big stage: sidebar, home shelves, search, library, player bar.

Layout conventions follow the familiar three-pane desktop music player:
navigation on the left, content cards up top, transport controls pinned
to the bottom. Everything here is original Hearth code painted from the
active Palette — no assets, no third-party marks.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import config, share
from .config import Palette, get_palette
from .cover import CoverTile
from .models import Track
from .storage import HearthStore
from .theme import build_stylesheet
from .utils import clock


# ----------------------------------------------------------------- rows

class TrackRow(QWidget):
    """One search/playlist/queue row: index, mini cover, title·artist, time."""

    def __init__(self, palette: Palette, track: Track, index: int = 0,
                 removable: bool = False):
        super().__init__()
        self.track = track
        self.setMinimumHeight(config.ROW_HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(10)

        self._pos = QLabel(f"{index}" if index else "▶")
        self._pos.setProperty("dim", True)
        self._pos.setFixedWidth(26)
        self._pos.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._cover = CoverTile(palette, 38)
        if track.thumbnail:
            self._cover.set_track_cover(track.thumbnail)

        text = QVBoxLayout()
        text.setSpacing(1)
        self._title = QLabel(track.title)
        self._title.setProperty("header", True)
        self._artist = QLabel(track.artist)
        self._artist.setProperty("dim", True)
        text.addWidget(self._title)
        text.addWidget(self._artist)

        self._time = QLabel(track.duration or clock(track.duration_sec * 1000))
        self._time.setProperty("dim", True)
        self._time.setFixedWidth(52)
        self._time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lay.addWidget(self._pos)
        lay.addWidget(self._cover)
        lay.addLayout(text, 1)
        lay.addWidget(self._time)

    def set_index(self, index: int) -> None:
        self._pos.setText(str(index))


class Shelf(QWidget):
    """A titled horizontal strip of track cards ('Made for you' vibes)."""

    card_picked = pyqtSignal(object, list)      # Track, shelf context

    def __init__(self, palette: Palette, title: str):
        super().__init__()
        self._palette = palette
        self._tracks: list[Track] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 10)
        lay.setSpacing(8)
        self._title = QLabel(title)
        self._title.setProperty("shelf", True)
        self._strip_area = QScrollArea()
        self._strip_area.setWidgetResizable(True)
        self._strip_area.setFixedHeight(config.COVER_TILE + 96)
        self._strip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._strip = QWidget()
        self._strip_lay = QHBoxLayout(self._strip)
        self._strip_lay.setContentsMargins(2, 2, 2, 2)
        self._strip_lay.setSpacing(10)
        self._strip_lay.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._strip_area.setWidget(self._strip)
        self._empty = QLabel("Nothing here yet — play something cozy.")
        self._empty.setProperty("dim", True)
        lay.addWidget(self._title)
        lay.addWidget(self._strip_area)
        lay.addWidget(self._empty)
        self.set_tracks([])

    def set_tracks(self, tracks: list[Track]) -> None:
        self._tracks = list(tracks)
        while self._strip_lay.count():
            item = self._strip_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, track in enumerate(self._tracks):
            card = self._make_card(track, index)
            self._strip_lay.addWidget(card)
        has = bool(self._tracks)
        self._strip_area.setVisible(has)
        self._empty.setVisible(not has)

    def _make_card(self, track: Track, index: int) -> QPushButton:
        card = QPushButton()
        card.setProperty("card", True)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFixedSize(config.COVER_TILE, config.COVER_TILE + 74)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(6)
        tile = CoverTile(self._palette, config.COVER_TILE - 24)
        tile.set_track_cover(track.thumbnail)
        title = QLabel(track.title)
        title.setWordWrap(True)
        title.setMaximumHeight(34)
        artist = QLabel(track.artist)
        artist.setProperty("dim", True)
        inner.addWidget(tile)
        inner.addWidget(title, 1)
        inner.addWidget(artist)
        card.clicked.connect(lambda _=False, t=track, i=index: self.card_picked.emit(t, list(self._tracks)))
        return card


# ----------------------------------------------------------------- views

class HomeView(QWidget):
    """Scrolling shelves: quick picks, pinned favorites, recently played."""

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setContentsMargins(24, 18, 24, 18)
        self._body_lay.setSpacing(14)
        area.setWidget(body)
        outer.addWidget(area)
        self._shelves: dict[str, Shelf] = {}
        for name in ("Quick picks", "Pinned favorites", "Recently played"):
            self._shelves[name] = Shelf(palette, name)
            self._body_lay.addWidget(self._shelves[name])
            self._shelves[name].setVisible(False)
        self._hero = QLabel("Good fire to sit by. What are we playing?")
        self._hero.setProperty("hero", True)
        self._body_lay.insertWidget(0, self._hero)

    def shelf(self, name: str) -> Shelf:
        return self._shelves[name]

    def set_shelf(self, name: str, tracks: list[Track]) -> None:
        self._shelves[name].set_tracks(list(tracks))
        self._shelves[name].setVisible(bool(tracks))

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette


class TrackListView(QWidget):
    """A searchable list of rows with double-click-to-play and a context menu."""

    track_activated = pyqtSignal(object, list)   # Track, full list context
    menu_requested = pyqtSignal(object, object)  # Track, QMenu (caller fills)

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._tracks: list[Track] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 12)
        lay.setSpacing(10)
        self._head = QLabel("")
        self._head.setProperty("hero", True)
        self._count = QLabel("")
        self._count.setProperty("dim", True)
        self._list = QListWidget()
        self._list.setProperty("rows", True)
        self._list.setSpacing(2)
        self._list.itemDoubleClicked.connect(self._on_double)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_menu)
        lay.addWidget(self._head)
        lay.addWidget(self._count)
        lay.addWidget(self._list, 1)

    def set_header(self, title: str) -> None:
        self._head.setText(title)

    def set_tracks(self, tracks: list[Track]) -> None:
        self._tracks = list(tracks)
        self._list.clear()
        for index, track in enumerate(self._tracks, start=1):
            item = QListWidgetItem()
            item.setSizeHint(TrackRow(self._palette, track).sizeHint())
            row = TrackRow(self._palette, track, index)
            item.setData(Qt.ItemDataRole.UserRole, track)
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        shown = len(self._tracks)
        self._count.setText(
            f"{shown} tracks" if shown != 1 else "1 track"
        )

    @property
    def current_tracks(self) -> list[Track]:
        return list(self._tracks)

    def _on_double(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if track is not None:
            self.track_activated.emit(track, list(self._tracks))

    def _on_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if track is None:
            return
        menu = QMenu(self)
        self.menu_requested.emit(track, menu)
        menu.exec(self._list.viewport().mapToGlobal(pos))


class SearchView(TrackListView):
    """The search page: a prominent query box above the result rows."""

    search_submitted = pyqtSignal(str)

    def __init__(self, palette: Palette):
        super().__init__(palette)
        self._head.setText("Search")
        self.set_tracks([])
        self._box = QLineEdit()
        self._box.setPlaceholderText("What do you want to play?  (or paste a link)")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._emit_search)
        self._box.textEdited.connect(lambda _: self._debounce.start())
        self._box.returnPressed.connect(self._emit_search)
        self.layout().insertWidget(0, self._box)
        self._count.hide()

    def _emit_search(self) -> None:
        query = self._box.text().strip()
        if query:
            self.search_submitted.emit(query)

    def set_query(self, text: str) -> None:
        self._box.setText(text)

    def query(self) -> str:
        return self._box.text().strip()


class LibraryView(QWidget):
    """Your stuff: pinned favorites, recent history, and playlist cards."""

    playlist_opened = pyqtSignal(int)            # playlist id
    track_activated = pyqtSignal(object, list)
    menu_requested = pyqtSignal(object, object)
    create_playlist_requested = pyqtSignal()

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(14)

        head = QHBoxLayout()
        hero = QLabel("Your Library")
        hero.setProperty("hero", True)
        new_btn = QPushButton("＋ New playlist")
        new_btn.setProperty("accent", True)
        new_btn.clicked.connect(self.create_playlist_requested.emit)
        head.addWidget(hero)
        head.addStretch(1)
        head.addWidget(new_btn)
        outer.addLayout(head)

        self._fav_shelf = Shelf(palette, "Pinned favorites")
        self._recent = TrackListView(palette)
        self._recent.set_header("Recently played")
        self._recent.setMinimumHeight(240)
        self._recent.track_activated.connect(self.track_activated)
        self._recent.menu_requested.connect(self.menu_requested)
        outer.addWidget(self._fav_shelf)
        outer.addWidget(QLabel("Recently played"))
        outer.addWidget(self._recent, 1)

    def set_favorites(self, tracks: list[Track]) -> None:
        self._fav_shelf.set_tracks(list(tracks))

    def set_recent(self, tracks: list[Track]) -> None:
        self._recent.set_tracks(list(tracks)[:8])


class PlaylistView(TrackListView):
    """One playlist: header actions + its rows."""

    play_all_requested = pyqtSignal(list, int)
    shuffle_requested_sig = pyqtSignal(list)
    rename_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, palette: Palette, playlist_id: int, name: str):
        super().__init__(palette)
        self.playlist_id = playlist_id
        self._playlist_name = name
        self.set_header(f"📁 {name}")

        actions = QHBoxLayout()
        play = QPushButton("▶ Play all")
        play.setProperty("accent", True)
        play.clicked.connect(lambda: self.play_all_requested.emit(list(self._tracks), 0))
        shuffle = QPushButton("🔀 Shuffle")
        shuffle.clicked.connect(lambda: self.shuffle_requested_sig.emit(list(self._tracks)))
        rename = QPushButton("Rename")
        rename.clicked.connect(lambda: self.rename_requested.emit(self.playlist_id))
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda: self.delete_requested.emit(self.playlist_id))
        for b in (play, shuffle, rename, delete):
            actions.addWidget(b)
        actions.addStretch(1)
        self.layout().insertLayout(2, actions)


# ----------------------------------------------------------------- now playing

class NowView(QWidget):
    """The Now Playing stage: big cover, identity, and the lyrics sheet."""

    pin_toggled = pyqtSignal()
    radio_requested = pyqtSignal()

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._track: Track | None = None
        self._video_id: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(12)

        head = QHBoxLayout()
        hero = QLabel("Now Playing")
        hero.setProperty("hero", True)
        head.addWidget(hero)
        head.addStretch(1)
        self._btn_radio = QPushButton("📻 Start radio")
        self._btn_radio.clicked.connect(self.radio_requested.emit)
        head.addWidget(self._btn_radio)
        outer.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(10)
        self._cover = CoverTile(palette, config.NOW_COVER)
        ident = QHBoxLayout()
        ident.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        self._title = QLabel("Nothing playing")
        self._title.setProperty("header", True)
        self._title.setWordWrap(True)
        self._artist = QLabel("pick something from the shelves")
        self._artist.setProperty("dim", True)
        self._artist.setWordWrap(True)
        text.addWidget(self._title)
        text.addWidget(self._artist)
        self._pin = QPushButton("♡")
        self._pin.setProperty("flat", True)
        self._pin.setFixedWidth(34)
        self._pin.setToolTip("Pin to favorites")
        self._pin.clicked.connect(self.pin_toggled.emit)
        ident.addLayout(text, 1)
        ident.addWidget(self._pin)
        left.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addLayout(ident)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(6)
        cap = QLabel("LYRICS")
        cap.setProperty("dim", True)
        self._lyrics = QPlainTextEdit()
        self._lyrics.setProperty("lyrics", True)
        self._lyrics.setReadOnly(True)
        self._lyrics.setPlaceholderText(
            "Lyrics show up here once something is playing."
        )
        right.addWidget(cap)
        right.addWidget(self._lyrics, 1)

        body.addLayout(left, 1)
        body.addLayout(right, 1)
        outer.addLayout(body, 1)

    # --- state in ---

    def set_track(self, track: Track | None) -> None:
        self._track = track
        if track is None:
            self._video_id = ""
            self._title.setText("Nothing playing")
            self._artist.setText("pick something from the shelves")
            self._pin.setText("♡")
            self._cover.set_mark()
            self._lyrics.setPlainText("")
            return
        self._video_id = track.video_id
        self._title.setText(track.title)
        self._artist.setText(track.artist)
        if track.thumbnail:
            self._cover.set_track_cover(track.thumbnail)
        else:
            self._cover.set_mark()

    def set_lyrics(self, video_id: str, text: str | None) -> None:
        """Late-arriving lyrics; drop them if the track moved on meanwhile."""
        if video_id != self._video_id:
            return
        self._lyrics.setPlainText(text or "No lyrics available for this track.")

    def set_lyrics_loading(self) -> None:
        self._lyrics.setPlainText("Loading lyrics…")

    def set_pinned(self, pinned: bool) -> None:
        self._pin.setText("♥" if pinned else "♡")

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._cover.apply_palette(palette)

    @property
    def current_track(self) -> Track | None:
        return self._track


# ----------------------------------------------------------------- player bar

class PlayerBar(QWidget):
    """Bottom transport: cover, pin, controls, seek, queue toggle, volume."""

    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    shuffle_requested = pyqtSignal()
    repeat_requested = pyqtSignal()
    volume_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(int)
    pin_toggled = pyqtSignal()
    queue_toggled = pyqtSignal()
    radio_requested = pyqtSignal()
    rate_cycled = pyqtSignal()
    sleep_requested = pyqtSignal(int)      # minutes; 0 = off
    lyrics_toggled = pyqtSignal()

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._track: Track | None = None
        self._pinned = False
        self.setFixedHeight(config.PLAYERBAR_HEIGHT)
        self.setAutoFillBackground(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        # left: cover + identity + pin
        self._cover = CoverTile(palette, 56)
        self._title = QLabel("Nothing playing")
        self._title.setProperty("header", True)
        self._artist = QLabel("pick something from the shelves")
        self._artist.setProperty("dim", True)
        ident = QVBoxLayout()
        ident.setSpacing(2)
        ident.addWidget(self._title)
        ident.addWidget(self._artist)
        self._pin = QPushButton("♡")
        self._pin.setProperty("flat", True)
        self._pin.setFixedWidth(34)
        self._pin.setToolTip("Pin to favorites")
        self._pin.clicked.connect(self.pin_toggled.emit)

        # center: transport + seek
        self._btn_shuffle = QPushButton("🔀")
        self._btn_prev = QPushButton("⏮")
        self._btn_play = QPushButton("▶")
        self._btn_play.setProperty("accent", True)
        self._btn_next = QPushButton("⏭")
        self._btn_repeat = QPushButton("🔁")
        self._btn_shuffle.setProperty("flat", True)
        self._btn_repeat.setProperty("flat", True)
        self._btn_prev.setProperty("flat", True)
        self._btn_next.setProperty("flat", True)
        for b in (self._btn_shuffle, self._btn_prev, self._btn_play,
                  self._btn_next, self._btn_repeat):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.setFixedSize(44, 36)
        self._btn_shuffle.clicked.connect(self.shuffle_requested.emit)
        self._btn_prev.clicked.connect(self.prev_requested.emit)
        self._btn_play.clicked.connect(self.play_pause_requested.emit)
        self._btn_next.clicked.connect(self.next_requested.emit)
        self._btn_repeat.clicked.connect(self.repeat_requested.emit)

        self._elapsed = QLabel("0:00")
        self._elapsed.setProperty("dim", True)
        self._total = QLabel("0:00")
        self._total.setProperty("dim", True)
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.sliderReleased.connect(
            lambda: self.seek_requested.emit(self._seek.value())
        )
        center = QVBoxLayout()
        center.setSpacing(4)
        ctrl = QHBoxLayout()
        ctrl.addStretch(1)
        for b in (self._btn_shuffle, self._btn_prev, self._btn_play,
                  self._btn_next, self._btn_repeat):
            ctrl.addWidget(b)
        ctrl.addStretch(1)
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        seek_row.addWidget(self._elapsed)
        seek_row.addWidget(self._seek, 1)
        seek_row.addWidget(self._total)
        center.addLayout(ctrl)
        center.addLayout(seek_row)

        # right: lyrics · radio · speed · sleep · queue · volume
        self._btn_lyrics = QPushButton("♪")
        self._btn_lyrics.setProperty("flat", True)
        self._btn_lyrics.setToolTip("Now playing & lyrics")
        self._btn_lyrics.clicked.connect(self.lyrics_toggled.emit)
        self._btn_radio = QPushButton("📻")
        self._btn_radio.setProperty("flat", True)
        self._btn_radio.setToolTip("Start radio from this track")
        self._btn_radio.clicked.connect(self.radio_requested.emit)
        self._btn_speed = QPushButton("1x")
        self._btn_speed.setProperty("flat", True)
        self._btn_speed.setFixedWidth(44)
        self._btn_speed.setToolTip("Playback speed")
        self._btn_speed.clicked.connect(self.rate_cycled.emit)
        self._btn_sleep = QPushButton("⏾")
        self._btn_sleep.setProperty("flat", True)
        self._btn_sleep.setToolTip("Sleep timer")
        self._sleep_menu = QMenu(self)
        for label, minutes in (("Off", 0), ("15 minutes", 15),
                               ("30 minutes", 30), ("45 minutes", 45),
                               ("60 minutes", 60)):
            act = self._sleep_menu.addAction(label)
            act.triggered.connect(
                lambda _checked=False, m=minutes: self.sleep_requested.emit(m)
            )
        self._btn_sleep.setMenu(self._sleep_menu)
        self._btn_queue = QPushButton("☰ Queue")
        self._btn_queue.setProperty("flat", True)
        self._btn_queue.clicked.connect(self.queue_toggled.emit)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(80)
        self._volume.setFixedWidth(110)
        self._volume.valueChanged.connect(lambda v: self.volume_changed.emit(v / 100.0))

        lay.addWidget(self._cover)
        lay.addLayout(ident, 1)
        lay.addWidget(self._pin)
        lay.addLayout(center, 3)
        lay.addWidget(self._btn_lyrics)
        lay.addWidget(self._btn_radio)
        lay.addWidget(self._btn_speed)
        lay.addWidget(self._btn_sleep)
        lay.addWidget(self._btn_queue)
        lay.addWidget(self._volume)

    # --- state in ---

    def set_track(self, track: Track | None) -> None:
        self._track = track
        if track is None:
            self._title.setText("Nothing playing")
            self._artist.setText("pick something from the shelves")
            self._pin.setText("♡")
            self._cover.set_mark()
            return
        self._title.setText(track.title)
        self._artist.setText(track.artist)
        self._pin.setText("♥" if self._pinned else "♡")
        if track.thumbnail:
            self._cover.set_track_cover(track.thumbnail)
        else:
            self._cover.set_mark()

    def set_pinned(self, pinned: bool) -> None:
        self._pinned = pinned
        self._pin.setText("♥" if pinned else "♡")

    def set_playing(self, playing: bool) -> None:
        self._btn_play.setText("⏸" if playing else "▶")

    def set_status(self, text: str) -> None:
        self._artist.setText(text) if self._track is None else None

    def set_position(self, position_ms: int) -> None:
        self._elapsed.setText(clock(position_ms))
        if not self._seek.isSliderDown():
            self._seek.setValue(position_ms)

    def set_duration(self, duration_ms: int) -> None:
        self._total.setText(clock(duration_ms))
        self._seek.setRange(0, max(0, duration_ms))

    def set_volume(self, value: float) -> None:
        self._volume.blockSignals(True)
        self._volume.setValue(int(value * 100))
        self._volume.blockSignals(False)

    def set_speed_label(self, rate: float) -> None:
        label = f"{rate:g}x"
        self._btn_speed.setText(label)
        self._btn_speed.setToolTip(f"Playback speed ({label})")

    def set_sleep_label(self, minutes: int | None) -> None:
        self._btn_sleep.setText(f"⏾ {minutes}" if minutes else "⏾")

    @property
    def current_track(self) -> Track | None:
        return self._track


# ----------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    """Hearth, grown up: navigation, shelves, lists, and a real transport."""

    search_submitted = pyqtSignal(str)
    track_picked = pyqtSignal(object)             # single card pick
    playlist_picked = pyqtSignal(list, int)       # play list from index
    play_next_requested = pyqtSignal(object)      # insert at queue head
    enqueue_requested = pyqtSignal(object)        # append to queue
    pin_toggled = pyqtSignal(object)              # Track
    queue_remove_requested = pyqtSignal(int)
    queue_reorder_requested = pyqtSignal(list)    # new upcoming order
    radio_requested = pyqtSignal(object)          # Track | None (None = current)
    rate_cycled = pyqtSignal()
    sleep_requested = pyqtSignal(int)             # minutes; 0 = off
    home_refresh_requested = pyqtSignal()
    library_refresh_requested = pyqtSignal()
    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    shuffle_requested = pyqtSignal()
    repeat_requested = pyqtSignal()
    volume_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(int)

    VIEWS = ("home", "search", "library", "now")

    def __init__(self, palette_key: str | None = None,
                 store: HearthStore | None = None):
        super().__init__()
        self._palette = get_palette(palette_key)
        self.store = store
        self.setWindowTitle(f"🔥 {config.APP_NAME} — {config.APP_TAGLINE}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        self.home_view = HomeView(self._palette)
        self.search_view = SearchView(self._palette)
        self.library_view = LibraryView(self._palette)
        self.now_view = NowView(self._palette)

        self.stack = QStackedWidget()
        for view in (self.home_view, self.search_view, self.library_view,
                     self.now_view):
            self.stack.addWidget(view)

        self.player_bar = PlayerBar(self._palette)
        self._build_queue_dock()

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        outer.addWidget(self.player_bar)
        self.setCentralWidget(central)

        self.setStyleSheet(build_stylesheet(self._palette))
        self._wire_internal()
        self.show_view("home")

    # --- construction bits ---

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(config.SIDEBAR_WIDTH)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(6)
        wordmark = QLabel("🔥 Hearth")
        wordmark.setProperty("hero", True)
        lay.addWidget(wordmark)
        lay.addSpacing(10)

        self._nav: dict[str, QPushButton] = {}
        for key, label in (("home", "🏠 Home"), ("search", "🔍 Search"),
                           ("library", "📚 Your Library"),
                           ("now", "🎧 Now Playing")):
            btn = QPushButton(label)
            btn.setProperty("nav", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.show_view(k))
            self._nav[key] = btn
            lay.addWidget(btn)

        head = QHBoxLayout()
        cap = QLabel("PLAYLISTS")
        cap.setProperty("dim", True)
        add = QPushButton("＋")
        add.setProperty("flat", True)
        add.setFixedWidth(30)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self._new_playlist_dialog)
        imp = QPushButton("⬆")
        imp.setProperty("flat", True)
        imp.setFixedWidth(30)
        imp.setToolTip("Import playlists (JSON)")
        imp.clicked.connect(self._import_playlists)
        head.addWidget(cap)
        head.addStretch(1)
        head.addWidget(imp)
        head.addWidget(add)
        lay.addSpacing(12)
        lay.addLayout(head)

        self._playlist_list = QListWidget()
        self._playlist_list.setProperty("sidebar", True)
        self._playlist_list.itemDoubleClicked.connect(self._open_playlist_item)
        self._playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._playlist_list.customContextMenuRequested.connect(self._playlist_menu)
        lay.addWidget(self._playlist_list, 1)
        return side

    def _build_queue_dock(self) -> None:
        from PyQt6.QtWidgets import QDockWidget

        self.queue_dock = QDockWidget("Up next", self)
        self.queue_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._queue_list = QListWidget()
        self._queue_list.setProperty("rows", True)
        self._queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._queue_list.customContextMenuRequested.connect(self._queue_menu)
        # drag & drop reordering (current row is pinned, the rest move freely)
        self._queue_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self._queue_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._queue_list.model().rowsMoved.connect(self._on_queue_rows_moved)
        self.queue_dock.setWidget(self._queue_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
        self.queue_dock.hide()
        self.resizeDocks([self.queue_dock], [config.QUEUE_WIDTH], Qt.Orientation.Horizontal)

    def _wire_internal(self) -> None:
        self.home_view.shelf("Quick picks").card_picked.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.home_view.shelf("Pinned favorites").card_picked.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.home_view.shelf("Recently played").card_picked.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.search_view.search_submitted.connect(self.search_submitted.emit)
        self.search_view.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.library_view.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.library_view.playlist_opened.connect(self.open_playlist)
        self.library_view.create_playlist_requested.connect(self._new_playlist_dialog)
        for view in (self.search_view, self.library_view._recent):
            view.menu_requested.connect(self._track_menu)
        self.player_bar.play_pause_requested.connect(self.play_pause_requested.emit)
        self.player_bar.next_requested.connect(self.next_requested.emit)
        self.player_bar.prev_requested.connect(self.prev_requested.emit)
        self.player_bar.shuffle_requested.connect(self.shuffle_requested.emit)
        self.player_bar.repeat_requested.connect(self.repeat_requested.emit)
        self.player_bar.volume_changed.connect(self.volume_changed.emit)
        self.player_bar.seek_requested.connect(self.seek_requested.emit)
        self.player_bar.pin_toggled.connect(self._on_pin_clicked)
        self.player_bar.queue_toggled.connect(self.toggle_queue)
        self.player_bar.lyrics_toggled.connect(lambda: self.show_view("now"))
        self.player_bar.radio_requested.connect(
            lambda: self.radio_requested.emit(None)
        )
        self.player_bar.rate_cycled.connect(self.rate_cycled.emit)
        self.player_bar.sleep_requested.connect(self.sleep_requested.emit)
        self.now_view.pin_toggled.connect(self._on_pin_clicked)
        self.now_view.radio_requested.connect(
            lambda: self.radio_requested.emit(None)
        )

    # --- navigation ---

    def show_view(self, name: str) -> None:
        if name not in self.VIEWS:
            return
        index = self.VIEWS.index(name)
        self.stack.setCurrentIndex(index)
        for key, btn in self._nav.items():
            btn.setChecked(key == name)
        if name == "home":
            self.home_refresh_requested.emit()
        elif name == "library":
            self.library_refresh_requested.emit()
        elif name == "search":
            self.search_view._box.setFocus()

    def focus_search(self) -> None:
        self.show_view("search")

    # --- home / library data ---

    def set_home_shelf(self, name: str, tracks: list[Track]) -> None:
        self.home_view.set_shelf(name, tracks)

    def set_favorites(self, tracks: list[Track]) -> None:
        self.library_view.set_favorites(tracks)
        self.home_view.set_shelf("Pinned favorites", tracks)

    def set_recent(self, tracks: list[Track]) -> None:
        self.library_view.set_recent(tracks)
        self.home_view.set_shelf("Recently played", tracks)

    # --- playlists ---

    def refresh_playlists(self) -> None:
        self._playlist_list.clear()
        if self.store is None:
            return
        for pid, name, count in self.store.playlists():
            item = QListWidgetItem(f"♪ {name}  ·  {count}")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self._playlist_list.addItem(item)

    def _new_playlist_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if not ok or not name.strip():
            return
        if self.store is not None:
            self.store.create_playlist(name)
        self.refresh_playlists()

    def _open_playlist_item(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid is not None:
            self.open_playlist(int(pid))

    def open_playlist(self, playlist_id: int) -> None:
        if self.store is None:
            return
        name = self.store.playlist_name(playlist_id)
        if name is None:
            return
        existing = self.findChild(PlaylistView, f"playlist-{playlist_id}")
        if existing is None:
            view = PlaylistView(self._palette, playlist_id, name)
            view.setObjectName(f"playlist-{playlist_id}")
            view.track_activated.connect(
                lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
            )
            view.play_all_requested.connect(self.playlist_picked.emit)
            view.shuffle_requested_sig.connect(
                lambda tracks: self.playlist_picked.emit(list(tracks), 0)
            )
            view.rename_requested.connect(self._rename_playlist)
            view.delete_requested.connect(self._delete_playlist)
            view.menu_requested.connect(self._playlist_track_menu)
            self.stack.addWidget(view)
        existing = self.findChild(PlaylistView, f"playlist-{playlist_id}")
        assert existing is not None
        existing.set_header(f"📁 {self.store.playlist_name(playlist_id) or name}")
        existing.set_tracks(self.store.playlist_tracks(playlist_id))
        self.stack.setCurrentWidget(existing)

    def _rename_playlist(self, playlist_id: int) -> None:
        if self.store is None:
            return
        current = self.store.playlist_name(playlist_id) or ""
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:", text=current)
        if not ok or not name.strip():
            return
        self.store.rename_playlist(playlist_id, name)
        self.refresh_playlists()
        self.open_playlist(playlist_id)

    def _delete_playlist(self, playlist_id: int) -> None:
        if self.store is None:
            return
        confirm, ok = QInputDialog.getText(
            self, "Delete playlist", "Type DELETE to confirm:"
        )
        if not ok or confirm.strip().upper() != "DELETE":
            return
        self.store.delete_playlist(playlist_id)
        view = self.findChild(PlaylistView, f"playlist-{playlist_id}")
        if view is not None:
            self.stack.removeWidget(view)
            view.deleteLater()
        self.refresh_playlists()
        self.show_view("library")

    # --- context menus ---

    def _track_menu(self, track: Track, menu: QMenu) -> None:
        play_next = menu.addAction("▶ Play next")
        enqueue = menu.addAction("➕ Add to queue")
        radio = menu.addAction("📻 Start radio")
        menu.addSeparator()
        pinned = self.store.is_pinned(track.video_id) if self.store else False
        pin = menu.addAction("♥ Unpin" if pinned else "♡ Pin to favorites")
        menu.addSeparator()
        playlists_menu = menu.addMenu("📌 Add to playlist")
        if self.store is not None:
            for pid, name, _count in self.store.playlists():
                playlists_menu.addAction(name).setData(pid)
            playlists_menu.addSeparator()
            new_act = playlists_menu.addAction("＋ New playlist…")
            new_act.setData(-1)

        def _add_to(playlist_id: int) -> None:
            if playlist_id == -1:
                name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
                if not ok or not name.strip() or self.store is None:
                    return
                playlist_id = self.store.create_playlist(name)
                self.refresh_playlists()
            if self.store is not None and self.store.add_to_playlist(playlist_id, track):
                self.refresh_playlists()

        play_next.triggered.connect(lambda: self.play_next_requested.emit(track))
        enqueue.triggered.connect(lambda: self.enqueue_requested.emit(track))
        radio.triggered.connect(lambda: self.radio_requested.emit(track))
        pin.triggered.connect(lambda: self.pin_toggled.emit(track))
        playlists_menu.triggered.connect(
            lambda act: _add_to(int(act.data()) if act.data() is not None else -1)
        )

    def _playlist_track_menu(self, track: Track, menu: QMenu) -> None:
        view = self.sender()
        if isinstance(view, PlaylistView):
            remove = menu.addAction("✕ Remove from this playlist")
            remove.triggered.connect(
                lambda: (self.store.remove_from_playlist(view.playlist_id, track.video_id),
                         self.open_playlist(view.playlist_id),
                         self.refresh_playlists())
            )
            menu.addSeparator()

    def _playlist_menu(self, pos) -> None:
        item = self._playlist_list.itemAt(pos)
        if item is None:
            return
        pid = int(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        open_act = menu.addAction("Open")
        export_act = menu.addAction("⬇ Export…")
        rename_act = menu.addAction("Rename")
        delete_act = menu.addAction("Delete")
        chosen = menu.exec(self._playlist_list.viewport().mapToGlobal(pos))
        if chosen is open_act:
            self.open_playlist(pid)
        elif chosen is export_act:
            self._export_playlist(pid)
        elif chosen is rename_act:
            self._rename_playlist(pid)
        elif chosen is delete_act:
            self._delete_playlist(pid)

    # --- playlist share (export / import) ---

    def _export_playlist(self, playlist_id: int) -> None:
        if self.store is None:
            return
        name = self.store.playlist_name(playlist_id)
        if name is None:
            return
        tracks = self.store.playlist_tracks(playlist_id)
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export playlist",
            f"{name}{config.PLAYLIST_SUFFIX}",
            "Hearth playlist (*.json);;All files (*)",
        )
        if not path:
            return
        payload = json.dumps(share.encode_playlist(name, tracks), ensure_ascii=False, indent=2)
        try:
            Path(path).write_text(payload, encoding="utf-8")
        except OSError:
            self.set_status(f"Could not write {path}")
            return
        self.set_status(f"Exported {len(tracks)} tracks → {path}")

    def _import_playlists(self) -> None:
        if self.store is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import playlists", "",
            "Hearth playlist (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            self.set_status(f"Could not read {path}")
            return
        imported = share.decode_playlists_text(text)
        if not imported:
            self.set_status("No playlists found in that file")
            return
        for name, tracks in imported:
            pid = self.store.create_playlist(name)
            for track in tracks:
                self.store.add_to_playlist(pid, track)
        self.refresh_playlists()
        self.set_status(f"Imported {len(imported)} playlist(s) from {path}")

    def _queue_menu(self, pos) -> None:
        item = self._queue_list.itemAt(pos)
        if item is None:
            return
        index = self._queue_list.row(item)
        menu = QMenu(self)
        remove = menu.addAction("✕ Remove from queue")
        chosen = menu.exec(self._queue_list.viewport().mapToGlobal(pos))
        if chosen is remove:
            self.queue_remove_requested.emit(index)

    # --- queue dock ---

    def toggle_queue(self) -> None:
        self.queue_dock.setVisible(not self.queue_dock.isVisible())

    def set_queue(self, upcoming: list[Track], current: Track | None = None) -> None:
        self._queue_list.clear()
        if current is not None:
            row = TrackRow(self._palette, current, 0)
            row._title.setText(f"▶ {current.title}")
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, current)
            item.setData(Qt.ItemDataRole.UserRole + 1, "current")
            # the playing row is pinned — only upcoming tracks reorder
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self._queue_list.addItem(item)
            self._queue_list.setItemWidget(item, row)
        for index, track in enumerate(upcoming, start=1):
            item = QListWidgetItem()
            item.setSizeHint(TrackRow(self._palette, track, index).sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setData(Qt.ItemDataRole.UserRole + 1, "upcoming")
            self._queue_list.addItem(item)
            self._queue_list.setItemWidget(
                item, TrackRow(self._palette, track, index)
            )

    def _on_queue_rows_moved(self, *_args) -> None:
        """Drag & drop finished: read back the new upcoming order."""
        reordered: list[Track] = []
        for row in range(self._queue_list.count()):
            item = self._queue_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole + 1) == "upcoming":
                track = item.data(Qt.ItemDataRole.UserRole)
                if track is not None:
                    reordered.append(track)
        if reordered:
            self.queue_reorder_requested.emit(reordered)

    # --- pin ---

    def _on_pin_clicked(self) -> None:
        track = self.player_bar.current_track
        if track is not None:
            self.pin_toggled.emit(track)

    # --- panel-compatible state API ---

    def set_track(self, track: Track | None) -> None:
        self.player_bar.set_track(track)
        self.now_view.set_track(track)
        if track is None:
            self.setWindowTitle(f"🔥 {config.APP_NAME} — {config.APP_TAGLINE}")
        else:
            self.setWindowTitle(f"▶ {track.display_name} — 🔥 {config.APP_NAME}")

    def set_pinned(self, pinned: bool) -> None:
        self.player_bar.set_pinned(pinned)
        self.now_view.set_pinned(pinned)

    def set_playing(self, playing: bool) -> None:
        self.player_bar.set_playing(playing)

    def set_status(self, text: str) -> None:
        self.player_bar.set_status(text)

    def set_position(self, position_ms: int) -> None:
        self.player_bar.set_position(position_ms)

    def set_duration(self, duration_ms: int) -> None:
        self.player_bar.set_duration(duration_ms)

    def set_volume(self, value: float) -> None:
        self.player_bar.set_volume(value)

    def show_search_results(self, tracks: list[Track]) -> None:
        self.search_view.set_tracks(list(tracks))

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.now_view.apply_palette(palette)
        self.setStyleSheet(build_stylesheet(palette))

    def summon(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
