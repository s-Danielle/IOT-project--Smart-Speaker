"""The LEDs: several programs drive them at once and must not wipe each other's lights."""

import pytest

import fakes
from hardware.leds import Colors, RGBLeds

LED_CHIP = 0x21
BUTTON_CHIP = 0x20


@pytest.fixture(autouse=True)
def shared_state_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAKER_LED_STATE", str(tmp_path / "leds.json"))


def led_byte():
    return fakes.FakeSMBus.values[LED_CHIP]


def button_byte():
    return fakes.FakeSMBus.values[BUTTON_CHIP]


# Light 1: P0 B, P1 G, P2 R.  Light 2: P3 B, P4 G, P5 R.  Light 3: P6 B and P7 G on 0x21, P6 R on 0x20.
LIGHT1_GREEN = 1 << 1
LIGHT2_RED = 1 << 5
LIGHT3_BLUE = 1 << 6


def test_one_program_does_not_wipe_the_lights_of_another():
    # The controller, its PTT light and the health monitor each make their own RGBLeds.
    # Each used to keep its own copy of the pins, so every write reset the other lights.
    health, ptt, speaker = RGBLeds(), RGBLeds(), RGBLeds()
    health.set_light(1, Colors.GREEN)
    speaker.set_light(3, Colors.BLUE)
    ptt.set_light(2, Colors.RED)
    assert led_byte() == LIGHT1_GREEN | LIGHT2_RED | LIGHT3_BLUE


def test_the_health_monitor_rewriting_its_light_keeps_the_others():
    health, speaker = RGBLeds(), RGBLeds()
    speaker.set_light(3, Colors.GREEN)  # Light 3 green: P7
    health.set_light(1, Colors.RED)
    health.set_light(1, Colors.BLUE)
    health.off(1)
    assert led_byte() == 1 << 7


def test_a_program_that_starts_later_keeps_what_is_already_lit():
    RGBLeds().set_light(1, Colors.GREEN)
    controller = RGBLeds()  # e.g. the controller restarts while the health monitor keeps running
    controller.set_light(2, Colors.BLUE)
    assert led_byte() == LIGHT1_GREEN | (1 << 3)


def test_the_first_start_after_boot_switches_every_led_off():
    # The chips power up with every pin high, which would light every LED.
    fakes.FakeSMBus.values = {LED_CHIP: 0xFF, BUTTON_CHIP: 0xFF}
    RGBLeds()
    assert led_byte() == 0x00
    assert button_byte() == 0x3F


def test_starting_another_program_does_not_touch_the_chips_again():
    first = RGBLeds()
    first.set_light(1, Colors.GREEN)
    writes_before = sum(len(bus.writes) for bus in fakes.FakeSMBus.instances)
    RGBLeds()
    # the new program only re-sends the current state to the LED chip (harmless), never to the buttons
    new_writes = [w for bus in fakes.FakeSMBus.instances for w in bus.writes][writes_before:]
    assert all(address == LED_CHIP and value == LIGHT1_GREEN for address, value in new_writes)


def test_a_button_held_at_startup_does_not_get_stuck_pressed():
    # 0x20 reads 0xFE when button 0 is held. The old code read that and wrote it back, which kept
    # the pin pulled low, so the button read as pressed until the next reboot.
    fakes.FakeSMBus.values = {BUTTON_CHIP: 0xFE}
    leds = RGBLeds()
    leds.set_light(3, Colors.RED)
    assert button_byte() == 0x3F | (1 << 6)  # all button pins high, only Light 3's red pin on


def test_button_pins_always_stay_high():
    leds = RGBLeds()
    for color in (Colors.RED, Colors.OFF, Colors.YELLOW, Colors.BLUE):
        leds.set_light(3, color)
        assert button_byte() & 0x3F == 0x3F


def test_light_3_uses_its_three_pins_across_two_chips():
    leds = RGBLeds()
    leds.set_light(3, Colors.RED)
    assert button_byte() & (1 << 6) and led_byte() & (1 << 6) == 0 and led_byte() & (1 << 7) == 0
    leds.set_light(3, Colors.YELLOW)  # red + green
    assert button_byte() & (1 << 6) and led_byte() & (1 << 7) and led_byte() & (1 << 6) == 0
    leds.set_light(3, Colors.BLUE)
    assert button_byte() & (1 << 6) == 0 and led_byte() & (1 << 6) and led_byte() & (1 << 7) == 0


def test_off_all_switches_every_light_off():
    leds = RGBLeds()
    leds.set_light(1, Colors.GREEN)
    leds.set_light(2, Colors.RED)
    leds.set_light(3, Colors.RED)
    leds.off_all()
    assert led_byte() == 0x00
    assert button_byte() == 0x3F


def test_write_errors_are_logged_rarely_not_four_times_a_second(monkeypatch):
    messages = []
    monkeypatch.setattr("hardware.leds.log", messages.append)
    leds = RGBLeds()
    fakes.FakeSMBus.fail = True
    for _ in range(50):
        leds.set_light(1, Colors.GREEN)
    assert len([m for m in messages if "Write error" in m]) == 1


def test_leds_still_work_if_the_shared_file_cannot_be_used(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAKER_LED_STATE", str(tmp_path / "no" / "such" / "folder" / "leds.json"))
    leds = RGBLeds()
    leds.set_light(1, Colors.GREEN)
    leds.set_light(2, Colors.RED)
    assert led_byte() == LIGHT1_GREEN | LIGHT2_RED  # this program's own lights still add up


def test_leds_are_disabled_quietly_without_the_bus(monkeypatch):
    def no_bus(_bus):
        raise OSError("no such device")

    monkeypatch.setattr("hardware.leds.SMBus", no_bus)
    leds = RGBLeds()
    leds.set_light(1, Colors.GREEN)  # nothing happens, and nothing crashes
    leds.off_all()
