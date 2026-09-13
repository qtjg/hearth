"""Tests for the Track dataclass and serialization."""

from __future__ import annotations

from hearth.models import Track


def test_track_properties() -> None:
    track = Track(
        video_id="xyz123",
        title="Midnight City",
        artist="M83",
        duration="4:04",
        artwork_url="https://example.com/art.jpg",
    )
    assert track.key == "xyz123"
    assert track.byline == "M83"
    assert str(track) == "Midnight City — M83"


def test_track_byline_fallback() -> None:
    track = Track(video_id="abc999", title="No Artist Track", artist="")
    assert track.byline == "unknown artist"


def test_track_identity() -> None:
    a = Track(video_id="id1", title="Title 1", artist="Artist 1")
    b = Track(video_id="id1", title="Title 2", artist="Artist 2")
    c = Track(video_id="id2", title="Title 1", artist="Artist 1")
    assert a.is_same_as(b)
    assert not a.is_same_as(c)
    assert not a.is_same_as(None)


def test_track_roundtrip() -> None:
    track = Track(video_id="t1", title="T", artist="A", duration="3:30", artwork_url="http://a.png")
    restored = Track.from_dict(track.to_dict())
    assert restored.is_same_as(track)
    assert restored.duration == "3:30"


def test_track_from_bad_input() -> None:
    for bad in (None, {}, "nope", 42):
        track = Track.from_dict(bad)  # type: ignore[arg-type]
        assert track.video_id == ""
        assert track.title == "untitled"
        assert track.byline == "unknown artist"
