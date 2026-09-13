"""Queue engine: history, shuffle, repeat — the pure heart of playback."""

import random

import pytest

from hearth import config
from hearth.models import Track
from hearth.player import PlaybackCore, QueueEngine

from .test_models import make_track


def tracks(n) -> list[Track]:
    return [make_track(video_id=f"t{i}", title=f"Song {i}") for i in range(n)]


def test_start_queue():
    eng = QueueEngine()
    first = eng.start_queue(tracks(3), start=0)
    assert first is not None and first.video_id == "t0"
    assert [t.video_id for t in eng.upcoming] == ["t1", "t2"]


def test_start_queue_invalid_index():
    eng = QueueEngine()
    assert eng.start_queue(tracks(3), start=9) is None
    assert eng.start_queue([], start=0) is None


def test_play_now_moves_current_to_history():
    eng = QueueEngine()
    eng.start_queue(tracks(2))
    extra = make_track(video_id="extra")
    eng.play_now(extra)
    assert eng.current.video_id == "extra"
    assert eng.history[-1].video_id == "t0"


def test_advance_walks_queue_and_history_grows():
    eng = QueueEngine()
    eng.start_queue(tracks(3))
    second = eng.advance()
    assert second.video_id == "t1"
    third = eng.advance()
    assert third.video_id == "t2"
    assert eng.history[-1].video_id == "t1"


def test_advance_empty_returns_none():
    eng = QueueEngine()
    assert eng.advance() is None


def test_repeat_all_wraps_history():
    eng = QueueEngine()
    eng.repeat = config.REPEAT_ALL
    eng.start_queue(tracks(2))
    eng.advance()   # t1
    wrapped = eng.advance()
    assert wrapped is not None and wrapped.video_id == "t0"


def test_repeat_one_sticks():
    eng = QueueEngine()
    eng.repeat = config.REPEAT_ONE
    eng.start_queue(tracks(2))
    again = eng.advance()
    assert again.video_id == "t0"
    assert eng.upcoming[0].video_id == "t1"


def test_go_back_restores_history():
    eng = QueueEngine()
    eng.start_queue(tracks(3))
    eng.advance()
    back = eng.go_back()
    assert back.video_id == "t0"
    assert eng.upcoming[0].video_id == "t1"


def test_go_back_at_start_is_noop():
    eng = QueueEngine()
    eng.start_queue(tracks(2))
    assert eng.go_back().video_id == "t0"


def test_shuffle_preserves_history_and_multiset():
    eng = QueueEngine(rng=random.Random(42))
    eng.start_queue(tracks(8))
    eng.advance()
    history_ids = [t.video_id for t in eng.history]
    eng.shuffle()
    upcoming_ids = [t.video_id for t in eng.upcoming]
    # Shuffling never yanks playback: history untouched, current keeps
    # playing, and the upcoming multiset is exactly the remaining queue.
    assert len(upcoming_ids) == 6
    assert history_ids == [t.video_id for t in eng.history]
    assert eng.current.video_id == "t1"
    assert set(upcoming_ids) == {f"t{i}" for i in range(2, 8)}


def test_peek_next_respects_repeat_one():
    eng = QueueEngine()
    eng.start_queue(tracks(2))
    assert eng.peek_next().video_id == "t1"
    eng.repeat = config.REPEAT_ONE
    assert eng.peek_next().video_id == "t0"


# --- PlaybackCore: signals and settings without touching audio backend ---

@pytest.fixture()
def core(qapp):
    return PlaybackCore()


def test_repeat_cycle_order(core):
    core.set_repeat(config.REPEAT_OFF)
    assert core.cycle_repeat() == config.REPEAT_ALL
    assert core.cycle_repeat() == config.REPEAT_ONE
    assert core.cycle_repeat() == config.REPEAT_OFF


def test_set_repeat_rejects_unknown(core):
    core.set_repeat("banana")
    assert core.engine.repeat == config.REPEAT_OFF


def test_rate_clamped_and_signaled(core):
    seen = []
    core.rate_changed.connect(seen.append)
    core.set_rate(99.0)
    assert seen[-1] == 2.5
    core.set_rate(0.1)
    assert seen[-1] == 0.5


def test_next_rate_cycles(core):
    core.set_rate(1.0)
    assert core.next_rate() == 1.25
    assert core.next_rate() == 1.5
    assert core.next_rate() == 0.75


def test_volume_roundtrip(core):
    core.set_volume(1.7)
    assert core.volume == 1.0
    core.set_volume(-1)
    assert core.volume == 0.0


def test_track_changed_signal(core):
    seen = []
    core.track_changed.connect(seen.append)
    core.play_track(make_track())
    assert len(seen) == 1
    assert core.engine.current.video_id == "dQw4w9WgXcQ"
