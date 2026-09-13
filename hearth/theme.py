"""
theme.py
Stylesheets compiled from the active Palette at runtime.

One source of truth: widgets never hardcode colors, they re-read these
builders whenever the theme changes.
"""

from __future__ import annotations

from string import Template

from .config import Palette

PANEL_QSS = Template("""
QWidget#HearthShell {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 ${shell_a}, stop:1 ${shell_b});
    border: 1px solid ${line};
    border-radius: 18px;
}
QLabel#RibbonTitle { color: ${text}; font-size: 13px; font-weight: 700; }
QLabel#RibbonArtist { color: ${muted}; font-size: 11px; }
QLabel#StatusChip { color: ${faint}; font-size: 11px; font-style: italic; }
QLabel#SectionLabel { color: ${faint}; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#TimeLabel { color: ${muted}; font-size: 11px; }

QPushButton {
    color: ${text};
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 12px;
}
QPushButton:hover { background: ${raised}; border-color: ${accent_lo}; }
QPushButton:checked { color: ${accent_hi}; border-color: ${accent_lo}; }

QLineEdit#SearchField {
    color: ${text};
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 14px;
    padding: 6px 12px;
    font-size: 12px;
    selection-background-color: ${accent_lo};
}
QLineEdit#SearchField:focus { border-color: ${accent}; }

QListWidget#TrackList {
    color: ${text};
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 12px;
    font-size: 12px;
    outline: none;
}
QListWidget#TrackList::item { padding: 7px 8px; border-radius: 8px; }
QListWidget#TrackList::item:hover { background: ${raised}; }
QListWidget#TrackList::item:selected { background: ${raised}; color: ${accent_hi}; }

QSlider::groove:horizontal {
    height: 4px;
    background: ${raised};
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: ${accent}; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; height: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: ${text};
    border: 2px solid ${accent};
}
QSlider::handle:horizontal:hover { background: ${accent_hi}; }

QMenu {
    color: ${text};
    background: ${surface};
    border: 1px solid ${line};
    border-radius: 10px;
    padding: 6px;
}
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: ${raised}; color: ${accent_hi}; }
""")


def panel_stylesheet() -> str:
    """Compile the panel stylesheet against the live palette."""
    return PANEL_QSS.substitute(
        shell_a=Palette.shell_a, shell_b=Palette.shell_b, line=Palette.line,
        text=Palette.text, muted=Palette.muted, faint=Palette.faint,
        surface=Palette.surface, raised=Palette.raised,
        accent=Palette.accent, accent_hi=Palette.accent_hi, accent_lo=Palette.accent_lo,
    )
