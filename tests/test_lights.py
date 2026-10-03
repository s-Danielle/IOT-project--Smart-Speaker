"""The speaker light must come back to the colour of the current state after every flash."""

import types

import pytest

from hardware.leds import Colors
from ui.lights import Lights


class FakeLeds:
    def __init__(self):
        self.calls = []  # (light, colour)

    def set_light(self, light, color):
        self.calls.append((light, color))

    def off(self, light):
        self.calls.append((light, Colors.OFF))

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def lights(monkeypatch):
    # run the flashes right away instead of on a thread, and do not really wait
    monkeypatch.setattr(Lights, "_run_in_background", staticmethod(lambda work: work()))
    monkeypatch.setattr("ui.lights.time", types.SimpleNamespace(sleep=lambda seconds: None))
    leds = FakeLeds()
    lights = Lights(leds=leds)
    lights.leds = leds
    return lights


def test_a_volume_flash_during_playback_goes_back_to_green(lights):
    # It used to switch the light off, so the speaker looked dead while music played.
    lights.show_playing()
    lights.show_volume(60)
    assert lights.leds.last == (3, Colors.GREEN)


def test_an_error_flash_goes_back_to_the_state_colour(lights):
    lights.show_playing()
    lights.show_error()
    assert lights.leds.last == (3, Colors.GREEN)
    lights.show_paused()
    lights.show_error()
    assert lights.leds.last == (3, Colors.BLUE)


def test_the_saved_flash_ends_blue_not_red_and_not_dark(lights):
    lights.show_recording()
    assert lights.leds.last == (3, Colors.RED)
    lights.show_success()
    assert (3, Colors.GREEN) in lights.leds.calls  # the green flash
    assert lights.leds.last == (3, Colors.BLUE)


def test_a_chip_scan_flashes_green_then_idle_blue(lights):
    lights.show_chip_loaded()
    assert lights.leds.calls == [(3, Colors.GREEN), (3, Colors.BLUE)]


def test_a_flash_while_recording_goes_back_to_red(lights):
    lights.show_recording()
    lights.show_volume(10)
    assert lights.leds.last == (3, Colors.RED)


def test_before_anything_has_happened_a_flash_ends_dark(lights):
    lights.show_volume(10)
    assert lights.leds.last == (3, Colors.OFF)


def test_off_stays_off_after_later_flashes(lights):
    lights.show_playing()
    lights.off()
    lights.show_volume(10)
    assert lights.leds.last == (3, Colors.OFF)


def test_only_the_speaker_light_is_touched(lights):
    lights.show_playing()
    lights.show_error()
    assert {light for light, _ in lights.leds.calls} == {3}
