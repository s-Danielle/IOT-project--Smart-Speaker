"""Starting, resuming and finishing music: one gate for every way in, and failures shown quickly."""

from datetime import datetime

import pytest

import config.paths
import core.controller as controller_module
import fakes
from config.settings import MAX_WAIT_FOR_PLAYBACK
from core.state import State
from hardware.buttons import ButtonID
from rig import NO_LIMITS, Rig


@pytest.fixture
def rig(monkeypatch):
    return Rig(monkeypatch, voice_command=fakes.FakeVoice())


# ---------------------------------------------------------------------------
# Say so quickly when a song cannot start
# ---------------------------------------------------------------------------


def test_a_link_mopidy_refuses_shows_an_error_at_once(rig):
    rig.audio.play_ok = False
    rig.tap_chip("AA")
    rig.play()
    assert rig.state == State.IDLE_CHIP_LOADED  # not "PLAYING"
    assert "on_error" in rig.ui_calls()
    assert rig.controller._play_initiated_time is None  # nothing to wait for
    rig.step(5)
    assert rig.usage_added == []


def test_a_song_that_never_starts_gives_up_after_the_wait(rig):
    rig.audio.confirms = False
    rig.tap_chip("AA")
    rig.play()
    assert rig.state == State.PLAYING  # accepted, now waiting for Mopidy to say "play"
    rig.step()
    assert rig.state == State.PLAYING
    rig.controller._play_initiated_time -= MAX_WAIT_FOR_PLAYBACK + 1  # time passes
    rig.ui.clear()
    rig.step()
    assert rig.state == State.IDLE_CHIP_LOADED
    assert "on_error" in rig.ui_calls()
    assert rig.audio.names()[-1] == "stop"  # it must not start playing later, unannounced
    assert rig.usage_added == []


def test_the_wait_is_short_not_a_minute():
    assert MAX_WAIT_FOR_PLAYBACK <= 30


def test_a_slow_spotify_start_is_not_an_error(rig):
    rig.audio.confirms = False  # Mopidy says "stop" while Spotify loads
    rig.tap_chip("AA")
    rig.play()
    rig.controller._play_initiated_time -= 3.4
    rig.step()
    assert rig.state == State.PLAYING
    rig.audio.playing = True  # now Mopidy says "play"
    rig.step()
    assert rig.controller._playback_confirmed is True
    assert "on_error" not in rig.ui_calls()


def test_a_resume_that_cannot_reach_mopidy_shows_an_error(rig):
    rig.load_and_play()
    rig.play()  # pause
    assert rig.state == State.PAUSED
    rig.audio.resume = lambda: False
    rig.ui.clear()
    rig.play()
    assert rig.state == State.PAUSED
    assert "on_error" in rig.ui_calls()


# ---------------------------------------------------------------------------
# Daily usage counts the time the music really played, nothing else
# ---------------------------------------------------------------------------


def test_usage_starts_when_mopidy_confirms_not_at_the_tap(rig):
    rig.audio.confirms = False
    rig.tap_chip("AA")
    rig.play()
    rig.step(3)  # still loading: nothing counted
    assert rig.controller._playback_time_start is None
    rig.audio.playing = True
    rig.step()  # confirmed: the clock starts
    assert rig.controller._playback_time_start is not None
    rig.controller._playback_time_start -= 30  # 30 s of music go by
    rig.play()  # pause
    assert rig.state == State.PAUSED
    assert rig.usage_added == [30]


def test_pausing_before_the_song_loaded_counts_nothing(rig):
    rig.audio.confirms = False
    rig.tap_chip("AA")
    rig.play()
    rig.play()  # pause while it is still loading
    assert rig.state == State.PAUSED
    assert rig.usage_added == []


def test_usage_is_counted_when_a_new_chip_replaces_the_music(rig):
    rig.load_and_play("AA")
    rig.controller._playback_time_start -= 12
    rig.tap_chip("BB")  # loads another chip and stops the music
    assert rig.usage_added == [12]


def test_usage_is_not_counted_while_the_mic_has_paused_the_music(rig):
    rig.load_and_play()
    rig.controller._playback_time_start -= 10
    rig.mic.owner = "ptt"  # the mic took over: the music is paused
    rig.step()
    assert rig.usage_added == [10]
    rig.mic.owner = None
    rig.step()
    assert rig.controller._playback_time_start is not None  # counting again


