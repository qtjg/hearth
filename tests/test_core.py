"""Tests for palette, utilities, catalogue parsing, and stream ranking."""

from __future__ import annotations

from hearth.catalog import artist_line, artwork_url, build_track, with_retry
from hearth.config import REPEAT_MODES, Palette
from hearth.player import clamp_rate, next_repeat_mode
from hearth.stream import is_permanent_failure, rank_format
from hearth.utils import clock, looks_like_link, pretty_count


# ---------------------------------------------------------------------- utils
def test_clock_formats() -> None:
    assert clock(0) == "0:00"
    assert clock(65_000) == "1:05"
    assert clock(3_600_000) == "1:00:00"
    assert clock(-5) == "0:00"


def test_pretty_count() -> None:
    assert pretty_count(1, "track") == "1 track"
    assert pretty_count(12, "track") == "12 tracks"
    assert pretty_count(2, "goose", "geese") == "2 geese"


def test_looks_like_link() -> None:
    assert looks_like_link("https://youtu.be/abc")
    assert looks_like_link("http://youtube.com/watch?v=x")
    assert looks_like_link("  https://music.youtube.com/watch?v=x  ")
    assert not looks_like_link("midnight city m83")
    assert not looks_like_link("")


# -------------------------------------------------------------------- palette
def test_palette_themes_complete() -> None:
    required = {"void", "shell_a", "shell_b", "surface", "raised", "line",
                "text", "muted", "faint", "accent", "accent_hi", "accent_lo",
                "clay", "sage", "ink"}
    for name, tokens in Palette.THEMES.items():
        assert set(tokens) == required, f"theme {name} token mismatch"


def test_palette_apply_and_revert() -> None:
    original = Palette.current_theme
    Palette.apply_theme("Forest")
    assert Palette.current_theme == "Forest"
    assert Palette.accent == Palette.THEMES["Forest"]["accent"]
    Palette.apply_theme("nonexistent")
    assert Palette.current_theme == "Forest"  # unknown names ignored
    Palette.apply_theme(original)


# -------------------------------------------------------------------- catalog
def test_artist_line_shapes() -> None:
    assert artist_line({"artists": [{"name": "M83"}]}) == "M83"
    assert artist_line({"artists": [{"name": "A"}, {"name": "B"}]}) == "A, B"
    assert artist_line({"author": {"name": "Channel"}}) == "Channel"
    assert artist_line({"artists": "Plain String"}) == "Plain String"
    assert artist_line({}) == "unknown artist"


def test_artwork_url_picks_largest() -> None:
    item = {"thumbnails": [
        {"url": "small.jpg", "width": 60, "height": 60},
        {"url": "big.jpg", "width": 544, "height": 544},
        {"url": "mid.jpg", "width": 168, "height": 168},
    ]}
    assert artwork_url(item) == "big.jpg"
    assert artwork_url({}) == ""


def test_build_track_valid_and_invalid() -> None:
    track = build_track({"videoId": "v1", "title": "T", "artists": [{"name": "A"}]})
    assert track is not None and track.video_id == "v1"
    assert build_track({"title": "no id"}) is None
    assert build_track("not a dict") is None


def test_with_retry_backoff() -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("drop")
        return "ok"

    assert with_retry(flaky, max_attempts=3, base_delay=0.01) == "ok"
    assert calls == 3


# --------------------------------------------------------------------- stream
def test_rank_format_prefers_aac_then_webm_last() -> None:
    m4a = {"ext": "m4a", "acodec": "mp4a.40.2", "abr": 128}
    opus = {"ext": "webm", "acodec": "opus", "abr": 160}
    other = {"ext": "ts", "acodec": "mp4a.40.5", "abr": 96}
    ranked = sorted([opus, other, m4a], key=rank_format)
    assert [f["ext"] for f in ranked] == ["m4a", "ts", "webm"]


def test_rank_format_higher_bitrate_wins_within_class() -> None:
    low = {"ext": "m4a", "acodec": "mp4a", "abr": 70}
    high = {"ext": "m4a", "acodec": "mp4a", "abr": 160}
    ranked = sorted([low, high], key=rank_format)
    assert ranked[0]["abr"] == 160


def test_permanent_failure_markers() -> None:
    assert is_permanent_failure(RuntimeError("Sign in to confirm your age"))
    assert is_permanent_failure(RuntimeError("Video unavailable"))
    assert not is_permanent_failure(RuntimeError("HTTP 503 temporarily"))


# --------------------------------------------------------------------- player
def test_clamp_rate() -> None:
    assert clamp_rate(1.25) == 1.25
    assert clamp_rate(99) == 2.5
    assert clamp_rate(0.1) == 0.5
    assert clamp_rate("garbage") == 1.0
    assert clamp_rate(float("nan")) == 1.0


def test_next_repeat_mode_cycles() -> None:
    assert next_repeat_mode("off") == "all"
    assert next_repeat_mode("all") == "one"
    assert next_repeat_mode("one") == "off"
    assert next_repeat_mode("junk") == "off"


def test_repeat_modes_constant() -> None:
    assert REPEAT_MODES == ("off", "all", "one")
