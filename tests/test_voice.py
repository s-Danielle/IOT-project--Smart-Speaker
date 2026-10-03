"""Voice commands: a bounded wait for the speech service, and the controller stays responsive."""

import sys
import threading
import time
import types

import pytest

import core.controller as controller_module
import fakes
from core.state import State
from hardware.buttons import ButtonID
from hardware.leds import Colors
from hardware.speech_recognition_wrapper import SpeechRecognitionWrapper
from hardware.voice_command import VoiceCommand
from rig import Rig


# ---------------------------------------------------------------------------
# The speech service: never wait for it for long
# ---------------------------------------------------------------------------


def install_fake_speech_library(monkeypatch, recognize):
    """Put a fake `speech_recognition` in place. `recognize()` plays the web service."""
    library = types.ModuleType("speech_recognition")

    class Recognizer:
        operation_timeout = None

        def record(self, source):
            return b"audio"

        def recognize_google(self, audio):
            return recognize()

    class AudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    library.Recognizer = Recognizer
    library.AudioFile = AudioFile
    monkeypatch.setitem(sys.modules, "speech_recognition", library)


PCM = b"\x00\x00" * 16000  # one second of silence


def test_a_hanging_speech_service_cannot_freeze_the_controller(monkeypatch):
    # With no internet the request used to block for minutes, and the buttons were dead meanwhile.
    stuck = threading.Event()
    install_fake_speech_library(monkeypatch, lambda: stuck.wait(30))
    started = time.monotonic()
    try:
        assert SpeechRecognitionWrapper().transcribe(PCM, timeout=0.3) is None
    finally:
        stuck.set()
    assert time.monotonic() - started < 3


def test_the_default_wait_is_short():
    from config.settings import PTT_TRANSCRIBE_TIMEOUT

    assert PTT_TRANSCRIBE_TIMEOUT <= 15


def test_the_library_is_told_the_same_time_limit(monkeypatch):
    seen = {}
    install_fake_speech_library(monkeypatch, lambda: "hi speaker play")
    wrapper = SpeechRecognitionWrapper()
    wrapper.transcribe(PCM, timeout=4.0)
    seen["timeout"] = wrapper._recognizer.operation_timeout
    assert seen["timeout"] == 4.0


def test_a_normal_answer_comes_back_lowercase(monkeypatch):
    install_fake_speech_library(monkeypatch, lambda: "Hi Speaker Play")
    assert SpeechRecognitionWrapper().transcribe(PCM, timeout=2) == "hi speaker play"


def test_a_service_error_gives_nothing_instead_of_crashing(monkeypatch):
    class UnknownValueError(Exception):
        pass

    def fail():
        raise UnknownValueError()

    install_fake_speech_library(monkeypatch, fail)
    assert SpeechRecognitionWrapper().transcribe(PCM, timeout=2) is None


# ---------------------------------------------------------------------------
# What the speaker understands (these must keep working, the reboot joke included)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("hi speaker play", "play"),
        ("hey speaker pause", "pause"),
        ("hi speaker stop", "stop"),
        ("hi speaker clear", "clear"),
        ("play", None),  # no wake phrase
        ("hi speaker dance", None),
        ("shut up", "easter_shut_up"),
        ("kill yourself", "easter_kill_yourself"),
        ("hey speaker reboot", "easter_kill_yourself"),
        ("play despacito", "easter_despacito"),
        ("happy birthday", "easter_happy_birthday"),
        ("what is our grade", "easter_grade"),
    ],
)
def test_voice_commands_are_understood(text, expected):
    assert VoiceCommand()._parse_command(text) == expected


# ---------------------------------------------------------------------------
# The controller around it
# ---------------------------------------------------------------------------


@pytest.fixture
def rig(monkeypatch):
    return Rig(monkeypatch, voice_command=fakes.FakeVoice())


def test_a_stuck_ptt_button_is_treated_as_let_go_after_the_limit(rig):
    rig.tap_chip("AA")
    rig.controller._voice_command.command = "play"
    rig.press(ButtonID.PTT)
    assert rig.mic.released == []
    rig.buttons.hold(ButtonID.PTT, 11)  # still held, longer than PTT_MAX_HOLD
    rig.step()
    assert rig.state == State.PLAYING  # the command was carried out
    assert rig.mic.released  # and the mic was given back
    released_before = list(rig.mic.released)
    rig.release(ButtonID.PTT)  # letting go later does not process it again
    assert rig.mic.released == released_before


def test_a_voice_failure_still_releases_the_mic_and_the_loop_goes_on(rig):
    def explode():
        raise RuntimeError("speech library crashed")

    rig.controller._voice_command.stop_and_parse = explode
    rig.tap_chip("AA")
    rig.press(ButtonID.PTT)
    rig.release(ButtonID.PTT)  # must not raise
    assert rig.mic.released == [True]
    assert rig.mic.owner is None
    assert rig.state == State.IDLE_CHIP_LOADED


def test_a_voice_blink_does_not_block_the_main_loop(monkeypatch):
    # The blink used to sleep on the main thread, so no button worked for 0.6 s after a command.
    gate = threading.Event()
    main_thread = threading.get_ident()
    seen_threads = []

    class SlowLeds(fakes.CallLog):
        def set_light(self, light, color):
            seen_threads.append(threading.get_ident())
            gate.wait(5)
            self.calls.append(("set_light", light, color))

        def off(self, light):
            self.calls.append(("off", light))

    leds = SlowLeds()
    rig = Rig(monkeypatch, voice_command=fakes.FakeVoice(), ptt_leds=leds)
    monkeypatch.setattr(controller_module.time, "sleep", lambda seconds: None)
    started = time.monotonic()
    thread = rig.controller._ptt_blink(Colors.RED)
    assert time.monotonic() - started < 0.5  # came straight back while the LED is still "busy"
    assert thread.is_alive()
    gate.set()
    thread.join(5)
    assert leds.calls.count(("set_light", 2, Colors.RED)) == 3
    assert leds.calls.count(("off", 2)) == 3
    assert seen_threads and main_thread not in seen_threads
