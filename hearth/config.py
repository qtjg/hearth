"""Design tokens, tunables, and palettes.

One palette. One source of truth. Every widget reads from here.
"""

from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "Hearth"
APP_TAGLINE = "keep the fire warm"
PLAYLIST_SUFFIX = ".hearthplaylist.json"
ORG_NAME = "hearth"
APP_AUTHOR = "Mayank Bhaskar (qtjg)"
REPO_URL = "https://github.com/qtjg/hearth"

# --- geometry ---
RIBBON_WIDTH = 380
RIBBON_HEIGHT = 68
PANEL_WIDTH = 430
PANEL_HEIGHT = 610
TOAST_WIDTH = 300
TOAST_HEIGHT = 68
TOAST_LIFETIME_MS = 3500

# --- main window (the big stage) ---
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 780
SIDEBAR_WIDTH = 232
PLAYERBAR_HEIGHT = 88
QUEUE_WIDTH = 300
COVER_TILE = 168
ROW_HEIGHT = 52

# Home shelves are seeded from these guest-API searches (fast, no login).
QUICK_PICKS = (
    "today's top hits",
    "chill lofi beats",
    "classic rock anthems",
    "focus flow",
    "late night drive",
    "acoustic mornings",
)

# --- radio / autoplay ---
RADIO_LIMIT = 25          # tracks fetched per Start Radio / autoplay refill
AUTOPLAY_DEFAULT = True   # keep the music alive when the queue runs dry

# --- now playing view ---
NOW_COVER = 240

# --- timing tunables ---
SEARCH_DEBOUNCE_MS = 350
SEEK_POLL_MS = 500
FADE_STEPS = 15
FADE_INTERVAL_MS = 1000  # total sleep-timer fade window (steps * interval)
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.5

# --- audio tunables ---
VOLUME_TARGET_DB = -16.0
MAX_GAIN_DB = 6.0
MIN_GAIN_DB = -6.0
PLAYBACK_RATES = (0.75, 1.0, 1.25, 1.5)

# --- v0.5.0: search scopes, top tracks, shortcuts ---
SEEK_STEP_MS = 10_000        # ←/→ keyboard seek step
VOLUME_STEP = 0.05           # ↑/↓ keyboard volume step
TOP_TRACKS_LIMIT = 8         # home shelf ranking size

# --- v0.6.0: discover (the whole world's music) ---
DISCOVER_PLAYLIST_LIMIT = 300   # max tracks pulled per curated playlist page
DISCOVER_CARD_SIZE = 150        # square thumbnail size of discover shelf cards
WORLD_STATION_LIMIT = 20        # tracks fetched per world-genre station tune-in

# --- v0.6.1: artist spotlight + synced lyrics ---
LRCLIB_URL = "https://lrclib.net/api"   # free, keyless lyrics database
LRCLIB_TIMEOUT = 10                      # seconds per lyrics request
ARTIST_AVATAR = 132                      # artist page avatar size
ARTIST_CARD_SIZE = 132                   # release card size on the artist page

VERSION = "0.6.2"

REPEAT_OFF = "off"
REPEAT_ALL = "all"
REPEAT_ONE = "one"
REPEAT_MODES = (REPEAT_OFF, REPEAT_ALL, REPEAT_ONE)

# --- logging ---
LOG_MAX_BYTES = 2_000_000
LOG_BACKUPS = 3

# --- default hotkeys (app-scope QShortcut chords) ---
DEFAULT_HOTKEYS = {
    "play_pause": "Ctrl+Alt+Space",
    "next_track": "Ctrl+Alt+Right",
    "prev_track": "Ctrl+Alt+Left",
    "toggle_panel": "Ctrl+Alt+E",
    "focus_search": "Ctrl+Alt+F",
}

# System chords that should never be bound in the app.
RESERVED_CHORDS = (
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+A", "Ctrl+S",
    "Ctrl+W", "Ctrl+Q", "Ctrl+T", "Ctrl+N",
    "Alt+F4", "Alt+Tab", "Alt+Space",
    "Meta+L", "Meta+D", "Meta+E", "Meta+R",
)


