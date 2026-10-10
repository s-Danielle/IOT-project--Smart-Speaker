"""The controller's status file: proof it is alive, what it is doing, whether the last play worked.

The file only ever lives in a temporary folder here. No clocks are waited on: time is moved by hand.
"""

import json
import os
import stat
import subprocess
import threading
import time

import pytest

import core.controller as controller_module
import fakes
from config.settings import MAX_WAIT_FOR_PLAYBACK
from core.state import State
from hardware.buttons import ButtonID
from rig import Rig
from utils import status_file
from utils.status_file import STATUS_STALE_AFTER, read_status, write_status

# ---------------------------------------------------------------------------
# The file itself
# ---------------------------------------------------------------------------


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "status.json")


def test_a_written_status_is_read_back_and_alive(path):
    assert write_status({"state": "PLAYING", "volume": 40}, path) is True
    status = read_status(path)
    assert status["alive"] is True and status["problem"] is None
    assert status["state"] == "PLAYING" and status["volume"] == 40
    assert status["schema"] == 1
    assert 0 <= status["age_seconds"] < 2


def test_the_file_can_be_read_by_other_users_and_leaves_no_temporary_files(path, tmp_path):
    write_status({}, path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    assert os.listdir(tmp_path) == ["status.json"]


def test_no_file_means_the_controller_is_not_running(path):
    status = read_status(path)
    assert status["alive"] is False and status["age_seconds"] is None
    assert "not running" in status["problem"]


@pytest.mark.parametrize("content", ["", "{broken", "[1, 2]", "null", "42"])
def test_a_file_that_cannot_be_used_is_not_alive_and_does_not_raise(path, content):
    with open(path, "w") as f:
        f.write(content)
    status = read_status(path)
    assert status["alive"] is False and status["problem"]


def test_a_file_without_a_timestamp_is_not_alive(path):
    with open(path, "w") as f:
        json.dump({"state": "IDLE_NO_CHIP", "monotonic": "yesterday"}, f)
    assert read_status(path)["alive"] is False


def test_a_controller_that_stops_writing_counts_as_stuck(path):
    write_status({"state": "PLAYING"}, path)
    written = json.load(open(path))["monotonic"]
    assert read_status(path, now=written + STATUS_STALE_AFTER - 1)["alive"] is True
    stuck = read_status(path, now=written + STATUS_STALE_AFTER + 5)
    assert stuck["alive"] is False
    assert "stuck" in stuck["problem"] and stuck["state"] == "PLAYING"  # what it was last doing is still shown


def test_a_file_from_another_boot_is_not_trusted(path):
    write_status({}, path)
    written = json.load(open(path))["monotonic"]
    status = read_status(path, now=written - 5000)  # this machine's clock is behind the file's: another boot
    assert status["alive"] is False and "another boot" in status["problem"]


def test_the_wall_clock_is_not_used_for_proof_of_life(path, monkeypatch):
    # The Pi starts with the wrong date and corrects it later. That must not make the controller look dead.
    write_status({}, path)
    monkeypatch.setattr(time, "time", lambda: 5e9)  # the wall clock jumps decades
    assert read_status(path)["alive"] is True


def test_a_missing_folder_is_reported_not_raised(tmp_path):
    assert write_status({}, str(tmp_path / "nowhere" / "status.json")) is False
    assert os.listdir(tmp_path) == []


def test_a_reader_never_sees_half_a_file(path):
    problems = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            status = read_status(path)
            if status.get("problem") and "cannot be read" in status["problem"]:
                problems.append(status["problem"])

    write_status({"n": 0}, path)
    t = threading.Thread(target=reader)
    t.start()
    try:
        for n in range(500):
            write_status({"n": n, "padding": "x" * 2000}, path)
    finally:
        stop.set()
        t.join()
    assert problems == []


def test_the_default_place_is_the_folder_systemd_makes():
    assert status_file.DEFAULT_PATH == "/run/smart_speaker/status.json"


def test_the_place_can_be_changed_with_an_environment_setting(monkeypatch, path):
    monkeypatch.setenv("SPEAKER_STATUS_FILE", path)
    assert status_file.status_path() == path
    write_status({"state": "X"})
    assert read_status()["state"] == "X"


@pytest.mark.parametrize("returncode, stdout, expected", [(0, "abc1234\n", "abc1234"), (128, "", "unknown"), (0, "", "unknown")])
def test_the_version_comes_from_git(monkeypatch, returncode, stdout, expected):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, returncode, stdout, ""))
    assert status_file.git_version("/anywhere") == expected


def test_the_version_is_unknown_when_git_is_missing(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)
    assert status_file.git_version("/anywhere") == "unknown"


