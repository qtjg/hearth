"""Tests for the SQLite favorites/history storage layer."""

from __future__ import annotations

from pathlib import Path

from hearth.models import Track
from hearth.storage import HearthStorage


def make_track(vid: str, title: str = "Song", artist: str = "Artist") -> Track:
    return Track(video_id=vid, title=title, artist=artist, duration="3:00")


def test_favorites_crud(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    t = make_track("v1", "Favorite Song")

    assert not store.is_favorite("v1")
    store.add_favorite(t)
    assert store.is_favorite("v1")

    rows = store.get_favorites()
    assert len(rows) == 1
    assert rows[0].title == "Favorite Song"

    store.remove_favorite("v1")
    assert not store.is_favorite("v1")
    assert store.get_favorites() == []


def test_favorite_upsert_refreshes_row(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    store.add_favorite(make_track("v1", "Old Title"))
    store.add_favorite(make_track("v1", "New Title"))
    rows = store.get_favorites()
    assert len(rows) == 1
    assert rows[0].title == "New Title"


def test_favorites_order_newest_first(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    store.add_favorite(make_track("a"))
    store.add_favorite(make_track("b"))
    store.add_favorite(make_track("c"))
    ids = [t.video_id for t in store.get_favorites()]
    assert ids == ["c", "b", "a"]


def test_history_record_and_dedupe(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    store.record_history(make_track("v1", "Played"))
    store.record_history(make_track("v2", "Also Played"))
    store.record_history(make_track("v1", "Played Again"))

    rows = store.get_history()
    assert len(rows) == 2  # one row per unique track
    by_id = {t.video_id: t for t in rows}
    assert by_id["v1"].title == "Played Again"


def test_history_clear(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    store.record_history(make_track("v1"))
    store.clear_history()
    assert store.get_history() == []


def test_bad_inputs_are_noops(tmp_path: Path) -> None:
    store = HearthStorage(tmp_path / "hearth.db")
    store.record_history(None)  # type: ignore[arg-type]
    store.add_favorite(Track(video_id="", title="x", artist="y"))  # empty id ignored
    store.remove_favorite("")
    assert store.get_history() == []
    assert store.get_favorites() == []
