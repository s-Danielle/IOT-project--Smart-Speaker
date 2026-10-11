"""Phase 1 of a deployment: installing the system files, with a preview and a rollback.

Everything happens in temporary folders, with a fake systemctl. Nothing is installed on this
computer, and no system command is run.
"""

import json
import re
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "pi"))

import pi_install_system as pis  # noqa: E402
from pi_install_system import FolderSource, Stop, SystemInstall, compare, exec_start_program, expected_entries, parse_manifest  # noqa: E402

HEALTH_UNIT = "[Service]\nExecStart=/home/iot-proj/venv/bin/python health_monitor.py\n"
HEALTH_UNIT_OLD = "[Service]\nExecStart=/usr/bin/python3 health_monitor.py\n"
CONTROLLER_UNIT = "[Service]\nExecStart=/home/iot-proj/venv/bin/python main.py\nRuntimeDirectory=smart_speaker\n"
SERVER_UNIT = "[Service]\nExecStart=/home/iot-proj/venv/bin/python server_main.py\n"
WIFI_UNIT = "[Service]\nExecStart=/home/iot-proj/venv/bin/python wifi_provisioner.py\n"
MANIFEST = """# comment
system/logrotate-smart-speaker      /etc/logrotate.d/smart_speaker                      644
system/journald-persistent.conf     /etc/systemd/journald.conf.d/90-smart-speaker.conf  644   systemd-journald
"""


def make_bundle(folder, **overrides):
    """A folder laid out like /tmp/pi: services/ with units, system/ and system-files.txt."""
    files = {
        "smart_speaker_server.service": SERVER_UNIT,
        "smart_speaker.service": CONTROLLER_UNIT,
        "smart_speaker_health.service": HEALTH_UNIT,
        "smart_speaker_wifi.service": WIFI_UNIT,
        "system-files.txt": MANIFEST,
        "system/logrotate-smart-speaker": "/var/log/x.log {\n  weekly\n}\n",
        "system/journald-persistent.conf": "[Journal]\nStorage=persistent\n",
    }
    files.update(overrides)
    for name, content in files.items():
        if content is None:
            continue
        path = Path(folder) / "services" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return FolderSource(folder)


class FakeSystemctl:
    def __init__(self):
        self.calls = []
        self.active = {}  # unit -> state answered by is-active (default: active)

    def __call__(self, argv, timeout=20, input_text=None):
        self.calls.append(argv)
        if argv[:2] == ["systemctl", "is-active"]:
            return 0, self.active.get(argv[2], "active") + "\n"
        return 0, ""

    def commands(self):
        return [" ".join(c) for c in self.calls]


@pytest.fixture
def world(tmp_path):
    class World:
        pass

    w = World()
    w.root = tmp_path / "pi"                # stands in for the Pi's /
    w.bundle = tmp_path / "bundle"
    w.state = tmp_path / "state"
    w.root.mkdir()
    w.systemctl = FakeSystemctl()
    w.source = make_bundle(w.bundle)

    def installer(dry=False, source=None, exists=lambda path: True):
        return SystemInstall(source or w.source, dry=dry, root=w.root, runner=w.systemctl, exists=exists,
                             state_root=w.state, restart_wait=0)

    w.installer = installer

    def dest(path):
        return w.root / path.lstrip("/")

    w.dest = dest
    return w


def install_current_files(w):
    """Put the bundle's files on the 'Pi' as if phase 1 had been run."""
    for entry, status in compare(expected_entries(w.source), w.root):
        target = w.dest(entry.dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.content)


# ---------------------------------------------------------------------------
# Reading what should be installed
# ---------------------------------------------------------------------------


def test_the_manifest_lines_are_read_and_comments_skipped():
    assert parse_manifest(MANIFEST) == [
        ("system/logrotate-smart-speaker", "/etc/logrotate.d/smart_speaker", "644", None),
        ("system/journald-persistent.conf", "/etc/systemd/journald.conf.d/90-smart-speaker.conf", "644", "systemd-journald"),
    ]
    assert parse_manifest("") == [] and parse_manifest(None) == []