# ---------------------------------------------------------------------------
# The controller writes it
# ---------------------------------------------------------------------------


@pytest.fixture
def rig(monkeypatch, path):
    return Rig(monkeypatch, status_path=path)


def status(path):
    return read_status(path)


def test_the_first_step_writes_the_status(rig, path):
    assert not os.path.exists(path)
    rig.step()
    s = status(path)
    assert s["alive"] is True
    assert s["state"] == "IDLE_NO_CHIP" and s["chip"] is None
    assert s["version"] == "test" and s["volume"] == 50
    assert s["playing"] is False and s["mic_held"] is False and s["last_play"] is None
    assert isinstance(s["components"], dict) and s["uptime_seconds"] >= 0


def test_the_status_follows_a_tapped_chip_at_once(rig, path):
    rig.step()
    rig.tap_chip("AA")
    s = status(path)  # no waiting for the next second
    assert s["state"] == "IDLE_CHIP_LOADED"
    assert s["chip"] == {"id": "chip-1", "uid": "AA", "name": "Chip", "song_name": None}


def test_the_status_shows_the_song_name_of_the_chip(monkeypatch, path):
    chip = {"uid": "AA", "name": "Bedtime", "uri": "spotify:track:abc", "id": "chip-7", "song_name": "Lullaby"}
    rig = Rig(monkeypatch, chips={"AA": chip}, status_path=path)
    rig.tap_chip("AA")
    assert status(path)["chip"] == {"id": "chip-7", "uid": "AA", "name": "Bedtime", "song_name": "Lullaby"}


