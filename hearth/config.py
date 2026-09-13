"""
config.py
Branding, palette, geometry and tunables for Hearth.

Everything visual lives here so the theme can be re-tuned in one place
without touching layout logic.
"""

from __future__ import annotations

from typing import Dict

APP_NAME = "Hearth"
APP_TAGLINE = "warm listening, everywhere"
ORG_NAME = "Hearth Audio"
APP_ID = "hearth.desktop.companion"
VERSION = "0.1.0"

# ---------------------------------------------------------------- geometry
PANEL_WIDTH = 380
RIBBON_HEIGHT = 64
EXPANDED_HEIGHT = 540
ART_RIBBON = 40
SHELL_MARGIN = 12

# ---------------------------------------------------------------- behaviour
RADIO_DEPTH = 25
SEARCH_DEPTH = 12
DEFAULT_VOLUME = 78
SEEK_MS_BACKSTEP = 3500   # "previous" restarts the track past this point
SEARCH_DEBOUNCE_MS = 350
ANIM_MS = 200
ARTWORK_CACHE_LIMIT = 64
HISTORY_LIMIT = 300

RATE_STEPS = [1.0, 1.25, 1.5, 0.75]
MIN_RATE = 0.5
MAX_RATE = 2.5

# ---------------------------------------------------------------- settings keys
SETTINGS_POS_X = "window/x"
SETTINGS_POS_Y = "window/y"
SETTINGS_EXPANDED = "window/expanded"
SETTINGS_VOLUME = "audio/volume"
SETTINGS_RATE = "audio/rate"
SETTINGS_REPEAT = "playback/repeat"
SETTINGS_ENDLESS = "queue/endless"
SETTINGS_THEME = "ui/theme"

REPEAT_MODES = ("off", "all", "one")


class Palette:
    """Warm hearthlight palette. Charred base, ember accent, cream type.

    The active theme is applied onto this class so every stylesheet and
    widget reads one source of truth at runtime.
    """

    current_theme: str = "Ember"

    void = "#17120E"
    shell_a = "#241A12"
    shell_b = "#1B130C"
    surface = "#2B2016"
    raised = "#38281A"
    line = "#4A3524"

    text = "#F7EDE2"
    muted = "#C4A78E"
    faint = "#96795F"

    accent = "#FF9E57"
    accent_hi = "#FFBE85"
    accent_lo = "#D97A32"

    clay = "#E08D75"
    sage = "#A8C6A1"
    ink = "#2A1708"

    THEMES: Dict[str, Dict[str, str]] = {
        "Ember": {
            "void": "#17120E", "shell_a": "#241A12", "shell_b": "#1B130C",
            "surface": "#2B2016", "raised": "#38281A", "line": "#4A3524",
            "text": "#F7EDE2", "muted": "#C4A78E", "faint": "#96795F",
            "accent": "#FF9E57", "accent_hi": "#FFBE85", "accent_lo": "#D97A32",
            "clay": "#E08D75", "sage": "#A8C6A1", "ink": "#2A1708",
        },
        "Forest": {
            "void": "#0F1510", "shell_a": "#18231A", "shell_b": "#0C120E",
            "surface": "#1C2B20", "raised": "#263A2B", "line": "#31493A",
            "text": "#EAF4EA", "muted": "#9DB8A0", "faint": "#6C8471",
            "accent": "#7BC98A", "accent_hi": "#A5DFB0", "accent_lo": "#4FA161",
            "clay": "#D98F72", "sage": "#A8C6A1", "ink": "#0B1F10",
        },
        "Orchid": {
            "void": "#140F1A", "shell_a": "#201831", "shell_b": "#100C18",
            "surface": "#291E3E", "raised": "#342550", "line": "#443168",
            "text": "#F2ECFA", "muted": "#AC9CC4", "faint": "#7C6C96",
            "accent": "#B98BE8", "accent_hi": "#D3B0F5", "accent_lo": "#9161C7",
            "clay": "#E08DA8", "sage": "#93A6DB", "ink": "#1B0D2C",
        },
    }

    @classmethod
    def apply_theme(cls, theme_name: str) -> None:
        """Apply a preset onto the class tokens (single source of truth)."""
        if theme_name not in cls.THEMES:
            return
        cls.current_theme = theme_name
        for key, value in cls.THEMES[theme_name].items():
            setattr(cls, key, value)

    @classmethod
    def list_themes(cls) -> list[str]:
        """Available preset names in menu order."""
        return list(cls.THEMES.keys())