@pytest.mark.parametrize("line", ["only-two-fields /etc/x", "src /usr/bin/x 644"])
def test_a_bad_manifest_line_stops_everything(line):
    with pytest.raises(Stop):
        parse_manifest(line)


def test_every_service_file_and_manifest_line_is_expected(world):
    entries = {e.dest: e for e in expected_entries(world.source)}
    assert set(entries) == {
        "/etc/systemd/system/smart_speaker_server.service", "/etc/systemd/system/smart_speaker.service",
        "/etc/systemd/system/smart_speaker_health.service", "/etc/systemd/system/smart_speaker_wifi.service",
        "/etc/logrotate.d/smart_speaker", "/etc/systemd/journald.conf.d/90-smart-speaker.conf"}
    assert entries["/etc/systemd/system/smart_speaker.service"].restart == "smart_speaker"
    assert entries["/etc/systemd/system/smart_speaker_wifi.service"].restart is None  # never restarted by this script
    assert entries["/etc/systemd/journald.conf.d/90-smart-speaker.conf"].restart == "systemd-journald"
    assert entries["/etc/logrotate.d/smart_speaker"].restart is None


def test_a_file_the_manifest_lists_but_the_bundle_lacks_stops_everything(tmp_path):
    source = make_bundle(tmp_path / "b", **{"system/logrotate-smart-speaker": None})
    with pytest.raises(Stop, match="missing"):
        expected_entries(source)


def test_a_manifest_mode_that_is_not_a_mode_stops_everything(tmp_path):
    source = make_bundle(tmp_path / "b", **{"system-files.txt": "system/logrotate-smart-speaker /etc/logrotate.d/x rw-r--r--\n"})
    with pytest.raises(Stop, match="mode"):
        expected_entries(source)


@pytest.mark.parametrize("unit, program", [
    ("[Service]\nExecStart=/usr/bin/python3 health_monitor.py\n", "/usr/bin/python3"),
    ("ExecStart=-/bin/true\n", "/bin/true"),
    ("ExecStart=\n", None),
    ("[Service]\nUser=x\n", None),
])
def test_the_program_a_service_starts(unit, program):
    assert exec_start_program(unit) == program


# ---------------------------------------------------------------------------
# Installing
# ---------------------------------------------------------------------------


def test_a_first_install_creates_every_file_with_its_mode(world, capsys):
    assert world.installer().install() == 0
    for entry in expected_entries(world.source):
        target = world.dest(entry.dest)
        assert target.read_bytes() == entry.content
        assert stat.S_IMODE(target.stat().st_mode) == int(entry.mode, 8)
    assert "NEW" in capsys.readouterr().out


def test_the_changed_services_are_restarted_in_order_after_one_reload(world):
    world.installer().install()
    commands = world.systemctl.commands()
    assert commands[0] == "systemctl daemon-reload"
    restarts = [c.split()[-1] for c in commands if " restart " in c]
    assert restarts == ["smart_speaker_server", "smart_speaker", "smart_speaker_health", "systemd-journald"]


def test_the_wifi_service_is_never_restarted(world, capsys):
    world.installer().install()
    assert not any("smart_speaker_wifi" in c and "restart" in c for c in world.systemctl.commands())
    assert "next boot" in capsys.readouterr().out


def test_only_services_whose_own_file_changed_are_restarted(world):
    install_current_files(world)
    world.dest("/etc/systemd/system/smart_speaker_health.service").write_text(HEALTH_UNIT_OLD)  # the Pi has the old one
    world.installer().install()
    assert world.systemctl.commands()[:2] == ["systemctl daemon-reload", "systemctl restart smart_speaker_health"]
    assert not any("restart smart_speaker_server" in c or "restart smart_speaker " in c + " " for c in world.systemctl.commands())


def test_the_saved_log_setting_restarts_the_journal_but_not_the_speaker(world):
    install_current_files(world)
    world.dest("/etc/systemd/journald.conf.d/90-smart-speaker.conf").unlink()
    world.installer().install()
    assert world.systemctl.commands() == ["systemctl daemon-reload", "systemctl restart systemd-journald"]


