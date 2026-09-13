"""Offscreen UI smoke test: the panel builds, wires, and renders headlessly."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from hearth.catalog import CatalogSource  # noqa: E402
from hearth.models import Track  # noqa: E402
from hearth.panel import FloatingPanel  # noqa: E402
from hearth.player import PlaybackCore  # noqa: E402
from hearth.stream import StreamResolver  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def panel(qapp: QApplication, tmp_path) -> FloatingPanel:
    core = PlaybackCore(CatalogSource(), StreamResolver())
    settings = QSettings("Hearth Audio Test", "Hearth Test")
    settings.clear()
    return FloatingPanel(core, None, settings)


def test_panel_builds_headless(panel: FloatingPanel) -> None:
    assert panel.windowTitle() == "Hearth"
    assert not panel.is_expanded()
    panel._apply_size(True)
    assert panel.is_expanded()
    panel._apply_size(False)
    assert not panel.is_expanded()


def test_panel_render_and_click(panel: FloatingPanel) -> None:
    tracks = [
        Track(video_id="a", title="Alpha", artist="One", duration="3:00"),
        Track(video_id="b", title="Beta", artist="Two", duration="4:00"),
    ]
    panel._render(tracks, active=0)
    assert panel.list.count() == 2

    # Clicking the second row must move the core cursor and queue that track.
    panel.core.adopt(tracks, 0)
    panel._on_row_clicked(panel.list.item(1))
    assert panel.core.current is not None
    assert panel.core.current.video_id == "b"


def test_panel_search_status_and_theme_menu_paths(panel: FloatingPanel) -> None:
    panel._set_status("searching")
    assert panel.status.text() == "searching"

    from hearth.config import Palette

    panel._apply_theme("Forest")
    assert Palette.current_theme == "Forest"
    assert panel.styleSheet()  # stylesheet recompiled against the new palette
