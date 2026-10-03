"""The service files, the log settings and the shared folders stay consistent.

These only read text files in the repo. They never install or run anything.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from utils.shared_dirs import ensure_shared_dir

REPO = Path(__file__).resolve().parent.parent
SERVICES = REPO / "services"
UNITS = sorted(SERVICES.glob("smart_speaker*.service"))


def lines_of(path):
    return [line.strip() for line in path.read_text().splitlines()]


@pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
def test_every_unit_runs_the_apps_own_python(unit):
    # The health monitor ran on the system Python, so a system package change could break it.
    exec_lines = [line for line in lines_of(unit) if line.startswith("ExecStart=")]
    assert exec_lines
    for line in exec_lines:
        assert "/venv/bin/python" in line, "%s should use the app's venv" % unit.name


@pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
def test_units_that_write_a_log_file_run_unbuffered(unit):
    # Without it the health log stayed empty for minutes and lost its last lines when the service died.
    if "StandardOutput=append:" in unit.read_text():
        assert "Environment=PYTHONUNBUFFERED=1" in lines_of(unit)


@pytest.mark.parametrize("script", sorted(SERVICES.glob("*.sh")), ids=lambda p: p.name)
def test_the_install_scripts_have_valid_syntax(script):
    # Syntax only (bash -n): nothing is run.
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_every_appended_log_is_rotated():
    logs = set()
    for unit in UNITS:
        logs.update(re.findall(r"StandardOutput=append:(\S+)", unit.read_text()))
    assert logs
    rotation = (SERVICES / "system" / "logrotate-smart-speaker").read_text()
    for log in logs:
        assert log in rotation, "%s grows for ever: add it to logrotate-smart-speaker" % log


def test_the_system_file_list_points_at_real_files():
    entries = [line.split() for line in lines_of(SERVICES / "system-files.txt") if line and not line.startswith("#")]
    assert entries
    for entry in entries:
        source, destination, mode = entry[:3]
        assert (SERVICES / source).is_file(), source
        assert destination.startswith("/etc/"), destination
        assert re.fullmatch(r"[0-7]{3,4}", mode), mode


def test_the_system_log_is_kept_across_reboots():
    # Raspberry Pi OS keeps it in memory only. On Sep 5 the evidence was gone after the next boot.
    text = (SERVICES / "system" / "journald-persistent.conf").read_text()
    assert "Storage=persistent" in text
    assert "SystemMaxUse=" in text  # and small, for the SD card


def test_mopidy_logs_spotifys_own_messages():
    text = (SERVICES / "audio" / "mopidy.conf").read_text()
    assert re.search(r"^\[loglevels\]", text, re.M)
    assert re.search(r"^mopidy_spotify = info", text, re.M)


def test_the_audio_installer_copies_the_loglevels_section_too():
    installer = (REPO / "scripts" / "pi" / "pi_install_audio.py").read_text()
    assert '"loglevels"' in installer


# ---------------------------------------------------------------------------
# Folders the server creates
# ---------------------------------------------------------------------------


def test_the_folder_is_created(tmp_path):
    target = tmp_path / "local_files" / "recordings"
    ensure_shared_dir(str(target), str(tmp_path))
    assert target.is_dir()


def test_an_existing_folder_is_fine(tmp_path):
    ensure_shared_dir(str(tmp_path), str(tmp_path))


def test_as_root_the_folder_is_handed_to_the_speakers_user(tmp_path, monkeypatch):
    # The server runs as root and made these folders root-owned, so arecord (running as the
    # normal user) could not save recordings into them.
    calls = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: calls.append(("chown", path, uid, gid)))
    monkeypatch.setattr(os, "chmod", lambda path, mode: calls.append(("chmod", path, mode)))
    target = str(tmp_path / "recordings")
    ensure_shared_dir(target, str(tmp_path))
    owner = os.stat(tmp_path)
    assert ("chown", target, owner.st_uid, owner.st_gid) in calls
    assert ("chmod", target, 0o775) in calls


def test_as_a_normal_user_ownership_is_left_alone(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError("must not change ownership when not root")

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(os, "chown", forbidden)
    ensure_shared_dir(str(tmp_path / "x"), str(tmp_path))


def test_a_failed_chown_does_not_stop_the_server_starting(tmp_path, monkeypatch):
    def refuse(*args):
        raise PermissionError("no")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", refuse)
    ensure_shared_dir(str(tmp_path / "x"), str(tmp_path))  # must not raise
