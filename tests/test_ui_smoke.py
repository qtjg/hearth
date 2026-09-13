"""Smoke tests: the real UI builds and repaints headless (offscreen)."""

import pytest

from hearth.config import get_palette
from hearth.panel import EqBars, FloatingPanel, SpringPhysics
from hearth.theme import build_stylesheet
from hearth.toast import NowPlayingToast
from hearth.tray import InstanceGuard, hearth_mark, paint_icon

from .test_models import make_track


def test_stylesheet_has_every_token():
    sheet = build_stylesheet(get_palette("hearthlight"))
    assert "#f0a437" in sheet   # accent lands in the compiled CSS
    assert "$" not in sheet     # strict substitution: no token left behind


def test_spring_physics_stays_clamped():
    physics = SpringPhysics(bars=4)
    physics.impulse(5.0)
    for _ in range(200):
        values = physics.step(0.05)
        assert all(0.05 <= v <= 1.0 for v in values)


def test_spring_physics_decays():
    physics = SpringPhysics()
    physics.impulse(4.0)
    peak = 0.0
    for _ in range(60):
        peak = max(peak, max(physics.step(0.05)))
    late = max(physics.step(0.05))
    # transients decay: the impulse spike never comes back
    assert peak > late
    for _ in range(120):
        values = physics.step(0.05)
    settled = sum(values)
    # steady state: bars come to rest at their targets
    assert abs(settled - sum(physics.step(0.05))) < 1e-4


def test_panel_builds_and_toggles(qapp):
    panel = FloatingPanel("frost")
    assert not panel.expanded
    panel.setExpanded()
    assert panel.expanded
    panel.setCompact()
    assert not panel.expanded


def test_panel_track_and_state(qapp):
    panel = FloatingPanel("moss")
    panel.set_track(make_track())
    panel.set_playing(True)
    assert panel._btn_play.text() == "⏸"
    panel.set_playing(False)
    assert panel._btn_play.text() == "▶"
    panel.set_track(None)
    assert "nothing playing" in panel._title.text()


def test_panel_results_and_pick_signal(qapp):
    panel = FloatingPanel("slate")
    seen = []
    panel.track_picked.connect(seen.append)
    panel.show_results([make_track(video_id="aaa"), make_track(video_id="bbb")])
    assert len(panel.current_results) == 2
    panel._on_result_clicked(panel._results.item(0))
    assert seen[0].video_id == "aaa"


def test_panel_search_debounce_emits(qapp):
    panel = FloatingPanel("orchid")
    seen = []
    panel.search_submitted.connect(seen.append)
    panel._search.setText("daft punk")
    panel._emit_search()
    assert seen == ["daft punk"]


def test_toast_builds_and_announces(qapp):
    toast = NowPlayingToast("emberfall")
    toast.announce(make_track())
    assert "▶" in toast._sub.text()


def test_paint_icon_returns_icon(qapp):
    icon = paint_icon()
    assert not icon.isNull()


def test_hearth_mark_returns_icon(qapp):
    icon = hearth_mark()
    assert not icon.isNull()


def test_hearth_mark_with_explicit_palette(qapp):
    # Regression: the mark must read colors off a palette *instance*,
    # never off the Palette class (NameError/AttributeError guard).
    icon = hearth_mark(get_palette("frost"))
    assert not icon.isNull()


def test_instance_guard_property(qapp, tmp_path):
    # With single_instance server disabled elsewhere, constructing a guard
    # here must at least be coherent about primary status.
    guard = InstanceGuard()
    assert isinstance(guard.is_primary, bool)
    if guard.server is not None:
        guard.server.close()
