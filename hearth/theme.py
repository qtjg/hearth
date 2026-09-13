"""Stylesheets compiled from Palette tokens via string.Template."""

from __future__ import annotations

from string import Template

from .config import Palette

_STYLESHEET = Template(
    """
QWidget { background: $bg; color: $text; font-size: 13px; }
QLabel { background: transparent; }
QLabel[dim="true"] { color: $text_dim; }
QLabel[header="true"] { font-size: 15px; font-weight: 600; }
QLabel[hero="true"] { font-size: 22px; font-weight: 700; }
QLabel[shelf="true"] {
    font-size: 17px; font-weight: 700; background: transparent;
}

QLineEdit {
    background: $surface_alt; color: $text;
    border: 1px solid $hairline; border-radius: 10px;
    padding: 7px 12px; selection-background-color: $selection;
}
QLineEdit:focus { border: 1px solid $accent; }

QPushButton {
    background: $surface_alt; color: $text;
    border: 1px solid $hairline; border-radius: 9px;
    padding: 6px 12px;
}
QPushButton:hover { border: 1px solid $accent; color: $accent_soft; }
QPushButton:pressed { background: $surface; }
QPushButton[accent="true"] { background: $accent; color: $bg; border: none; font-weight: 600; }
QPushButton[accent="true"]:hover { background: $accent_soft; }
QPushButton[flat="true"] { background: transparent; border: none; color: $text_dim; }
QPushButton[flat="true"]:hover { color: $accent; }
QPushButton[nav="true"] {
    background: transparent; border: none; border-radius: 8px;
    padding: 9px 14px; text-align: left; font-size: 14px; font-weight: 600;
    color: $text_dim;
}
QPushButton[nav="true"]:hover { color: $text; background: $surface; }
QPushButton[nav="true"]:checked { color: $text; background: $surface_alt; }
QPushButton[card="true"] {
    background: $surface; border: 1px solid $hairline; border-radius: 12px;
    padding: 0; text-align: left;
}
QPushButton[card="true"]:hover { border: 1px solid $accent; background: $surface_alt; }

QLabel[tile="true"] {
    background: $surface_alt; border-radius: 10px;
}

QListWidget {
    background: $surface; border: 1px solid $hairline;
    border-radius: 10px; outline: none; padding: 4px;
}
QListWidget::item { border-radius: 8px; padding: 8px; margin: 2px; color: $text; }
QListWidget::item:selected { background: $selection; color: $accent_soft; }
QListWidget::item:hover { background: $surface_alt; }
QListWidget[rows="true"] {
    background: transparent; border: none; border-radius: 0; padding: 0;
}
QListWidget[rows="true"]::item { padding: 4px; margin: 0; border-radius: 8px; }
QListWidget[rows="true"]::item:selected { background: $selection; color: $text; }
QListWidget[sidebar="true"] {
    background: transparent; border: none; padding: 0;
}

QFrame[playerbar="true"] {
    background: $surface; border-top: 1px solid $hairline;
}
QFrame[card="true"] {
    background: $surface; border: 1px solid $hairline; border-radius: 12px;
}
QFrame[sidebar="true"] {
    background: $bg; border-right: 1px solid $hairline;
}

QMenu { background: $surface; border: 1px solid $hairline; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px; border-radius: 7px; }
QMenu::item:selected { background: $selection; color: $accent_soft; }
QMenu::separator { height: 1px; background: $hairline; margin: 5px 8px; }

QSlider::groove:horizontal {
    height: 4px; background: $surface_alt; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; height: 12px; margin: -5px 0;
    background: $accent_soft; border-radius: 6px;
}
QSlider::handle:horizontal:hover { background: $accent; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 3px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 3px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QScrollArea { background: transparent; border: none; }
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: $surface; padding: 8px; border: 1px solid $hairline; }

QToolTip { background: $surface_alt; color: $text; border: 1px solid $hairline; }
"""
)


def build_stylesheet(p: Palette) -> str:
    """Compile the runtime stylesheet from a Palette (strict: missing token = error)."""
    return _STYLESHEET.substitute(
        bg=p.bg, surface=p.surface, surface_alt=p.surface_alt,
        hairline=p.hairline, text=p.text, text_dim=p.text_dim,
        accent=p.accent, accent_soft=p.accent_soft, danger=p.danger,
        success=p.success, selection=p.selection, scroll=p.scroll,
    )
