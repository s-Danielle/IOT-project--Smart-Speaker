"""Button behaviour of the controller, run against fake hardware."""

import pytest

import fakes
from core.state import State
from hardware.buttons import ButtonID
from rig import Rig


@pytest.fixture
def rig(monkeypatch):
    return Rig(monkeypatch)


# ---------------------------------------------------------------------------
# A first look at the normal flow (these should pass before and after the fixes)
# ---------------------------------------------------------------------------


def test_tap_loads_the_chip_and_play_starts_it(rig):
    rig.tap_chip("AA")
    assert rig.state == State.IDLE_CHIP_LOADED
    assert rig.audio.calls == []  # a tap alone does not start music
    rig.play()
    assert rig.state == State.PLAYING
    assert rig.audio.names() == ["play_uri"]


def test_short_stop_press_while_playing_keeps_the_chip(rig):
    rig.load_and_play()
    rig.click(ButtonID.STOP)
    assert rig.state == State.IDLE_CHIP_LOADED
    assert rig.controller.device_state.loaded_chip is not None


# ---------------------------------------------------------------------------
# Stop button: a long press must not leave a flag set that eats the next press
# ---------------------------------------------------------------------------


def test_stop_long_press_clears_the_chip_quietly(rig):
    rig.tap_chip("AA")
    rig.press(ButtonID.STOP, held=3.1)
    assert rig.state == State.IDLE_NO_CHIP
    rig.ui.clear()
    rig.release(ButtonID.STOP)
    assert "on_blocked_action" not in rig.ui_calls()  # letting go of the long press is not an error


def test_short_stop_press_after_a_long_press_is_not_ignored(rig):
    rig.tap_chip("AA")
    rig.press(ButtonID.STOP, held=3.1)  # long press: clears the chip
    rig.release(ButtonID.STOP)
    rig.tap_chip("BB")
    assert rig.state == State.IDLE_CHIP_LOADED
    rig.click(ButtonID.STOP)  # a short press clears the chip
    assert rig.state == State.IDLE_NO_CHIP


def test_second_long_stop_press_still_clears_the_chip(rig):
    rig.tap_chip("AA")
    rig.press(ButtonID.STOP, held=3.1)
    rig.release(ButtonID.STOP)
    rig.tap_chip("BB")
    rig.press(ButtonID.STOP, held=3.1)
    assert rig.state == State.IDLE_NO_CHIP


# ---------------------------------------------------------------------------
# Record button: the "saved" chime must not be cut off by a new countdown
# ---------------------------------------------------------------------------


def start_recording(rig):
    rig.tap_chip("AA")
    rig.press(ButtonID.RECORD, held=5.1)  # holding Record for 5 s starts recording
    assert rig.state == State.RECORDING
    rig.release(ButtonID.RECORD)
    assert rig.state == State.RECORDING


def test_saved_chime_is_not_cut_off_while_record_is_still_held(rig):
    start_recording(rig)
    rig.ui._sounds.clear()
    rig.press(ButtonID.RECORD)  # this press saves the recording
    assert rig.state == State.IDLE_CHIP_LOADED
    assert "on_record_saved" in rig.ui_calls()
    rig.buttons.hold(ButtonID.RECORD, 0.5)  # ...and the finger is still down half a second later
    rig.step(3)
    assert "play_record_start" not in rig.ui._sounds.names()


def test_recording_shows_the_red_light(rig):
    # The red recording light was never switched on: nothing called the UI when recording began.
    start_recording(rig)
    assert "on_recording" in rig.ui_calls()


def test_shutdown_switches_the_leds_off(monkeypatch):
    ptt_leds = fakes.CallLog()
    rig = Rig(monkeypatch, ptt_leds=ptt_leds, voice_command=fakes.FakeVoice())
    rig.controller.shutdown()
    assert "shutdown" in rig.ui_calls()  # the speaker light
    assert ("off", 2) in ptt_leds.calls  # the PTT light


def test_record_works_normally_again_after_a_save(rig):
    start_recording(rig)
    rig.press(ButtonID.RECORD)  # save
    rig.release(ButtonID.RECORD)
    rig.ui._sounds.clear()
    rig.press(ButtonID.RECORD, held=0.5)  # a new press counts down again
    assert "play_record_start" in rig.ui._sounds.names()
