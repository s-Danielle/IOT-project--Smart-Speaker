"""Volume: a safe level at start-up, and a missing audio package must not crash the speaker."""

import importlib
import sys

import fakes
import hardware.mixer as mixer_module
from config.settings import VOLUME_DEFAULT
from hardware.mixer import Mixer
from rig import NO_LIMITS, Rig


# --- start-up volume -------------------------------------------------------------------------


def test_start_up_is_lowered_to_the_default_volume(monkeypatch):
    # The sound card powers up loud (85%) and nothing set the volume, so the first sound
    # after a boot could be much louder than the buttons ever allow.
    rig = Rig(monkeypatch, volume=85)
    assert rig.mixer.volume == VOLUME_DEFAULT


def test_start_up_respects_the_parental_cap(monkeypatch):
    rig = Rig(monkeypatch, volume=85, parental={**NO_LIMITS, "enabled": True, "volume_limit": 30})
    assert rig.mixer.volume == 30


def test_a_volume_that_is_already_quiet_is_left_alone(monkeypatch):
    rig = Rig(monkeypatch, volume=20)
    assert rig.mixer.volume == 20
    assert rig.mixer.set_calls == []


def test_a_broken_mixer_does_not_stop_the_controller_starting(monkeypatch):
    class BrokenMixer(fakes.FakeMixer):
        def get_volume(self):
            raise RuntimeError("mixer died")

    monkeypatch.setattr(fakes, "FakeMixer", BrokenMixer)
    Rig(monkeypatch)  # must not raise


# --- the mixer itself ------------------------------------------------------------------------


def test_the_mixer_reads_and_sets_the_card_volume():
    mixer = Mixer()
    assert mixer.get_volume() == 85
    assert mixer.set_volume(40) is True
    assert fakes.FakeAlsaMixer.volumes == [40, 40]
    assert mixer.volume_up() == 50
    assert mixer.volume_down() == 40


def test_a_missing_pcm_control_does_not_crash():
    fakes.FakeAlsaMixer.fail_open = True
    mixer = Mixer()
    assert mixer.get_volume() == VOLUME_DEFAULT
    assert mixer.set_volume(30) is False


def test_a_missing_audio_package_does_not_crash(monkeypatch):
    monkeypatch.setattr(mixer_module, "alsaaudio", None)
    mixer = Mixer()
    assert mixer.get_volume() == VOLUME_DEFAULT
    assert mixer.set_volume(30) is False


def test_importing_the_mixer_without_the_audio_package_does_not_crash(monkeypatch):
    # The controller imported the mixer at start-up, so a missing pyalsaaudio crashed it every 5 s.
    monkeypatch.setitem(sys.modules, "alsaaudio", None)  # makes `import alsaaudio` fail
    try:
        reloaded = importlib.reload(mixer_module)
        assert reloaded.alsaaudio is None
        assert reloaded.Mixer().get_volume() == VOLUME_DEFAULT
    finally:
        monkeypatch.undo()
        importlib.reload(mixer_module)
