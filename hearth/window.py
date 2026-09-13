"""The big stage: sidebar, home shelves, search, library, player bar.

Layout conventions follow the familiar three-pane desktop music player:
navigation on the left, content cards up top, transport controls pinned
to the bottom. Everything here is original Hearth code painted from the
active Palette — no assets, no third-party marks.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
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
    QStackedLayout,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import config, share, world
from .config import Palette, get_palette
from .cover import CoverTile
from .lyrics import LrcLine, SyncedLyrics
from .models import Album, Artist, Track
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
        for name in ("Quick picks", "Top tracks", "Pinned favorites", "Recently played"):
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

    def set_visible_rows(self, rows: int) -> None:
        """Cap the list to `rows` visible rows (embeds inside scroll pages)."""
        rows = max(1, min(int(rows), 12))
        self._list.setFixedHeight(rows * (config.ROW_HEIGHT + 8) + 14)

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
        if not isinstance(track, Track):
            return
        menu = QMenu(self)
        self.menu_requested.emit(track, menu)
        menu.exec(self._list.viewport().mapToGlobal(pos))


class SearchView(TrackListView):
    """The search page: query box, scope chips, and the result rows."""

    search_submitted = pyqtSignal(str)
    search_scoped = pyqtSignal(str, str)      # query, scope ("songs"/"videos"/"albums")
    album_opened = pyqtSignal(object)         # Album (double-click an album result)

    SCOPES = (("songs", "♪ Songs"), ("videos", "▶ Videos"), ("albums", "💿 Albums"))

    def __init__(self, palette: Palette):
        super().__init__(palette)
        self._head.setText("Search")
        self.set_tracks([])
        self._scope = "songs"
        self._box = QLineEdit()
        self._box.setPlaceholderText("What do you want to play?  (or paste a link)")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._emit_search)
        self._box.textEdited.connect(lambda _: self._debounce.start())
        self._box.returnPressed.connect(self._emit_search)
        self.layout().insertWidget(0, self._box)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for scope, label in self.SCOPES:
            chip = QPushButton(label)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setChecked(scope == self._scope)
            chip.clicked.connect(lambda _=False, s=scope: self.set_scope(s))
            self._chips[scope] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        self.layout().insertLayout(1, chips)
        self._count.hide()

    # --- scope ---

    def set_scope(self, scope: str) -> None:
        if scope not in self._chips:
            return
        changed = scope != self._scope
        self._scope = scope
        for name, chip in self._chips.items():
            chip.setChecked(name == scope)
        if changed and self.query():
            self.search_scoped.emit(self.query(), scope)

    def scope(self) -> str:
        return self._scope

    # --- results ---

    def set_albums(self, albums: list[Album]) -> None:
        """Show album cards instead of track rows (albums scope)."""
        self._tracks = []
        self._list.clear()
        for album in albums:
            label = album.title if not album.year else f"{album.title}  ·  {album.year}"
            item = QListWidgetItem(f"💿  {label}\n      {album.artist or 'Unknown artist'}")
            item.setSizeHint(QSize(0, config.ROW_HEIGHT + 24))
            item.setData(Qt.ItemDataRole.UserRole, album)
            self._list.addItem(item)

    def _emit_search(self) -> None:
        query = self._box.text().strip()
        if not query:
            return
        if self._scope == "songs":
            self.search_submitted.emit(query)
        else:
            self.search_scoped.emit(query, self._scope)

    def set_query(self, text: str) -> None:
        self._box.setText(text)

    def query(self) -> str:
        return self._box.text().strip()

    def _on_double(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, Album):
            self.album_opened.emit(data)
            return
        if data is not None:
            self.track_activated.emit(data, list(self._tracks))


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


class DiscoverView(QWidget):
    """The whole world's music: charts, new releases, trending, moods & genres.

    The view stays deliberately dumb — every click just asks the app for
    data via a signal, and the app pushes content back in through
    set_sections / set_collections / set_track_list.
    """

    category_selected = pyqtSignal(str)        # mood/genre params
    collection_opened = pyqtSignal(object)     # Collection | Album card clicked
    charts_requested = pyqtSignal()
    explore_requested = pyqtSignal(str)        # "new_releases" | "trending" | "new_videos"
    track_activated = pyqtSignal(object, list)
    menu_requested = pyqtSignal(object, object)

    MAX_GRID_CARDS = 60

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._sections: list[tuple[str, list[dict]]] = []
        self._mode = ""          # which chip is lit ("section" or an explore mode)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        hero = QLabel("🌍 Discover")
        hero.setProperty("hero", True)
        self._status = QLabel("every mood, genre and corner of the world's music")
        self._status.setProperty("dim", True)
        head.addWidget(hero)
        head.addStretch(1)
        head.addWidget(self._status)
        outer.addLayout(head)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for key, label in (
            ("charts", "🔥 Charts"),
            ("new_releases", "✨ New releases"),
            ("trending", "🎶 Trending"),
            ("new_videos", "🎬 New videos"),
        ):
            chip = QPushButton(label)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=key: self._chip_clicked(k))
            self._chips[key] = chip
            chips.addWidget(chip)
        self._chip_sep = QLabel("·")
        self._chip_sep.setProperty("dim", True)
        chips.addWidget(self._chip_sep)
        chips.addStretch(1)
        self._chips_row = chips          # direct handle — section chips insert here
        outer.addLayout(chips)

        self._body = QStackedWidget()
        outer.addWidget(self._body, 1)

        # page 0 — grid: subcategory list + collection cards
        grid_page = QWidget()
        grid_lay = QHBoxLayout(grid_page)
        grid_lay.setContentsMargins(0, 0, 0, 0)
        grid_lay.setSpacing(12)
        self._cat_list = QListWidget()
        self._cat_list.setProperty("sidebar", True)
        self._cat_list.setFixedWidth(200)
        self._cat_list.itemClicked.connect(self._category_clicked)
        grid_lay.addWidget(self._cat_list)
        self._grid_area = QScrollArea()
        self._grid_area.setWidgetResizable(True)
        self._grid_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._grid_host = QWidget()
        self._grid_lay = QGridLayout(self._grid_host)
        self._grid_lay.setContentsMargins(0, 0, 8, 0)
        self._grid_lay.setSpacing(10)
        self._grid_lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._grid_area.setWidget(self._grid_host)
        grid_lay.addWidget(self._grid_area, 1)
        self._body.addWidget(grid_page)

        # page 1 — straight track list (trending / new videos)
        self._track_page = TrackListView(palette)
        self._track_page.track_activated.connect(self.track_activated)
        self._track_page.menu_requested.connect(self.menu_requested)
        self._body.addWidget(self._track_page)

    # --- chips / navigation ---

    def _chip_clicked(self, key: str) -> None:
        if key == "charts":
            self._light_chip("charts")
            self.charts_requested.emit()
        elif key in ("new_releases", "trending", "new_videos"):
            self._light_chip(key)
            self.explore_requested.emit(key)

    def _light_chip(self, key: str) -> None:
        self._mode = key
        for name, chip in self._chips.items():
            chip.setChecked(name == key)

    def set_sections(self, sections: list[tuple[str, list[dict]]]) -> None:
        """(Re)build the mood/genre section chips and open the first one."""
        self._sections = list(sections)
        # drop stale section chips (everything after the built-in four)
        for name in [k for k in self._chips if k not in
                     ("charts", "new_releases", "trending", "new_videos")]:
            chip = self._chips.pop(name)
            chip.deleteLater()
        for index, (title, _subs) in enumerate(self._sections):
            chip = QPushButton(title)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            key = f"section-{index}"
            chip.clicked.connect(
                lambda _=False, i=index, k=key: self._section_chip(i, k)
            )
            self._chips[key] = chip
            self._chips_row.insertWidget(
                self._chips_row.indexOf(self._chip_sep) + 1 + index, chip
            )
        if self._sections:
            self._section_chip(0, "section-0")

    def _section_chip(self, index: int, key: str) -> None:
        self._light_chip(key)
        self.show_section(index)

    def show_section(self, index: int) -> None:
        """Fill the subcategory list for a section and select the first one."""
        if not (0 <= index < len(self._sections)):
            return
        _title, submenus = self._sections[index]
        self._cat_list.clear()
        for sub in submenus:
            item = QListWidgetItem(sub.get("title", "?"))
            item.setData(Qt.ItemDataRole.UserRole, sub.get("params", ""))
            self._cat_list.addItem(item)
        self._mode = "section"
        self._body.setCurrentIndex(0)
        self._cat_list.setVisible(bool(submenus))
        if self._cat_list.count():
            self._cat_list.setCurrentRow(0)
            self.category_selected.emit(submenus[0].get("params", ""))

    def _category_clicked(self, item: QListWidgetItem) -> None:
        params = item.data(Qt.ItemDataRole.UserRole)
        if params:
            self.category_selected.emit(str(params))

    # --- content in ---

    def set_collections(self, items: list) -> None:
        """Grid of Collection / Album cards."""
        self._cat_list.setVisible(self._mode == "section")
        self._body.setCurrentIndex(0)
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, thing in enumerate(items[: self.MAX_GRID_CARDS]):
            self._grid_lay.addWidget(
                self._make_card(thing), index // 4, index % 4
            )
        overflow = len(items) - self.MAX_GRID_CARDS
        if overflow > 0:
            note = QLabel(f"… and {overflow} more — pick a subcategory to narrow it down")
            note.setProperty("dim", True)
            rows = (self.MAX_GRID_CARDS + 3) // 4
            self._grid_lay.addWidget(note, rows, 0, 1, 4)

    def _make_card(self, thing) -> QPushButton:
        card = QPushButton()
        card.setProperty("card", True)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFixedSize(config.DISCOVER_CARD_SIZE, config.DISCOVER_CARD_SIZE + 64)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(10, 10, 10, 10)
        inner.setSpacing(4)
        tile = CoverTile(self._palette, config.DISCOVER_CARD_SIZE - 20)
        thumbnail = getattr(thing, "thumbnail", "")
        if thumbnail:
            tile.set_track_cover(thumbnail)
        title = QLabel(thing.title)
        title.setWordWrap(True)
        title.setMaximumHeight(30)
        subtitle = getattr(thing, "subtitle", "") or getattr(thing, "artist", "")
        sub = QLabel(str(subtitle or ""))
        sub.setProperty("dim", True)
        inner.addWidget(tile)
        inner.addWidget(title, 1)
        inner.addWidget(sub)
        card.clicked.connect(lambda _=False, t=thing: self.collection_opened.emit(t))
        return card

    def set_track_list(self, title: str, tracks: list[Track]) -> None:
        """Straight playable list (trending / new videos)."""
        self._mode = ""
        self._body.setCurrentIndex(1)
        self._track_page.set_header(title)
        self._track_page.set_tracks(list(tracks))

    def set_status(self, text: str) -> None:
        self._status.setText(text)


class RemotePlaylistView(TrackListView):
    """A curated Discover playlist opened as a page: play all / shuffle / queue all."""

    play_all_requested = pyqtSignal(list, int)
    shuffle_requested_sig = pyqtSignal(list)
    enqueue_all_requested = pyqtSignal(list)

    def __init__(self, palette: Palette):
        super().__init__(palette)
        actions = QHBoxLayout()
        play = QPushButton("▶ Play all")
        play.setProperty("accent", True)
        play.clicked.connect(lambda: self.play_all_requested.emit(list(self._tracks), 0))
        shuffle = QPushButton("🔀 Shuffle")
        shuffle.clicked.connect(lambda: self.shuffle_requested_sig.emit(list(self._tracks)))
        enqueue = QPushButton("➕ Queue all")
        enqueue.setToolTip("Append every track to the up-next queue")
        enqueue.clicked.connect(lambda: self.enqueue_all_requested.emit(list(self._tracks)))
        for b in (play, shuffle, enqueue):
            actions.addWidget(b)
        actions.addStretch(1)
        self.layout().insertLayout(2, actions)


class WorldView(QWidget):
    """The World Explorer: a curated dial of every kind of music on Earth.

    Genre stations across nine regions — tap one and the app tunes a
    station (search-everywhere backed, so the dial never comes back
    static). A filter narrows the dial; the dice tunes a surprise.
    All data is local (hearth.world), so the page paints instantly,
    network or no network.
    """

    station_requested = pyqtSignal(object)     # world.Genre

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        hero = QLabel("🗺️ World Explorer")
        hero.setProperty("hero", True)
        self._status = QLabel(
            f"{len(world.genres())} stations — every continent, every era"
        )
        self._status.setProperty("dim", True)
        head.addWidget(hero)
        head.addStretch(1)
        head.addWidget(self._status)
        surprise = QPushButton("🎲 Surprise me")
        surprise.setToolTip("Tune a random genre from anywhere on Earth")
        surprise.clicked.connect(self._surprise)
        head.addWidget(surprise)
        outer.addLayout(head)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(
            "Filter the dial — try 'Africa', 'metal', 'bhangra'…"
        )
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        outer.addWidget(self._filter)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(0, 4, 8, 12)
        host_lay.setSpacing(12)
        area.setWidget(host)
        outer.addWidget(area, 1)

        # (region caption, [chip, ...]) — kept for the filter to sweep
        self._sections: list[tuple[QLabel, list[QPushButton]]] = []
        for region, items in world.genres_by_region():
            cap = QLabel(region.upper())
            cap.setProperty("dim", True)
            host_lay.addWidget(cap)
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            host_lay.addWidget(grid_host)
            chips: list[QPushButton] = []
            for index, g in enumerate(items):
                chip = QPushButton(f"{g.emoji} {g.label}")
                chip.setProperty("chip", True)
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.setToolTip(f"{g.blurb}\n(region: {g.region})")
                chip.setProperty("genre", g)
                chip.clicked.connect(
                    lambda _=False, gg=g: self.station_requested.emit(gg)
                )
                grid.addWidget(chip, index // 4, index % 4)
                chips.append(chip)
            self._sections.append((cap, chips))

    # --- filter / dice ---

    def _apply_filter(self, text: str) -> None:
        needle = text.strip()
        visible = 0
        for cap, chips in self._sections:
            any_visible = False
            for chip in chips:
                g = chip.property("genre")
                show = (not needle) or world.match(g, needle)
                chip.setVisible(show)
                any_visible = any_visible or show
                visible += 1 if show else 0
            cap.setVisible(any_visible)
        total = len(world.genres())
        if not needle:
            self._status.setText(f"{total} stations — every continent, every era")
        else:
            self._status.setText(
                f"{visible} of {total} stations match “{needle}”"
            )

    def _surprise(self) -> None:
        self.station_requested.emit(world.random_genre())

    def set_status(self, text: str) -> None:
        self._status.setText(text)


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


class AlbumView(TrackListView):
    """One album's track list with Play all / Shuffle actions."""

    play_all_requested = pyqtSignal(list, int)
    shuffle_requested_sig = pyqtSignal(list)

    def __init__(self, palette: Palette):
        super().__init__(palette)
        actions = QHBoxLayout()
        play = QPushButton("▶ Play all")
        play.setProperty("accent", True)
        play.clicked.connect(lambda: self.play_all_requested.emit(list(self._tracks), 0))
        shuffle = QPushButton("🔀 Shuffle")
        shuffle.clicked.connect(lambda: self.shuffle_requested_sig.emit(list(self._tracks)))
        for b in (play, shuffle):
            actions.addWidget(b)
        actions.addStretch(1)
        self.layout().insertLayout(2, actions)