@dataclass(frozen=True)
class Palette:
    """A hand-tuned color scheme. All values are #rrggbb."""

    key: str
    label: str
    bg: str
    surface: str
    surface_alt: str
    hairline: str
    text: str
    text_dim: str
    accent: str
    accent_soft: str
    danger: str
    success: str
    selection: str
    scroll: str


PALETTES: dict[str, Palette] = {
    "hearthlight": Palette(
        key="hearthlight", label="Hearthlight",
        bg="#14100c", surface="#1d1712", surface_alt="#282017",
        hairline="#3a2f22", text="#f3e9d8", text_dim="#a89880",
        accent="#f0a437", accent_soft="#f6c97e", danger="#e2694f",
        success="#8fbf6f", selection="#4a3517", scroll="#3a2f22",
    ),
    "emberfall": Palette(
        key="emberfall", label="Emberfall",
        bg="#160d0d", surface="#211313", surface_alt="#2e1a1a",
        hairline="#412525", text="#f5e6e0", text_dim="#ab8d86",
        accent="#ef6f4f", accent_soft="#f79d82", danger="#e04a3a",
        success="#9fbf6f", selection="#4a2018", scroll="#412525",
    ),
    "frost": Palette(
        key="frost", label="Frost",
        bg="#0c1216", surface="#121b21", surface_alt="#1a262e",
        hairline="#24343f", text="#e8f1f5", text_dim="#8ba3b0",
        accent="#5fc8e8", accent_soft="#9adcf0", danger="#e2694f",
        success="#7fd0a0", selection="#173a4a", scroll="#24343f",
    ),
    "moss": Palette(
        key="moss", label="Moss",
        bg="#0f130d", surface="#161c12", surface_alt="#1f2819",
        hairline="#2c3a22", text="#eef2e4", text_dim="#9aa889",
        accent="#a3c96a", accent_soft="#c7e09a", danger="#e2694f",
        success="#8fd07a", selection="#2c3d17", scroll="#2c3a22",
    ),
    "orchid": Palette(
        key="orchid", label="Orchid",
        bg="#120f16", surface="#1a1522", surface_alt="#241c30",
        hairline="#342847", text="#f2ecf7", text_dim="#a394b5",
        accent="#c08df0", accent_soft="#dcbcf7", danger="#e2694f",
        success="#8fbf9f", selection="#3a2550", scroll="#342847",
    ),
    "slate": Palette(
        key="slate", label="Slate",
        bg="#101314", surface="#181d1f", surface_alt="#212829",
        hairline="#2e383a", text="#ecf0f0", text_dim="#96a3a3",
        accent="#5fd4c4", accent_soft="#9ae8dc", danger="#e2694f",
        success="#7fd0a0", selection="#1d3c38", scroll="#2e383a",
    ),
    "grove": Palette(
        key="grove", label="Grove",
        bg="#0e1210", surface="#131917", surface_alt="#1a2420",
        hairline="#223029", text="#e8f5ee", text_dim="#93a89d",
        accent="#1db954", accent_soft="#52e08a", danger="#e2694f",
        success="#7fd0a0", selection="#14422a", scroll="#223029",
    ),
}

DEFAULT_PALETTE = "grove"


def get_palette(key: str | None) -> Palette:
    """Look up a palette by key, falling back to the default."""
    return PALETTES.get(key or "", PALETTES[DEFAULT_PALETTE])


def palette_keys() -> tuple[str, ...]:
    return tuple(PALETTES)


def validate_palette(p: Palette) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    errors: list[str] = []
    color_fields = [f for f in p.__dataclass_fields__ if f not in ("key", "label")]
    for name in color_fields:
        value = getattr(p, name)
        if not (isinstance(value, str) and value.startswith("#") and len(value) == 7):
            errors.append(f"{name}: expected #rrggbb, got {value!r}")
    if p.bg == p.text:
        errors.append("bg and text must differ (invisible text)")
    if p.key not in p.key.strip() or not p.key:
        errors.append("key must be non-empty")
    return errors