def test_log_rotation_alone_needs_no_reload_and_no_restart(world):
    install_current_files(world)
    world.dest("/etc/logrotate.d/smart_speaker").unlink()
    world.installer().install()
    assert world.systemctl.calls == []


def test_a_second_run_does_nothing(world, capsys):
    world.installer().install()
    world.systemctl.calls.clear()
    runs_before = sorted(p.name for p in world.state.iterdir())
    assert world.installer().install() == 0
    assert world.systemctl.calls == []
    assert sorted(p.name for p in world.state.iterdir()) == runs_before  # no empty backup folder
    assert "already installed" in capsys.readouterr().out


def test_a_preview_changes_nothing_and_runs_nothing(world, capsys):
    assert world.installer(dry=True).install() == 0
    assert list(world.root.iterdir()) == [] and not world.state.exists()
    assert world.systemctl.calls == []
    out = capsys.readouterr().out
    assert "[preview]" in out and "This was a preview" in out


def test_a_preview_says_what_would_be_replaced(world, capsys):
    install_current_files(world)
    world.dest("/etc/systemd/system/smart_speaker.service").write_text("[Service]\nExecStart=/bin/true\n")
    world.installer(dry=True).install()
    out = capsys.readouterr().out
    assert re.search(r"CHANGES\s+/etc/systemd/system/smart_speaker.service", out)
    assert re.search(r"ok\s+/etc/systemd/system/smart_speaker_health.service", out)
    assert "restart smart_speaker" in out


def test_a_service_file_whose_program_is_missing_stops_before_anything_changes(world):
    with pytest.raises(Stop, match="does not exist"):
        world.installer(exists=lambda path: False).install()
    assert list(world.root.iterdir()) == [] and world.systemctl.calls == [] and not world.state.exists()


def test_unchanged_service_files_are_not_checked_for_their_program(world):
    install_current_files(world)
    assert world.installer(exists=lambda path: False).install() == 0  # nothing changed, so nothing to start


def test_a_service_that_does_not_come_back_is_reported(world, capsys):
    world.systemctl.active["smart_speaker_health"] = "failed"
    assert world.installer().install() == 1
    assert "smart_speaker_health is failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Rolling back
# ---------------------------------------------------------------------------


def test_the_old_files_are_saved_before_they_are_replaced(world):
    install_current_files(world)
    old = world.dest("/etc/systemd/system/smart_speaker_health.service")
    old.write_text(HEALTH_UNIT_OLD)
    world.installer().install()
    folder = next(world.state.iterdir())
    state = json.loads((folder / "state.json").read_text())
    assert [r["dest"] for r in state["entries"]] == ["/etc/systemd/system/smart_speaker_health.service"]
    assert (folder / state["entries"][0]["backup"]).read_text() == HEALTH_UNIT_OLD
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_a_rollback_puts_old_files_back_and_removes_new_ones(world):
    install_current_files(world)
    world.dest("/etc/systemd/system/smart_speaker_health.service").write_text(HEALTH_UNIT_OLD)
    world.dest("/etc/logrotate.d/smart_speaker").unlink()  # this one did not exist before
    world.installer().install()
    assert world.dest("/etc/logrotate.d/smart_speaker").exists()
    world.systemctl.calls.clear()
    assert world.installer().rollback() == 0
    assert world.dest("/etc/systemd/system/smart_speaker_health.service").read_text() == HEALTH_UNIT_OLD
    assert not world.dest("/etc/logrotate.d/smart_speaker").exists()
    assert world.systemctl.commands()[:2] == ["systemctl daemon-reload", "systemctl restart smart_speaker_health"]


def test_a_rollback_of_a_first_install_leaves_the_pi_as_it_was(world):
    world.installer().install()
    world.installer().rollback()
    leftovers = [p for p in world.root.rglob("*") if p.is_file()]
    assert leftovers == []


def test_a_rollback_preview_changes_nothing(world):
    world.installer().install()
    before = sorted(str(p) for p in world.root.rglob("*") if p.is_file())
    world.systemctl.calls.clear()
    world.installer(dry=True).rollback()
    assert sorted(str(p) for p in world.root.rglob("*") if p.is_file()) == before
    assert world.systemctl.calls == []