class ArtistView(QWidget):
    """One artist's stage: face, story, top tracks, releases, kindred acts."""

    play_all_requested = pyqtSignal(list, int)
    shuffle_requested_sig = pyqtSignal(list)
    track_activated = pyqtSignal(object, list)     # Track, context — top tracks
    album_opened = pyqtSignal(object)      # Album — drill into a release
    artist_opened = pyqtSignal(object)     # Artist — a related act's page
    menu_requested = pyqtSignal(object, object)   # Track, QMenu (top tracks)

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._artist: Artist | None = None

        area = QScrollArea()
        area.setWidgetResizable(True)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 18, 24, 12)
        lay.setSpacing(10)

        # --- face + identity ---
        head = QHBoxLayout()
        head.setSpacing(16)
        self._avatar = CoverTile(palette, config.ARTIST_AVATAR)
        ident = QVBoxLayout()
        ident.setSpacing(4)
        self._name = QLabel("Artist")
        self._name.setProperty("hero", True)
        self._name.setWordWrap(True)
        self._meta = QLabel("")
        self._meta.setProperty("dim", True)
        self._meta.setWordWrap(True)
        ident.addWidget(self._name)
        ident.addWidget(self._meta)
        ident.addStretch(1)
        head.addWidget(self._avatar)
        head.addLayout(ident, 1)
        lay.addLayout(head)

        # --- actions ---
        actions = QHBoxLayout()
        play = QPushButton("▶ Play top tracks")
        play.setProperty("accent", True)
        play.clicked.connect(
            lambda: self.play_all_requested.emit(list(self._top_tracks()), 0)
        )
        shuffle = QPushButton("🔀 Shuffle")
        shuffle.clicked.connect(
            lambda: self.shuffle_requested_sig.emit(list(self._top_tracks()))
        )
        for b in (play, shuffle):
            actions.addWidget(b)
        actions.addStretch(1)
        lay.addLayout(actions)

        # --- top tracks (embedded list, capped height) ---
        self._top = TrackListView(palette)
        self._top.set_header("Top tracks")
        self._top.track_activated.connect(self.track_activated.emit)
        self._top.menu_requested.connect(self.menu_requested.emit)
        lay.addWidget(self._top)

        # --- albums & singles ---
        self._albums_cap = QLabel("Albums")
        self._albums_cap.setProperty("shelf", True)
        self._albums_grid = QGridLayout()
        self._albums_grid.setSpacing(10)
        lay.addWidget(self._albums_cap)
        lay.addLayout(self._albums_grid)
        self._singles_cap = QLabel("Singles")
        self._singles_cap.setProperty("shelf", True)
        self._singles_grid = QGridLayout()
        self._singles_grid.setSpacing(10)
        lay.addWidget(self._singles_cap)
        lay.addLayout(self._singles_grid)

        # --- related artists ---
        self._related_cap = QLabel("Fans also like")
        self._related_cap.setProperty("shelf", True)
        self._related_row = QHBoxLayout()
        self._related_row.setSpacing(6)
        lay.addWidget(self._related_cap)
        lay.addLayout(self._related_row)
        lay.addStretch(1)

        area.setWidget(page)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(area)

        self._empty_sections()

    def _empty_sections(self) -> None:
        self._albums_cap.setVisible(False)
        self._albums_grid.setEnabled(False)
        self._singles_cap.setVisible(False)
        self._related_cap.setVisible(False)

    def _top_tracks(self) -> list[Track]:
        return self._top.current_tracks if hasattr(self, "_top") else []

    # --- content in ---

    def set_artist(self, artist: Artist) -> None:
        self._artist = artist
        if artist.thumbnail:
            self._avatar.set_track_cover(artist.thumbnail)
        else:
            self._avatar.set_mark()
        self._name.setText(artist.name)
        self._meta.setText(artist.meta_line)
        self._top.set_tracks(list(artist.top_tracks))
        self._top.set_visible_rows(
            len(artist.top_tracks) or 1
        )
        self._fill_grid(self._albums_grid, artist.albums, self._albums_cap)
        self._fill_grid(self._singles_grid, artist.singles, self._singles_cap)
        self._fill_related(artist.related)

    def _fill_grid(self, grid: QGridLayout, albums: list[Album],
                   caption: QLabel) -> None:
        """One grid of release cards; the section hides itself when empty."""
        while grid.count():
            item = grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, album in enumerate(albums):
            card = self._release_card(album)
            grid.addWidget(card, index // 4, index % 4)
        caption.setVisible(bool(albums))
        grid.setEnabled(bool(albums))

    def _release_card(self, album: Album) -> QPushButton:
        card = QPushButton()
        card.setProperty("card", True)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFixedSize(config.ARTIST_CARD_SIZE, config.ARTIST_CARD_SIZE + 58)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(10, 10, 10, 10)
        inner.setSpacing(4)
        tile = CoverTile(self._palette, config.ARTIST_CARD_SIZE - 20)
        if album.thumbnail:
            tile.set_track_cover(album.thumbnail)
        title = QLabel(album.title)
        title.setWordWrap(True)
        title.setMaximumHeight(30)
        sub = QLabel(album.year or album.artist or "")
        sub.setProperty("dim", True)
        inner.addWidget(tile)
        inner.addWidget(title, 1)
        inner.addWidget(sub)
        card.clicked.connect(lambda _=False, a=album: self.album_opened.emit(a))
        return card

    def _fill_related(self, related: list[Artist]) -> None:
        while self._related_row.count():
            item = self._related_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for act in related:
            chip = QPushButton(f"🎤 {act.name}")
            chip.setProperty("chip", True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(
                lambda _=False, a=act: self.artist_opened.emit(a)
            )
            self._related_row.addWidget(chip)
        self._related_row.addStretch(1)
        self._related_cap.setVisible(bool(related))

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._top.apply_palette(palette)

    @property
    def current_artist(self) -> Artist | None:
        return self._artist


# ----------------------------------------------------------------- now playing

class LyricsSheet(QWidget):
    """The lyrics pane: plain text, or LRC lines that glow with the song.

    In synced mode the active line is lit in the palette accent and kept
    centered; clicking any line seeks the player to that moment.
    """

    line_clicked = pyqtSignal(int)   # ms — click a lyric line to seek there

    def __init__(self, palette: Palette):
        super().__init__()
        self._palette = palette
        self._sync: SyncedLyrics | None = None
        self._active = -2                       # -2 = nothing highlighted yet

        pages = QStackedLayout(self)
        pages.setContentsMargins(0, 0, 0, 0)
        self._plain = QPlainTextEdit()
        self._plain.setProperty("lyrics", True)
        self._plain.setReadOnly(True)
        self._plain.setPlaceholderText(
            "Lyrics show up here once something is playing."
        )
        self._sheet = QListWidget()
        self._sheet.setProperty("lyrics", True)
        self._sheet.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._sheet.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._sheet.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sheet.itemClicked.connect(self._on_clicked)
        pages.addWidget(self._plain)
        pages.addWidget(self._sheet)
        self._pages = pages

    # --- content in ---

    def show_message(self, text: str) -> None:
        """Plain-text state (loading notices, empty results)."""
        self._sync = None
        self._active = -2
        self._pages.setCurrentWidget(self._plain)
        self._plain.setPlainText(text)

    def set_plain(self, text: str | None) -> None:
        self._sync = None
        self._active = -2
        self._pages.setCurrentWidget(self._plain)
        self._plain.setPlainText(text or "No lyrics available for this track.")

    def set_synced(self, lines: list[LrcLine]) -> None:
        if not lines:
            self.set_plain(None)
            return
        self._sync = SyncedLyrics(lines)
        self._active = -2
        self._sheet.clear()
        dim = QColor(self._palette.text_dim)
        for line in self._sync.lines:
            item = QListWidgetItem(line.text or "♪")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            )
            item.setData(Qt.ItemDataRole.UserRole, line.time_ms)
            item.setToolTip(clock(line.time_ms))
            item.setForeground(dim)
            font = QFont()
            font.setPixelSize(15)
            item.setFont(font)
            self._sheet.addItem(item)
        self._pages.setCurrentWidget(self._sheet)

    # --- position in / interaction out ---

    def set_position(self, position_ms: int) -> None:
        """Light the line that owns this moment (no-op in plain mode)."""
        if self._sync is None or self._sync.empty:
            return
        index = self._sync.line_at(position_ms)
        if index == self._active:
            return
        self._activate(index)

    def _activate(self, index: int) -> None:
        if 0 <= self._active < self._sheet.count():
            prev = self._sheet.item(self._active)
            font = prev.font()
            font.setBold(False)
            prev.setFont(font)
            prev.setForeground(QColor(self._palette.text_dim))
        self._active = index
        if 0 <= index < self._sheet.count():
            item = self._sheet.item(index)
            font = item.font()
            font.setBold(True)
            font.setPixelSize(16)
            item.setFont(font)
            item.setForeground(QColor(self._palette.accent))
            self._sheet.scrollToItem(
                item, QAbstractItemView.ScrollHint.PositionAtCenter
            )

    def _on_clicked(self, item: QListWidgetItem) -> None:
        ms = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(ms, int):
            self.line_clicked.emit(ms)

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        if self._sync is None:
            return
        active_color = QColor(self._palette.accent)
        dim = QColor(self._palette.text_dim)
        for index in range(self._sheet.count()):
            item = self._sheet.item(index)
            if index == self._active:
                item.setForeground(active_color)
            else:
                item.setForeground(dim)


class NowView(QWidget):
    """The Now Playing stage: big cover, identity, and the lyrics sheet."""

    pin_toggled = pyqtSignal()
    radio_requested = pyqtSignal()
    lyrics_seek_requested = pyqtSignal(int)   # ms — click a lyric line, go there

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
        self._lyrics = LyricsSheet(palette)
        self._lyrics.line_clicked.connect(self.lyrics_seek_requested.emit)
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
            self._lyrics.show_message("")
            return
        self._video_id = track.video_id
        self._title.setText(track.title)
        self._artist.setText(track.artist)
        if track.thumbnail:
            self._cover.set_track_cover(track.thumbnail)
        else:
            self._cover.set_mark()

    def set_lyrics(self, video_id: str, text: str | None,
                   lines: list[LrcLine] | None = None) -> None:
        """Late-arriving lyrics; drop them if the track moved on meanwhile."""
        if video_id != self._video_id:
            return
        if lines:
            self._lyrics.set_synced(lines)
        else:
            self._lyrics.set_plain(text)

    def set_lyrics_loading(self) -> None:
        self._lyrics.show_message("Loading lyrics…")

    def set_position(self, position_ms: int) -> None:
        """Keep the glowing lyric line in step with the song."""
        self._lyrics.set_position(position_ms)

    def set_pinned(self, pinned: bool) -> None:
        self._pin.setText("♥" if pinned else "♡")

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._cover.apply_palette(palette)
        self._lyrics.apply_palette(palette)

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
    search_scoped = pyqtSignal(str, str)          # query, scope
    album_opened = pyqtSignal(object)             # Album — open its page
    artist_opened = pyqtSignal(object)            # Track | Artist | Album — artist page
    track_picked = pyqtSignal(object)             # single card pick
    playlist_picked = pyqtSignal(list, int)       # play list from index
    play_next_requested = pyqtSignal(object)      # insert at queue head
    enqueue_requested = pyqtSignal(object)        # append to queue
    pin_toggled = pyqtSignal(object)              # Track
    queue_remove_requested = pyqtSignal(int)
    queue_reorder_requested = pyqtSignal(list)    # new upcoming order
    queue_jump_requested = pyqtSignal(int)        # upcoming index to play now
    queue_clear_requested = pyqtSignal()
    radio_requested = pyqtSignal(object)          # Track | None (None = current)
    rate_cycled = pyqtSignal()
    sleep_requested = pyqtSignal(int)             # minutes; 0 = off
    mute_toggled = pyqtSignal()
    home_refresh_requested = pyqtSignal()
    library_refresh_requested = pyqtSignal()
    discover_refresh_requested = pyqtSignal()
    discover_category_selected = pyqtSignal(str)     # mood/genre params
    discover_collection_opened = pyqtSignal(object)  # Collection | Album
    discover_charts_requested = pyqtSignal()
    discover_explore_requested = pyqtSignal(str)     # new_releases|trending|new_videos
    discover_enqueue_all_requested = pyqtSignal(list)  # queue a whole curated list
    world_station_requested = pyqtSignal(object)     # world.Genre — tune a station
    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    shuffle_requested = pyqtSignal()
    repeat_requested = pyqtSignal()
    volume_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(int)

    VIEWS = ("home", "discover", "world", "search", "library", "now")

    def __init__(self, palette_key: str | None = None,
                 store: HearthStore | None = None):
        super().__init__()
        self._palette = get_palette(palette_key)
        self.store = store
        self.setWindowTitle(f"🔥 {config.APP_NAME} — {config.APP_TAGLINE}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        self.home_view = HomeView(self._palette)
        self.discover_view = DiscoverView(self._palette)
        self.world_view = WorldView(self._palette)
        self.search_view = SearchView(self._palette)
        self.library_view = LibraryView(self._palette)
        self.now_view = NowView(self._palette)
        self.album_view = AlbumView(self._palette)
        self.remote_playlist_view = RemotePlaylistView(self._palette)
        self.artist_view = ArtistView(self._palette)

        self.stack = QStackedWidget()
        for view in (self.home_view, self.discover_view, self.world_view,
                     self.search_view, self.library_view, self.now_view,
                     self.album_view, self.remote_playlist_view,
                     self.artist_view):
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
        self._install_shortcuts()
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
        for key, label in (("home", "🏠 Home"), ("discover", "🧭 Discover"),
                           ("world", "🗺️ World"), ("search", "🔍 Search"),
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
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(2)
        tools = QHBoxLayout()
        tools.addStretch(1)
        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("flat", True)
        clear_btn.setToolTip("Remove every upcoming track")
        clear_btn.clicked.connect(self.queue_clear_requested.emit)
        tools.addWidget(clear_btn)
        body_lay.addLayout(tools)
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
        self._queue_list.itemDoubleClicked.connect(
            lambda item: self._queue_jump_from_row(self._queue_list.row(item))
        )
        body_lay.addWidget(self._queue_list, 1)
        self.queue_dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
        self.queue_dock.hide()
        self.resizeDocks([self.queue_dock], [config.QUEUE_WIDTH], Qt.Orientation.Horizontal)

    def _wire_internal(self) -> None:
        for shelf_name in ("Quick picks", "Top tracks", "Pinned favorites",
                           "Recently played"):
            self.home_view.shelf(shelf_name).card_picked.connect(
                lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
            )
        self.search_view.search_submitted.connect(self.search_submitted.emit)
        self.search_view.search_scoped.connect(self.search_scoped.emit)
        self.search_view.album_opened.connect(self.album_opened.emit)
        self.search_view.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.album_view.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.album_view.play_all_requested.connect(self.playlist_picked.emit)
        self.album_view.shuffle_requested_sig.connect(
            lambda tracks: self.playlist_picked.emit(list(tracks), 0)
        )
        self.album_view.menu_requested.connect(self._track_menu)
        d = self.discover_view
        d.category_selected.connect(self.discover_category_selected.emit)
        d.collection_opened.connect(self.discover_collection_opened.emit)
        d.charts_requested.connect(self.discover_charts_requested.emit)
        d.explore_requested.connect(self.discover_explore_requested.emit)
        self.world_view.station_requested.connect(self.world_station_requested.emit)
        d.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        d.menu_requested.connect(self._track_menu)
        self.remote_playlist_view.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        self.remote_playlist_view.play_all_requested.connect(self.playlist_picked.emit)
        self.remote_playlist_view.shuffle_requested_sig.connect(
            lambda tracks: self.playlist_picked.emit(list(tracks), 0)
        )
        self.remote_playlist_view.menu_requested.connect(self._track_menu)
        self.remote_playlist_view.enqueue_all_requested.connect(
            self.discover_enqueue_all_requested.emit
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
        self.now_view.lyrics_seek_requested.connect(self.seek_requested.emit)
        av = self.artist_view
        av.track_activated.connect(
            lambda t, ctx: self.playlist_picked.emit(list(ctx), list(ctx).index(t))
        )
        av.play_all_requested.connect(self.playlist_picked.emit)
        av.shuffle_requested_sig.connect(
            lambda tracks: self.playlist_picked.emit(list(tracks), 0)
        )
        av.menu_requested.connect(self._track_menu)
        av.album_opened.connect(self.album_opened.emit)
        av.artist_opened.connect(self.artist_opened.emit)

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
        elif name == "discover":
            self.discover_refresh_requested.emit()
        elif name == "search":
            self.search_view._box.setFocus()

    def focus_search(self) -> None:
        self.show_view("search")

    # --- home / library data ---

    def set_home_shelf(self, name: str, tracks: list[Track]) -> None:
        self.home_view.set_shelf(name, tracks)

    def set_top_tracks(self, tracks: list[Track]) -> None:
        self.home_view.set_shelf("Top tracks", list(tracks))

    def show_album_results(self, albums: list[Album]) -> None:
        self.search_view.set_albums(list(albums))

    def open_album(self, album: Album, tracks: list[Track]) -> None:
        self.album_view.set_header(f"💿 {album.title}")
        self.album_view.set_tracks(list(tracks))
        self.stack.setCurrentWidget(self.album_view)
        for key, btn in self._nav.items():
            btn.setChecked(key == "search")   # albums arrive from Search

    def open_artist(self, artist: Artist) -> None:
        """An artist's stage: face, top tracks, releases, kindred acts."""
        self.artist_view.set_artist(artist)
        self.stack.setCurrentWidget(self.artist_view)

    def open_remote_playlist(self, title: str, tracks: list[Track]) -> None:
        """A curated Discover playlist, opened as a full page."""
        self.remote_playlist_view.set_header(f"🎧 {title}")
        self.remote_playlist_view.set_tracks(list(tracks))
        self.stack.setCurrentWidget(self.remote_playlist_view)
        for key, btn in self._nav.items():
            btn.setChecked(key == "discover")   # arrived from Discover

    # --- keyboard shortcuts (text-field safe) ---

    def _install_shortcuts(self) -> None:
        """Window keys: guarded so typing in the search box never triggers them."""
        entry_widgets = (QLineEdit, QTextEdit, QPlainTextEdit)

        def typing() -> bool:
            return isinstance(QApplication.focusWidget(), entry_widgets)

        def bind(chord: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(chord), self)
            shortcut.activated.connect(
                lambda: None if typing() else handler()
            )

        bind("Space", self.play_pause_requested.emit)
        bind("M", self.mute_toggled.emit)
        bind("S", self.shuffle_requested.emit)
        bind("R", self.repeat_requested.emit)
        bind("N", lambda: self.show_view("now"))
        bind("Q", self.toggle_queue)
        bind("/", self.focus_search)

        def seek_by(step_ms: int) -> None:
            self.seek_requested.emit(
                max(0, self.player_bar._seek.value() + step_ms)
            )

        def volume_by(step: int) -> None:
            value = self.player_bar._volume.value() + step
            self.volume_changed.emit(max(0, min(100, value)) / 100.0)

        bind("Right", lambda: seek_by(config.SEEK_STEP_MS))
        bind("Left", lambda: seek_by(-config.SEEK_STEP_MS))
        bind("Up", lambda: volume_by(int(config.VOLUME_STEP * 100)))
        bind("Down", lambda: volume_by(-int(config.VOLUME_STEP * 100)))

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
        artist_page = menu.addAction("🎤 Artist page")
        copy_link = menu.addAction("🔗 Copy YouTube link")
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
        artist_page.triggered.connect(lambda: self.artist_opened.emit(track))
        copy_link.triggered.connect(
            lambda: QApplication.clipboard().setText(
                f"https://www.youtube.com/watch?v={track.video_id}"
            )
        )
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
        row = self._queue_list.row(item)
        kind = item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)
        play_now = None
        move_up = None
        move_down = None
        if kind == "upcoming":
            play_now = menu.addAction("▶ Play now")
            move_up = menu.addAction("↑ Move up")
            move_down = menu.addAction("↓ Move down")
            menu.addSeparator()
            remove = menu.addAction("✕ Remove from queue")
        else:
            remove = menu.addAction("✕ Remove from queue")
            remove.setEnabled(False)   # the playing row isn't in `upcoming`
        chosen = menu.exec(self._queue_list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is play_now:
            self.queue_jump_requested.emit(row - 1)   # upcoming index
        elif chosen is move_up:
            self._queue_swap(row - 1, row - 2)
        elif chosen is move_down:
            self._queue_swap(row - 1, row)
        elif chosen is remove and kind == "upcoming":
            self.queue_remove_requested.emit(row - 1)

    def _queue_jump_from_row(self, row: int) -> None:
        item = self._queue_list.item(row) if row >= 0 else None
        if item is None or item.data(Qt.ItemDataRole.UserRole + 1) != "upcoming":
            return
        self.queue_jump_requested.emit(row - 1)

    def _queue_swap(self, i: int, j: int) -> None:
        """Swap upcoming positions via the reorder signal (engine owns truth)."""
        item_i = self._queue_list.item(i + 1)
        item_j = self._queue_list.item(j + 1)
        if item_i is None or item_j is None:
            return
        order = []
        for row in range(1, self._queue_list.count()):
            track = self._queue_list.item(row).data(Qt.ItemDataRole.UserRole)
            if track is not None:
                order.append(track)
        if 0 <= i < len(order) and 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            self.queue_reorder_requested.emit(order)

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
        self.now_view.set_position(position_ms)

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
