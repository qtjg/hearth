"""App-level smoke test: full wiring headless, settings persistence roundtrip."""

from hearth import config
from hearth.app import Hearth


def make_hearth(tmp_path) -> Hearth:
    return Hearth(
        argv=["hearth-test"],
        settings_path=str(tmp_path / "settings.ini"),
        data_directory=tmp_path / "data",
        single_instance=False,
        enable_streaming=False,  # keep pool jobs out of unit tests
    )


def test_app_boots_all_components(tmp_path, qapp):
    hearth = make_hearth(tmp_path)
    assert hearth.core is not None
    assert hearth.panel is not None
    assert hearth.toast is not None
    assert hearth.store is not None
    hearth.shutdown()


def test_settings_persist_volume_repeat_rate(tmp_path, qapp):
    hearth = make_hearth(tmp_path)
    hearth.core.set_volume(0.55)
    hearth.core.set_repeat(config.REPEAT_ONE)
    hearth.core.set_rate(1.25)
    hearth.shutdown()

    reopened = make_hearth(tmp_path)
    assert reopened.core.volume == 0.55
    assert reopened.core.engine.repeat == config.REPEAT_ONE
    assert reopened.core.rate == 1.25
    reopened.shutdown()


def test_pick_track_writes_history_and_updates_panel(tmp_path, qapp):
    hearth = make_hearth(tmp_path)
    from .test_models import make_track

    hearth._pick_track(make_track())
    assert len(hearth.store.history()) == 1
    assert hearth.panel._title.text() != "Hearth — nothing playing yet"
    hearth.shutdown()