def test_the_same_run_cannot_be_rolled_back_twice(world):
    world.installer().install()
    world.installer().rollback()
    with pytest.raises(Stop, match="nothing to roll back"):
        world.installer().rollback()


def test_a_rollback_with_no_earlier_run_says_so(world):
    with pytest.raises(Stop, match="nothing to roll back"):
        world.installer().rollback()


def test_a_rollback_goes_back_one_run_at_a_time(world, monkeypatch):
    install_current_files(world)
    health = world.dest("/etc/systemd/system/smart_speaker_health.service")
    health.write_text(HEALTH_UNIT_OLD)
    monkeypatch.setattr(pis, "stamp", lambda: "20261010-100000")
    world.installer().install()                              # run 1: old -> new
    monkeypatch.setattr(pis, "stamp", lambda: "20261010-110000")
    world.installer(source=make_bundle(world.bundle / "v2", **{"smart_speaker_health.service": HEALTH_UNIT + "# v2\n"})).install()  # run 2
    world.installer().rollback()
    assert health.read_text() == HEALTH_UNIT                 # back to run 1's result
    world.installer().rollback()
    assert health.read_text() == HEALTH_UNIT_OLD             # and then to the original


# ---------------------------------------------------------------------------
# Checking (what pi_update.sh asks before it switches the code)
# ---------------------------------------------------------------------------


def test_check_says_yes_when_everything_matches(world, capsys):
    install_current_files(world)
    assert world.installer().check() == 0
    assert "All 6 system files match" in capsys.readouterr().out


def test_check_says_no_when_something_differs_or_is_missing(world, capsys):
    install_current_files(world)
    world.dest("/etc/logrotate.d/smart_speaker").write_text("changed")
    world.dest("/etc/systemd/journald.conf.d/90-smart-speaker.conf").unlink()
    assert world.installer().check() == 3
    out = capsys.readouterr().out
    assert re.search(r"differs\s+/etc/logrotate.d/smart_speaker", out)
    assert re.search(r"new\s+/etc/systemd/journald.conf.d", out)
    assert "2 system file(s) differ" in out


def test_check_changes_nothing(world):
    world.installer().check()
    assert list(world.root.iterdir()) == [] and world.systemctl.calls == []


# ---------------------------------------------------------------------------
# The real repository, and the scripts around it
# ---------------------------------------------------------------------------


def test_the_real_service_folder_is_readable_and_complete():
    entries = expected_entries(FolderSource(REPO))
    dests = {e.dest for e in entries}
    assert "/etc/systemd/system/smart_speaker.service" in dests
    assert "/etc/systemd/journald.conf.d/90-smart-speaker.conf" in dests
    assert "/etc/logrotate.d/smart_speaker" in dests
    assert all(e.content for e in entries)


def test_the_programs_the_real_service_files_start_are_absolute_paths():
    for entry in expected_entries(FolderSource(REPO)):
        if entry.unit_name:
            program = exec_start_program(entry.content.decode())
            assert program and program.startswith("/"), entry.source


def test_the_bundle_script_copies_the_whole_services_folder():
    text = (REPO / "scripts" / "dev" / "push_to_pi.sh").read_text()
    assert 'cp -r "$REPO/services" "$BUNDLE/pi/services"' in text


def test_switching_code_never_installs_system_files():
    text = (REPO / "scripts" / "pi" / "pi_update.sh").read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("install_units", "install_system_files", "cp \"$f\" \"/etc/", "/etc/systemd/system/", "daemon-reload"):
        assert forbidden not in code, forbidden
    assert "check_system_files" in code and "pi_install_system.py" in code


def test_the_new_wrapper_asks_for_sudo_only_when_it_changes_something():
    text = (REPO / "scripts" / "pi" / "pi_install_system.sh").read_text()
    for harmless in ("--dry-run", "--check", "--help"):
        assert harmless in text.split("needs_root=1")[1].split("done")[0]
    assert "exec sudo" in text
