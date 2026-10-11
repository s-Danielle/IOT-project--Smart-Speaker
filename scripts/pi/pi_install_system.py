#!/usr/bin/env python3
"""Install the Smart Speaker's system files: service files, the saved system log, log rotation.

These are the changes that a `git checkout` cannot undo, so they are kept apart from the code
(`pi_update.sh` never touches them). Run it with the .sh wrapper, which asks for sudo:

    bash pi_install_system.sh --dry-run       # preview: what is installed, what would change
    bash pi_install_system.sh                 # install, then restart what changed
    bash pi_install_system.sh --rollback      # put the newest run's backups back
    bash pi_install_system.sh --check         # only say whether the Pi matches (no sudo)

What counts as a system file:
  - every services/*.service file          -> /etc/systemd/system/
  - every line of services/system-files.txt -> where that line says (journald, logrotate)
The Mopidy settings are not here: they are installed by `pi_install_audio.sh --mopidy-conf`.

Where the files come from: the bundle that push_to_pi.sh put in /tmp/pi (the default), or a git
ref in the Pi's checkout (--from-git REF, which reads the files from git without switching the
code). The code the Pi is running is never changed by this script.

Before it replaces anything it saves the old file (or the fact that there was none) in
/var/lib/smart-speaker-setup/system-rollback/<time>/, and --rollback puts that back.
A service file that changed is followed by a restart of that service (the server, the controller
and the health monitor only; the WiFi service is never restarted: it takes effect at the next boot).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pi_common import is_root, now_iso, sh, stamp  # noqa: E402

BUNDLE = Path(__file__).resolve().parent
UNIT_DIR = "/etc/systemd/system"
STATE_ROOT = Path("/var/lib/smart-speaker-setup/system-rollback")
DEFAULT_REPO = "/home/iot-proj/IOT-project--Smart-Speaker"

# Restarted when their own service file changed, in this order (the controller needs the server).
RESTARTABLE_UNITS = ["smart_speaker_server", "smart_speaker", "smart_speaker_health"]

CHECK_SAME, CHECK_DIFFERENT = 0, 3
ROLLED_BACK = ".rolled-back"  # a run folder gets this added when it has been undone


class Stop(Exception):
    """Something went wrong that should end the run."""


# ---------------------------------------------------------------------------
# Where the files come from
# ---------------------------------------------------------------------------


class FolderSource:
    """A folder that has a `services/` folder in it: the bundle in /tmp/pi, or a checkout."""

    def __init__(self, root):
        self.root = Path(root)
        self.label = f"folder {self.root}"

    def read(self, relative):
        try:
            return (self.root / "services" / relative).read_bytes()
        except OSError:
            return None

    def units(self):
        folder = self.root / "services"
        return sorted(p.name for p in folder.glob("*.service")) if folder.is_dir() else []


class GitSource:
    """The files of one commit, read with `git show`. The working tree is not touched."""

    def __init__(self, repo, ref):
        self.repo, self.ref = repo, ref
        self.label = f"git {ref}"

    def _git(self, *args):
        # safe.directory: under sudo git runs as root, and the checkout belongs to iot-proj.
        command = ["git", "-c", f"safe.directory={self.repo}", "-C", self.repo, *args]
        result = subprocess.run(command, capture_output=True, timeout=30)
        return result.stdout if result.returncode == 0 else None

    def read(self, relative):
        return self._git("show", f"{self.ref}:services/{relative}")

    def units(self):
        listing = self._git("ls-tree", "--name-only", self.ref, "services/")
        names = (listing or b"").decode().split()
        return sorted(Path(n).name for n in names if n.endswith(".service"))


# ---------------------------------------------------------------------------
# What should be installed
# ---------------------------------------------------------------------------


class Entry:
    def __init__(self, source, dest, mode, restart, content):
        self.source, self.dest, self.mode, self.restart, self.content = source, dest, mode, restart, content

    @property
    def unit_name(self):
        return Path(self.dest).name[: -len(".service")] if self.dest.endswith(".service") else None

    @property
    def is_systemd_file(self):
        return self.dest.startswith("/etc/systemd/")


def parse_manifest(text):
    """The lines of services/system-files.txt: (source, destination, mode, restart-or-None)."""
    entries = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3:
            raise Stop(f"system-files.txt: cannot read the line: {line!r}")
        if not fields[1].startswith("/etc/"):
            raise Stop(f"system-files.txt: {fields[1]} is not under /etc/")
        entries.append((fields[0], fields[1], fields[2], fields[3] if len(fields) > 3 else None))
    return entries


def expected_entries(source):
    """Everything that should be installed according to `source`. Raises Stop if a file is missing."""
    entries = []
    for unit in source.units():
        content = source.read(unit)
        if content is None:
            raise Stop(f"{unit} is listed but cannot be read from {source.label}")
        name = unit[: -len(".service")]
        entries.append(Entry(unit, f"{UNIT_DIR}/{unit}", "644", name if name in RESTARTABLE_UNITS else None, content))
    manifest = source.read("system-files.txt")
    for src, dst, mode, restart in parse_manifest(manifest.decode() if manifest else ""):
        content = source.read(src)
        if content is None:
            raise Stop(f"system-files.txt lists services/{src} but it is missing in {source.label}")
        if not re.fullmatch(r"[0-7]{3,4}", mode):
            raise Stop(f"system-files.txt: {mode!r} is not a file mode")
        entries.append(Entry(src, dst, mode, restart, content))
    return entries


def exec_start_program(unit_text):
    """The program a service file starts (first word of ExecStart), or None."""
    for line in unit_text.splitlines():
        line = line.strip()
        if line.startswith("ExecStart="):
            words = line[len("ExecStart="):].lstrip("-@+!:").split()
            return words[0] if words else None
    return None


def compare(entries, root="/"):
    """[(entry, 'same' | 'new' | 'differs')] against what is installed under `root`."""
    result = []
    for entry in entries:
        path = Path(root) / entry.dest.lstrip("/")
        try:
            installed = path.read_bytes()
        except OSError:
            result.append((entry, "new"))
            continue
        result.append((entry, "same" if installed == entry.content else "differs"))
    return result


# ---------------------------------------------------------------------------
# The installer
# ---------------------------------------------------------------------------


class SystemInstall:
    def __init__(self, source, dry=False, root="/", runner=None, exists=None, state_root=STATE_ROOT, restart_wait=5.0):
        self.source = source
        self.dry = dry
        self.root = Path(root)
        self.run_command = runner or sh
        self.exists = exists or os.path.exists
        self.state_root = Path(state_root)
        self.restart_wait = restart_wait
        self.failures = []

    # ---- output ------------------------------------------------------
    def say(self, text=""):
        print(text, flush=True)

    def step(self, title):
        self.say("\n== %s ==" % title)

    def act(self, text):
        self.say(("[preview] " if self.dry else "") + text)

    def path(self, dest):
        return self.root / dest.lstrip("/")

    # ---- the pieces ----------------------------------------------------
    def preflight(self, changes):
        """Stop before anything is touched if a changed service file could not start."""
        for entry, status in changes:
            if entry.unit_name is None or status == "same":
                continue
            program = exec_start_program(entry.content.decode(errors="replace"))
            if program and program.startswith("/") and not self.exists(program):
                raise Stop(f"{entry.source} would start {program}, which does not exist on this Pi. "
                           "Nothing has been changed.")

    def snapshot(self, changes):
        folder = self.state_root / stamp()
        files = folder / "files"
        files.mkdir(parents=True, exist_ok=True)
        os.chmod(str(folder), 0o700)
        records = []
        for number, (entry, status) in enumerate(changes):
            record = {"dest": entry.dest, "existed": status == "differs", "backup": None, "restart": entry.restart,
                      "unit": entry.unit_name, "systemd": entry.is_systemd_file}
            if status == "differs":
                record["backup"] = f"files/{number}"
                shutil.copy2(str(self.path(entry.dest)), str(folder / record["backup"]))
            records.append(record)
        (folder / "state.json").write_text(json.dumps({
            "created": now_iso(), "source": self.source.label if self.source else None,
            "bundle_commit": read_bundle_commit(), "entries": records}, indent=2))
        return folder

    def write_file(self, entry):
        target = self.path(entry.dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.name + ".new")
        staging.write_bytes(entry.content)
        os.chmod(str(staging), int(entry.mode, 8))
        if os.geteuid() == 0 and self.root == Path("/"):
            os.chown(str(staging), 0, 0)
        os.replace(str(staging), str(target))

    def systemctl(self, what, *args):
        self.act("%s\n    $ systemctl %s" % (what, " ".join(args)))
        if self.dry:
            return 0
        rc, out = self.run_command(["systemctl", *args], timeout=120)
        if out.strip():
            self.say("    " + out.strip().replace("\n", "\n    ")[:1500])
        return rc

    def reload_and_restart(self, records):
        """records: dicts with 'systemd', 'unit', 'restart'. Returns the services restarted."""
        if any(r["systemd"] for r in records):
            self.systemctl("Tell systemd about the new files", "daemon-reload")
        restart = []
        for r in records:
            if r["restart"] and r["restart"] not in restart:
                restart.append(r["restart"])
        ordered = [u for u in RESTARTABLE_UNITS if u in restart] + [u for u in restart if u not in RESTARTABLE_UNITS]
        for unit in ordered:
            self.systemctl(f"Restart {unit} so it uses its new settings", "restart", unit)
        for r in records:
            if r["unit"] and r["unit"] not in RESTARTABLE_UNITS and r["systemd"]:
                self.say(f"NOTE: {r['unit']}.service changed. It is not restarted here; it takes effect at the next boot.")
        return ordered

    def verify(self, restarted):
        if self.dry or not restarted:
            return
        self.step("Checking the restarted services")
        time.sleep(self.restart_wait)
        for unit in restarted:
            if unit == "systemd-journald":
                continue
            rc, out = self.run_command(["systemctl", "is-active", unit], timeout=20)
            state = out.strip()
            if state == "active":
                self.say(f"  {unit}: active")
            else:
                self.failures.append(f"{unit} is {state or 'not running'} after the restart")
                self.say(f"PROBLEM: {unit} is {state or 'not running'}. Put the old files back with:  bash pi_install_system.sh --rollback")

    # ---- commands --------------------------------------------------------------
    def install(self):
        self.step("What this Pi has, compared with %s" % self.source.label)
        entries = expected_entries(self.source)
        results = compare(entries, self.root)
        for entry, status in results:
            mark = {"same": "ok       ", "new": "NEW      ", "differs": "CHANGES  "}[status]
            self.say(f"  {mark} {entry.dest}")
        changes = [(e, s) for e, s in results if s != "same"]
        if not changes:
            self.say("\nEverything is already installed. Nothing to do.")
            return 0

        self.step("Checking that the changed service files can start")
        self.preflight(changes)
        self.say("  ok")

        if not self.dry and not is_root() and self.root == Path("/"):
            raise Stop("This needs root. Run it with sudo, or use the .sh wrapper: bash pi_install_system.sh")

        self.step("Saving what is there now" if not self.dry else "What would be saved")
        if self.dry:
            for entry, status in changes:
                self.act(f"{'back up ' + entry.dest if status == 'differs' else 'note that ' + entry.dest + ' did not exist'}")
            folder = None
        else:
            folder = self.snapshot(changes)
            self.say(f"  saved in {folder}")

        self.step("Installing")
        for entry, status in changes:
            self.act(f"{'replace' if status == 'differs' else 'create'} {entry.dest} (mode {entry.mode})")
            if not self.dry:
                self.write_file(entry)
        records = [{"systemd": e.is_systemd_file, "unit": e.unit_name, "restart": e.restart} for e, _ in changes]
        restarted = self.reload_and_restart(records)
        self.verify(restarted)

        self.step("Done" if not self.failures else "Finished with problems")
        if self.dry:
            self.say("This was a preview. Nothing was changed.")
        elif self.failures:
            return 1
        else:
            self.say("To undo all of this:  bash pi_install_system.sh --rollback")
        return 0

    def rollback(self, name=None):
        runs = sorted(p for p in self.state_root.glob("*")
                      if not p.name.endswith(ROLLED_BACK) and (p / "state.json").is_file()) if self.state_root.is_dir() else []
        if name:
            runs = [p for p in runs if p.name == name]
        if not runs:
            raise Stop("There is nothing to roll back" + (f" (no run called {name})" if name else "") + ".")
        folder = runs[-1]
        state = json.loads((folder / "state.json").read_text())
        self.step(f"Putting back what was there before the run of {folder.name}")
        records = []
        for record in state["entries"]:
            target = self.path(record["dest"])
            if record["existed"]:
                self.act(f"restore {record['dest']}")
                if not self.dry:
                    shutil.copy2(str(folder / record["backup"]), str(target))
            else:
                self.act(f"remove {record['dest']} (it did not exist before)")
                if not self.dry:
                    try:
                        target.unlink()
                    except FileNotFoundError:
                        pass
            records.append(record)
        restarted = self.reload_and_restart(records)
        self.verify(restarted)
        if self.dry:
            self.say("\nThis was a preview. Nothing was changed.")
        else:
            # A second rollback must not undo this one's undo
            folder.rename(folder.with_name(folder.name + ROLLED_BACK))
        return 1 if self.failures else 0

    def check(self):
        entries = expected_entries(self.source)
        results = compare(entries, self.root)
        drift = [(e, s) for e, s in results if s != "same"]
        for entry, status in results:
            self.say(f"  {status:8} {entry.dest}")
        if drift:
            self.say(f"\n{len(drift)} system file(s) differ from {self.source.label}.")
            return CHECK_DIFFERENT
        self.say(f"\nAll {len(results)} system files match {self.source.label}.")
        return CHECK_SAME


def read_bundle_commit():
    try:
        return (BUNDLE / "BUNDLE_COMMIT").read_text().strip()
    except OSError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the speaker's system files (service files, journal, log rotation).")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    parser.add_argument("--rollback", nargs="?", const="", metavar="RUN", help="put the backups of the newest run (or the named one) back")
    parser.add_argument("--check", action="store_true", help="only say whether this Pi matches (exit 0: yes, 3: no)")
    parser.add_argument("--from-git", metavar="REF", help="read the files from this commit in the Pi's checkout instead of the bundle")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="the speaker's program folder (with --from-git)")
    parser.add_argument("--root", default="/", help=argparse.SUPPRESS)  # for tests: install under another folder
    args = parser.parse_args(argv)

    source = GitSource(args.repo, args.from_git) if args.from_git else FolderSource(BUNDLE)
    installer = SystemInstall(source, dry=args.dry_run, root=args.root)
    try:
        if args.rollback is not None:
            return installer.rollback(args.rollback or None)
        if args.check:
            return installer.check()
        return installer.install()
    except Stop as problem:
        print("\nSTOPPED: %s" % problem)
        return 2


if __name__ == "__main__":
    sys.exit(main())