def test_playing_is_only_true_once_mopidy_has_confirmed(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    rig.audio.confirms = False  # Spotify is still loading
    rig.tap_chip("AA")
    rig.play()
    s = status(path)
    assert s["state"] == "PLAYING" and s["playing"] is False
    assert s["last_play"]["result"] == "waiting"
    rig.audio.playing = True
    rig.step()
    s = status(path)
    assert s["playing"] is True and s["last_play"]["result"] == "ok" and s["last_play"]["reason"] is None


def test_a_link_mopidy_refuses_is_recorded_with_the_reason(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    rig.audio.play_ok = False
    rig.tap_chip("AA")
    rig.play()
    s = status(path)
    assert s["state"] == "IDLE_CHIP_LOADED" and s["playing"] is False
    assert s["last_play"]["result"] == "failed"
    assert "directory or file not found" in s["last_play"]["reason"]


def test_a_song_that_never_starts_is_recorded_as_failed(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    rig.audio.confirms = False
    rig.tap_chip("AA")
    rig.play()
    rig.controller._play_initiated_time -= MAX_WAIT_FOR_PLAYBACK + 1
    rig.step()
    s = status(path)
    assert s["last_play"]["result"] == "failed" and "no sound" in s["last_play"]["reason"]


def test_a_chip_with_no_song_is_not_a_failed_play(monkeypatch, path):
    # It is blocked ("assign a song in the app"), which is nothing like Spotify failing. The app
    # must not show "the last song could not be played" for it.
    rig = Rig(monkeypatch, chips={"AA": {"uid": "AA", "name": "Empty", "uri": "", "id": "c1"}}, status_path=path)
    rig.audio.last_error = "an old Mopidy error"  # left over from earlier: must not be blamed on this
    rig.tap_chip("AA")
    rig.play()
    assert rig.state == State.IDLE_CHIP_LOADED
    assert status(path)["last_play"] is None


def test_a_block_does_not_overwrite_a_real_failure(monkeypatch, path):
    chips = {"AA": {"uid": "AA", "name": "Real", "uri": "spotify:track:bad", "id": "c1"},
             "BB": {"uid": "BB", "name": "Empty", "uri": "", "id": "c2"}}
    rig = Rig(monkeypatch, chips=chips, status_path=path)
    rig.audio.play_ok = False
    rig.tap_chip("AA")
    rig.play()
    assert status(path)["last_play"]["result"] == "failed"
    rig.tap_chip("BB")
    rig.play()  # blocked: no song
    assert status(path)["last_play"]["result"] == "failed"  # the Spotify failure is still the last real attempt


def test_a_resume_that_cannot_reach_mopidy_is_recorded_as_failed(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    rig.load_and_play()
    rig.play()  # pause
    rig.audio.resume = lambda: False
    rig.play()
    last = status(path)["last_play"]
    assert last["result"] == "failed" and "Mopidy" in last["reason"]


def test_a_good_play_after_a_failure_clears_it(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    rig.audio.play_ok = False
    rig.tap_chip("AA")
    rig.play()
    assert status(path)["last_play"]["result"] == "failed"
    rig.audio.play_ok = True
    rig.play()
    rig.step()
    assert status(path)["last_play"]["result"] == "ok"


def test_the_heartbeat_moves_on_every_second_even_when_nothing_changes(rig, path):
    rig.step()
    first = json.load(open(path))["monotonic"]
    rig.controller._last_status_write -= 2  # a second or two pass
    rig.step()
    assert json.load(open(path))["monotonic"] > first


def test_it_does_not_write_on_every_loop(monkeypatch, path):
    rig = Rig(monkeypatch, status_path=path)
    writes = []
    real = controller_module.write_status
    monkeypatch.setattr(controller_module, "write_status", lambda *a, **k: writes.append(1) or real(*a, **k))
    rig.step(200)  # the loop runs 20 times a second
    assert len(writes) <= 2


def test_a_status_folder_that_cannot_be_written_does_not_stop_the_speaker(monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(controller_module, "log_error", errors.append)
    rig = Rig(monkeypatch, status_path=str(tmp_path / "nowhere" / "status.json"))
    rig.step(50)
    rig.tap_chip("AA")
    rig.play()
    assert rig.state == State.PLAYING
    assert len([e for e in errors if "status file" in e]) == 1  # said once, not 20 times a second


def test_with_the_status_file_off_nothing_is_written(monkeypatch, tmp_path):
    rig = Rig(monkeypatch)  # status_path=None
    rig.step(5)
    assert list(tmp_path.iterdir()) == []


def test_the_status_says_when_the_mic_is_in_use(rig, path):
    rig.mic.is_held = lambda: True
    rig.load_and_play()
    s = status(path)
    assert s["mic_held"] is True and s["playing"] is False


def test_a_mixer_that_cannot_be_read_gives_no_volume_not_a_crash(rig, path):
    def broken():
        raise OSError("no sound card")

    rig.mixer.get_volume = broken
    rig.step()
    assert status(path)["volume"] is None


def test_shutting_down_removes_the_file_so_it_shows_as_not_running(rig, path):
    rig.step()
    assert os.path.exists(path)
    rig.controller.shutdown()
    assert not os.path.exists(path)
    assert read_status(path)["alive"] is False


def test_the_component_health_is_in_the_status(rig, path):
    from utils.hardware_health import HardwareHealthManager

    tracker = HardwareHealthManager.get_instance().register("test_part", expected_errors=[], log_interval=1.0, failure_threshold=2)
    tracker.report_error(OSError("boom"))
    tracker.report_error(OSError("boom"))
    rig.step()
    part = status(path)["components"]["test_part"]
    assert part["status"] == "failed" and "boom" in part["last_error"]
    HardwareHealthManager.get_instance().reset_component("test_part")


# ---------------------------------------------------------------------------
# The health monitor lights its LED from it
# ---------------------------------------------------------------------------


@pytest.fixture
def monitor(monkeypatch, path):
    monkeypatch.setenv("SPEAKER_STATUS_FILE", path)
    import health_monitor

    m = health_monitor.HealthMonitor()
    m.check_internet = lambda: True
    m.check_server = lambda: True
    return m


def test_the_controller_counts_as_running_when_its_status_is_fresh(monitor, path):
    write_status({}, path)
    assert monitor.check_hardware() is True


def test_a_missing_status_file_means_no_controller(monitor):
    assert monitor.check_hardware() is False


def test_a_controller_stuck_in_its_loop_is_noticed(monitor, path, monkeypatch):
    # It used to ask systemd "is the process there?", which is still yes for a stuck controller.
    write_status({}, path)
    written = json.load(open(path))["monotonic"]
    monkeypatch.setattr(status_file.time, "monotonic", lambda: written + STATUS_STALE_AFTER + 30)
    assert monitor.check_hardware() is False


def test_the_light_is_green_only_when_the_controller_is_really_running(monitor, path):
    from hardware.leds import Colors

    lit = []
    monitor._leds.set_light = lambda light, color: lit.append(color)
    monitor._blink = lambda color: lit.append(("blink", color))
    write_status({}, path)
    monitor.update_led()
    assert lit[-1] == Colors.GREEN
    os.remove(path)
    monitor.update_led()
    assert lit[-1] == ("blink", Colors.RED)  # network fine, controller gone


def test_the_health_monitor_says_it_once_when_the_controller_goes_away(monitor, path, monkeypatch):
    lines = []
    import health_monitor

    monkeypatch.setattr(health_monitor, "log_health", lines.append)
    for _ in range(5):
        monitor.check_hardware()
    assert len([l for l in lines if "Controller problem" in l]) == 1
