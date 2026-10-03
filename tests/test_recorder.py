"""The recorder: it takes the mic, starts arecord, and always gives the mic back.

arecord is replaced by a fake process here. No sound card is touched and nothing is recorded.
"""

import io
import os
import subprocess

import fakes
import pytest
from hardware import recorder as recorder_module
from hardware.mic_session import MicSession
from hardware.recorder import Recorder


class FakeProcess:
    """What subprocess.Popen returns for arecord."""

    instances = []

    def __init__(self, command, **kwargs):
        self.command = command
        self.terminated = False
        self.killed = False
        self.exit_code = None  # None: still running
        self.hang_on_terminate = False
        self.stderr = io.BytesIO(b"")
        FakeProcess.instances.append(self)

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        if self.hang_on_terminate and not self.killed:
            raise subprocess.TimeoutExpired("arecord", timeout)
        return 0

    def kill(self):
        self.killed = True


@pytest.fixture
def audio():
    return fakes.FakeAudio()


@pytest.fixture
def mic(audio):
    return MicSession(audio)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module, "RECORDINGS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def arecord(monkeypatch):
    """arecord exists and starts fine, unless a test changes `state`."""
    FakeProcess.instances = []
    state = {"installed": True, "popen_error": None, "exit_at_once": None}

    def run(command, **kwargs):
        if state["installed"]:
            return subprocess.CompletedProcess(command, 0, b"/usr/bin/arecord", b"")
        raise subprocess.CalledProcessError(1, command)

    def popen(command, **kwargs):
        if state["popen_error"]:
            raise state["popen_error"]
        process = FakeProcess(command, **kwargs)
        process.exit_code = state["exit_at_once"]
        return process

    monkeypatch.setattr(recorder_module.subprocess, "run", run)
    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    monkeypatch.setattr(recorder_module.time, "sleep", lambda seconds: None)
    return state


@pytest.fixture
def rec(folder, mic, arecord):
    return Recorder(mic_session=mic)


def test_start_takes_the_mic_and_runs_arecord(rec, mic):
    assert rec.start("Bedtime") is True
    assert mic.owner == "record" and rec.is_recording() is True
    command = FakeProcess.instances[-1].command
    assert command[0] == "arecord" and "-f" in command and command[-1].endswith(".wav")
    assert os.path.basename(command[-1]).startswith("recording_Bedtime_")


def test_a_chip_name_cannot_put_the_file_somewhere_else(rec, folder):
    rec.start("../../etc/pass wd/x")
    path = FakeProcess.instances[-1].command[-1]
    assert os.path.dirname(path) == str(folder)
    assert "/" not in os.path.basename(path)


def test_start_is_refused_when_the_mic_is_busy_and_starts_nothing(rec, mic):
    mic.acquire("ptt")
    assert rec.start("Bedtime") is False
    assert FakeProcess.instances == [] and mic.owner == "ptt"  # the voice command keeps it


def test_a_second_start_while_recording_is_refused(rec, mic):
    rec.start("A")
    assert rec.start("B") is False
    assert len(FakeProcess.instances) == 1 and mic.owner == "record"


def test_music_is_paused_while_recording(rec, audio):
    audio.playing = True
    rec.start("A")
    assert audio.names() == ["pause"]


# --- every way start can fail gives the mic (and the music) back ---------------------------------


def test_no_arecord_installed_gives_the_mic_back(rec, mic, audio, arecord):
    audio.playing = True
    arecord["installed"] = False
    assert rec.start("A") is False
    assert mic.is_held() is False and rec.is_recording() is False
    assert audio.names() == ["pause", "resume"]  # the music comes back


def test_arecord_that_dies_at_once_gives_the_mic_back(rec, mic, audio, arecord):
    audio.playing = True
    arecord["exit_at_once"] = 1
    assert rec.start("A") is False
    assert mic.is_held() is False and rec.is_recording() is False
    assert audio.names() == ["pause", "resume"]


@pytest.mark.parametrize("error", [FileNotFoundError("arecord"), PermissionError("no"), OSError("busy")])
def test_a_failure_to_launch_gives_the_mic_back(rec, mic, arecord, error):
    arecord["popen_error"] = error
    assert rec.start("A") is False
    assert mic.is_held() is False and rec.is_recording() is False
    # and the recorder can be used again afterwards
    arecord["popen_error"] = None
    assert rec.start("A") is True


# --- stop, cancel, close ---------------------------------------------------------------------------


def test_stop_ends_arecord_returns_the_file_and_gives_the_mic_back(rec, mic, audio, folder):
    audio.playing = True
    rec.start("Bedtime")
    path = FakeProcess.instances[-1].command[-1]
    with open(path, "wb") as f:
        f.write(b"RIFF....")
    assert rec.stop() == path
    process = FakeProcess.instances[-1]
    assert process.terminated is True and process.killed is False
    assert mic.is_held() is False and rec.is_recording() is False
    assert audio.names() == ["pause"]  # saved: the music stays paused (the speaker goes to PAUSED)


def test_stop_kills_an_arecord_that_will_not_stop(rec, mic):
    rec.start("A")
    FakeProcess.instances[-1].hang_on_terminate = True
    rec.stop()
    assert FakeProcess.instances[-1].killed is True
    assert mic.is_held() is False


def test_stop_when_not_recording_does_nothing(rec, mic):
    assert rec.stop() is None
    assert mic.is_held() is False


def test_stop_with_a_missing_file_still_gives_the_mic_back(rec, mic):
    rec.start("A")
    assert rec.stop() is not None  # the path; the caller checks the file
    assert mic.is_held() is False


def test_cancel_deletes_the_file_and_resumes_the_music(rec, mic, audio):
    audio.playing = True
    rec.start("A")
    path = FakeProcess.instances[-1].command[-1]
    open(path, "wb").write(b"RIFF")
    rec.cancel()
    assert not os.path.exists(path)
    assert mic.is_held() is False and rec.is_recording() is False
    assert audio.names() == ["pause", "resume"]


def test_cancel_without_restore_leaves_the_music_paused(rec, mic, audio):
    audio.playing = True
    rec.start("A")
    rec.cancel(restore=False)  # cancel-and-clear: the chip is gone
    assert audio.names() == ["pause"] and mic.is_held() is False


def test_cancel_kills_an_arecord_that_will_not_stop(rec, mic):
    rec.start("A")
    FakeProcess.instances[-1].hang_on_terminate = True
    rec.cancel()
    assert FakeProcess.instances[-1].killed is True and mic.is_held() is False


def test_cancel_when_not_recording_does_nothing(rec, mic):
    rec.cancel()
    assert mic.is_held() is False


def test_closing_while_recording_cancels_and_frees_the_mic(rec, mic):
    rec.start("A")
    rec.close()
    assert mic.is_held() is False and rec.is_recording() is False


def test_without_a_mic_session_it_still_records(folder, arecord):
    plain = Recorder()
    assert plain.start("A") is True
    plain.cancel()