# ---------------------------------------------------------------------------
# One gate for every way of starting music
# ---------------------------------------------------------------------------


class FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 3, 12, 0, 0)


PATHS = ["button play", "button resume", "voice play", "voice resume", "latest recording", "easter egg"]


def prepare(rig, path, tmp_path, monkeypatch):
    """Get the speaker ready for one way of starting music. Returns the action that triggers it."""
    rig.tap_chip("AA")
    if path == "button play":
        return rig.play
    if path == "voice play":
        return lambda: rig.say("play")
    if path in ("button resume", "voice resume"):
        rig.play()  # start
        rig.play()  # pause
        assert rig.state == State.PAUSED
        return rig.play if path == "button resume" else (lambda: rig.say("play"))
    if path == "latest recording":
        (tmp_path / "recording_x_20260101_000000.wav").write_bytes(b"RIFF")
        monkeypatch.setattr(config.paths, "RECORDINGS_DIR", str(tmp_path))
        return lambda: rig.press(ButtonID.PLAY_PAUSE, held=2.1)
    if path == "easter egg":
        return lambda: rig.say("easter_despacito")
    raise AssertionError(path)


def started(rig, path):
    """Did the speaker just start (play_uri) or resume (resume) music?"""
    return rig.audio.names()[-1] == ("resume" if "resume" in path else "play_uri")


@pytest.mark.parametrize("path", PATHS)
def test_every_way_of_starting_music_works_when_nothing_blocks_it(rig, monkeypatch, tmp_path, path):
    trigger = prepare(rig, path, tmp_path, monkeypatch)
    trigger()
    assert rig.state == State.PLAYING
    assert started(rig, path)


@pytest.mark.parametrize("path", PATHS)
def test_quiet_hours_block_every_way_of_starting_music(rig, monkeypatch, tmp_path, path):
    trigger = prepare(rig, path, tmp_path, monkeypatch)
    monkeypatch.setattr(controller_module, "datetime", FixedNow)
    rig.parental = {**NO_LIMITS, "enabled": True, "quiet_hours": {"enabled": True, "start": "11:00", "end": "13:00"}}
    calls_before = list(rig.audio.calls)
    state_before = rig.state
    rig.ui.clear()
    trigger()
    assert rig.audio.calls == calls_before
    assert rig.state == state_before
    assert "on_blocked_action" in rig.ui_calls()


@pytest.mark.parametrize("path", PATHS)
def test_the_daily_limit_blocks_every_way_of_starting_music(rig, monkeypatch, tmp_path, path):
    trigger = prepare(rig, path, tmp_path, monkeypatch)
    rig.parental = {**NO_LIMITS, "enabled": True, "daily_limit_minutes": 5}
    rig.usage_today = 600  # ten minutes used
    calls_before = list(rig.audio.calls)
    state_before = rig.state
    rig.ui.clear()
    trigger()
    assert rig.audio.calls == calls_before
    assert rig.state == state_before
    assert "on_blocked_action" in rig.ui_calls()


@pytest.mark.parametrize("path", PATHS)
def test_the_volume_cap_holds_for_every_way_of_starting_music(rig, monkeypatch, tmp_path, path):
    trigger = prepare(rig, path, tmp_path, monkeypatch)
    rig.parental = {**NO_LIMITS, "enabled": True, "volume_limit": 30}
    rig.mixer.volume = 60
    trigger()
    assert rig.state == State.PLAYING
    assert rig.mixer.volume == 30


def test_a_blocked_easter_egg_does_not_stop_the_music_that_is_playing(rig, monkeypatch):
    rig.load_and_play()
    monkeypatch.setattr(controller_module, "datetime", FixedNow)
    rig.parental = {**NO_LIMITS, "enabled": True, "quiet_hours": {"enabled": True, "start": "11:00", "end": "13:00"}}
    rig.say("easter_despacito")
    assert rig.state == State.PLAYING
    assert rig.audio.names().count("stop") == 0


def test_an_easter_egg_that_cannot_start_returns_to_idle(rig):
    rig.load_and_play()
    rig.audio.play_ok = False
    rig.say("easter_despacito")
    assert rig.state == State.IDLE_CHIP_LOADED
    assert "on_error" in rig.ui_calls()
