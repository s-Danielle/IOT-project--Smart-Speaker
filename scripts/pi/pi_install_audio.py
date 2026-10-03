#!/usr/bin/env python3
"""Set up shared audio for the Smart Speaker, safely.

Run it with the .sh wrapper, which asks for sudo:

    bash pi_install_audio.sh --dry-run        # preview, changes nothing
    bash pi_install_audio.sh                  # Part A: sound card sharing
    bash pi_install_audio.sh --mopidy-conf    # Part B: Mopidy settings
    bash pi_install_audio.sh --rollback       # undo the newest run

Part A (the default):
  - installs the packages the new audio code needs
  - installs the pyalsaaudio package into the app's venv
  - puts iot-proj and mopidy in the 'audio' group
  - makes sure the recordings and uploads folders exist, belong to iot-proj
    and can be read by mopidy
  - installs /etc/asound.conf (the shared sound card setup)
  - lowers the card's PCM volume to a safe level and saves it
  - restarts Mopidy and checks that both users can play and record

Part B (--mopidy-conf):
  - sets the [audio], [mpd] and [file] settings from audio/mopidy.conf in the
    live /etc/mopidy/mopidy.conf. It never touches [spotify].

Before it changes anything it saves what it is about to change in
/var/lib/smart-speaker-setup/rollback/<time>/, and --rollback puts that back.
"""

import argparse
import grp
import json
import os
import pwd
import re
import shutil
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ini_edit  # noqa: E402
from pi_common import (  # noqa: E402
    MPDError,
    MPDSocket,
    as_user,
    have,
    is_root,
    mask_secrets,
    now_iso,
    parse_amixer_percent,
    pick_card,
    sh,
    stamp,
)

BUNDLE = Path(__file__).resolve().parent
REF_ASOUND = BUNDLE / "audio" / "asound.conf"
REF_MOPIDY = BUNDLE / "audio" / "mopidy.conf"
REQUIREMENTS = BUNDLE / "requirements.txt"

ASOUND = Path("/etc/asound.conf")
MOPIDY_CONF = Path("/etc/mopidy/mopidy.conf")
STATE_ROOT = Path("/var/lib/smart-speaker-setup/rollback")
APT_PACKAGES = ["alsa-utils", "libasound2-dev", "python3-dev", "build-essential", "i2c-tools", "flac"]
DEFAULT_PYALSAAUDIO = "0.11.0"
SAFE_VOLUME_PERCENT = 40
HAT_SCRIPTS = [
    "/usr/bin/seeed-voicecard",
    "/usr/local/bin/seeed-voicecard",
    "/etc/systemd/system/seeed-voicecard.service",
    "/lib/systemd/system/seeed-voicecard.service",
    "/usr/lib/systemd/system/seeed-voicecard.service",
]


class Stop(Exception):
    """Something went wrong that should end the run."""


def read_text(path):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def render_asound(reference_text, card):
    """The reference asound.conf, pointed at `card` instead of card 0."""
    if card in (None, 0):
        return reference_text
    out = []
    for line in reference_text.splitlines(keepends=True):
        if not line.lstrip().startswith("#"):
            line = re.sub(r'(pcm\s+"hw:)0(,0")', r"\g<1>%d\2" % card, line)
            line = re.sub(r"(\bcard\s+)0\b", r"\g<1>%d" % card, line)
        out.append(line)
    return "".join(out)


def pyalsaaudio_requirement(requirements_text):
    """'pyalsaaudio==x.y.z' from a requirements file, or the default."""
    if requirements_text:
        for line in requirements_text.splitlines():
            if line.strip().lower().startswith("pyalsaaudio"):
                return line.strip()
    return "pyalsaaudio==%s" % DEFAULT_PYALSAAUDIO


def hat_rewrites_asound(paths=HAT_SCRIPTS):
    """(path, line) if the HAT driver's boot script touches /etc/asound.conf, else None."""
    for path in paths:
        text = read_text(path)
        if text:
            for line in text.splitlines():
                if "asound.conf" in line and not line.lstrip().startswith("#"):
                    return path, line.strip()
    return None


class Setup:
    def __init__(self, args):
        self.args = args
        self.dry = args.dry_run
        self.app_user = args.app_user
        self.repo = Path(args.repo)
        self.venv_pip = self.repo / "venv" / "bin" / "pip"
        self.venv_python = self.repo / "venv" / "bin" / "python"
        self.state = {"created": now_iso(), "dry_run": self.dry}
        self.snapshot = None
        self.failures = []
        self.warnings = []

    # ---- output -----------------------------------------------------
    def say(self, text=""):
        print(text, flush=True)

    def step(self, title):
        self.say("\n== %s ==" % title)

    def act(self, text):
        self.say(("[preview] " if self.dry else "") + text)

    def fail(self, text):
        self.failures.append(text)
        self.say("PROBLEM: " + text)

    def warn(self, text):
        self.warnings.append(text)
        self.say("NOTE: " + text)

    # ---- running things --------------------------------------------
    def run(self, argv, what, user=None, timeout=600, changes=True):
        """Run a command. In preview mode, commands that change things are only shown."""
        if user:
            argv = as_user(user, argv)
        self.act("%s\n    $ %s" % (what, " ".join(argv)))
        if self.dry and changes:
            return 0, ""
        rc, out = sh(argv, timeout=timeout)
        out = out.strip()
        if out:
            self.say("    " + out.replace("\n", "\n    ")[:3000])
        return rc, out

    # ---- snapshot (for --rollback) ---------------------------------
    def open_snapshot(self):
        if self.dry or self.snapshot is not None:
            return
        self.snapshot = STATE_ROOT / stamp()
        self.snapshot.mkdir(parents=True, exist_ok=True)
        os.chmod(str(self.snapshot), 0o700)

    def save_state(self):
        if self.dry or self.snapshot is None:
            return
        path = self.snapshot / "state.json"
        path.write_text(json.dumps(self.state, indent=2))
        os.chmod(str(path), 0o600)

    def backup_file(self, source, name):
        """Copy `source` (following links) into the snapshot as `name`."""
        if self.dry:
            return
        self.open_snapshot()
        shutil.copy2(str(source), str(self.snapshot / name))
        os.chmod(str(self.snapshot / name), 0o600)

    # ---- checks before any change ----------------------------------
    def preflight(self, need_part_a, need_part_b):
        self.step("Checking this Pi (nothing is changed yet)")
        if not is_root() and not self.dry:
            raise Stop("This needs root. Run it with sudo, or use the .sh wrapper: bash pi_install_audio.sh")
        if not is_root():
            self.warn("Not running as root, so some root-only files can't be checked in this preview.")
        needed = []
        if need_part_a:
            needed.append(REF_ASOUND)
        if need_part_b:
            needed.append(REF_MOPIDY)
        for path in needed:
            if not path.exists():
                raise Stop("Missing %s. Copy the whole bundle with scripts/pi/push_to_pi.sh." % path)
        try:
            pwd.getpwnam(self.app_user)
        except KeyError:
            raise Stop("The user '%s' does not exist on this machine." % self.app_user)
        try:
            pwd.getpwnam("mopidy")
        except KeyError:
            raise Stop("The user 'mopidy' does not exist. Is Mopidy installed?")
        if need_part_a:
            hat = hat_rewrites_asound()
            if hat and not self.args.ignore_hat_service:
                raise Stop(
                    "The HAT's own boot script rewrites /etc/asound.conf, so our file would be "
                    "undone at every boot:\n    %s: %s\n"
                    "I won't guess. Send me the output of pi_report.sh and I'll adjust this script. "
                    "(To go ahead anyway: --ignore-hat-service.)" % hat
                )
        self.say("OK: user %s and mopidy exist, bundle files found." % self.app_user)

    def detect_card(self):
        if self.args.card is not None:
            return self.args.card
        rc, out = sh(["aplay", "-l"])
        card = pick_card(out) if rc == 0 else None
        if card is None:
            self.warn("No sound card found with `aplay -l`; assuming card 0.")
            return 0
        return card

    # ---- Part A -----------------------------------------------------
    def part_a(self):
        self.open_snapshot()
        self.state["part_a"] = True
        self.packages()
        card = self.detect_card()
        self.say("Using sound card number %s." % card)
        self.state["card"] = card
        self.pyalsaaudio()
        self.groups()
        self.folders()
        self.install_asound(card)
        self.safe_volume(card)
        self.restart_mopidy()
        self.verify_audio()
        self.save_state()

    def packages(self):
        self.step("Packages")
        self.run(["apt-get", "update"], "Refresh the package lists")
        rc, _ = self.run(
            ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y"] + APT_PACKAGES,
            "Install %s" % ", ".join(APT_PACKAGES),
        )
        if rc != 0:
            self.fail("apt-get install failed (is the Pi online?).")

    def pyalsaaudio(self):
        self.step("pyalsaaudio in the app's venv")
        if not self.venv_pip.exists():
            self.fail("%s not found. Is the repo at %s?" % (self.venv_pip, self.repo))
            return
        requirement = pyalsaaudio_requirement(read_text(REQUIREMENTS))
        rc, _ = self.run([str(self.venv_pip), "install", requirement],
                         "Install %s" % requirement, user=self.app_user)
        if rc != 0:
            self.fail("pip could not install %s (see the output above)." % requirement)
            return
        if self.dry:
            self.act("Check that alsaaudio imports in the venv")
            return
        rc, out = self.run([str(self.venv_python), "-c", "import alsaaudio; print(alsaaudio.version)"],
                           "Check that it imports", user=self.app_user, changes=False)
        if rc != 0:
            self.fail("alsaaudio still does not import in the venv.")

    def user_groups(self, user):
        try:
            return {g.gr_name for g in grp.getgrall() if user in g.gr_mem} | {
                grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
            }
        except KeyError:
            return set()

    def groups(self):
        self.step("Groups")
        before = {u: self.user_groups(u) for u in (self.app_user, "mopidy")}
        self.state["groups_before"] = {u: sorted(g) for u, g in before.items()}
        for user in (self.app_user, "mopidy"):
            if "audio" in before[user]:
                self.say("OK: %s is already in the audio group." % user)
            else:
                rc, _ = self.run(["usermod", "-aG", "audio", user], "Add %s to the audio group" % user)
                if rc != 0:
                    self.fail("could not add %s to the audio group." % user)
        self.save_state()

    def folders(self):
        self.step("Recordings and uploads folders")
        home = Path(pwd.getpwnam(self.app_user).pw_dir)
        local_files = self.repo / "Main" / "local_files"
        dirs = [local_files, local_files / "recordings", local_files / "uploads"]
        uid = pwd.getpwnam(self.app_user).pw_uid
        gid = pwd.getpwnam(self.app_user).pw_gid
        saved = []
        for path in dirs:
            if path.exists():
                st = os.stat(str(path))
                saved.append({"path": str(path), "existed": True, "mode": stat.S_IMODE(st.st_mode),
                              "uid": st.st_uid, "gid": st.st_gid})
            else:
                saved.append({"path": str(path), "existed": False})
        self.state["folders_before"] = saved
        for path in dirs:
            self.act("Make sure %s exists, belongs to %s, mode 2775 (group can write, new files keep the group)"
                     % (path, self.app_user))
            if not self.dry:
                path.mkdir(parents=True, exist_ok=True)
                os.chown(str(path), uid, gid)
                os.chmod(str(path), 0o2775)

        # Can mopidy walk down to the folders? If not, use group permissions (not world access).
        chain = [p for p in (home, self.repo, self.repo / "Main", local_files) if p.exists()]
        if self.dry and not is_root():
            self.act("Check whether the mopidy user can reach those folders; if not, add mopidy to group "
                     "'%s' and let the group enter %s" % (self.app_user, home))
            return
        blocked = [p for p in chain if sh(as_user("mopidy", ["test", "-x", str(p)]))[0] != 0]
        if not blocked:
            self.say("OK: the mopidy user can reach the folders.")
            return
        self.say("The mopidy user can't enter: %s" % ", ".join(str(p) for p in blocked))
        before = self.user_groups("mopidy")
        self.state["mopidy_in_app_group_before"] = self.app_user in before
        if self.app_user not in before:
            self.run(["usermod", "-aG", self.app_user, "mopidy"],
                     "Add mopidy to the '%s' group (so folder permissions can be group-based)" % self.app_user)
        modes = []
        for path in chain:
            st = os.stat(str(path))
            mode = stat.S_IMODE(st.st_mode)
            if not mode & stat.S_IXGRP:
                modes.append({"path": str(path), "mode": mode})
                self.act("Let the group enter %s (chmod g+x)" % path)
                if not self.dry:
                    os.chmod(str(path), mode | stat.S_IXGRP)
        self.state["modes_before"] = modes
        if not self.dry:
            still = [p for p in chain if sh(as_user("mopidy", ["test", "-x", str(p)]))[0] != 0]
            if still:
                self.fail("mopidy still can't enter: %s. Check the folder permissions by hand."
                          % ", ".join(str(p) for p in still))
            else:
                self.say("OK: the mopidy user can now reach the folders.")
        self.save_state()

    def install_asound(self, card):
        self.step("/etc/asound.conf (shared sound card)")
        reference = read_text(REF_ASOUND)
        new_text = render_asound(reference, card)
        if ASOUND.is_symlink():
            kind, target = "symlink", os.readlink(str(ASOUND))
        elif ASOUND.exists():
            kind, target = "file", None
        else:
            kind, target = "absent", None
        self.state["asound"] = {"kind": kind, "target": target}
        current = read_text(ASOUND) if kind != "absent" else ""
        if kind != "absent" and current == new_text and kind == "file":
            self.say("OK: /etc/asound.conf already has the shared-audio setup.")
            return
        self.say("Right now /etc/asound.conf is: %s%s" %
                 (kind, " -> %s" % target if target else ""))
        if kind != "absent" and current is not None:
            self.backup_file(ASOUND, "asound.conf.orig")
        if self.dry:
            diff = ini_edit.unified_diff(current or "", new_text, "/etc/asound.conf")
            self.say("What would change (first lines):\n" + "".join(diff.splitlines(keepends=True)[:40]))
        self.act("Write the shared-audio /etc/asound.conf for card %s" % card)
        if not self.dry:
            if ASOUND.is_symlink():
                ASOUND.unlink()
            ASOUND.write_text(new_text)
            os.chown(str(ASOUND), 0, 0)
            os.chmod(str(ASOUND), 0o644)
        self.save_state()

    def mixer_controls(self, card):
        rc, out = sh(["amixer", "-c", str(card), "scontrols"])
        return out if rc == 0 else ""

    def safe_volume(self, card):
        self.step("Safe starting volume")
        if not have("amixer"):
            self.warn("amixer is not installed yet (it comes with alsa-utils).")
            return
        rc, out = sh(["amixer", "-c", str(card), "sget", "PCM"])
        if rc != 0:
            controls = self.mixer_controls(card)
            self.fail("The sound card has no volume control called 'PCM', so the volume buttons and the "
                      "volume cap won't work. Controls on card %s:\n    %s\nTell me which one is right "
                      "(settings.py: ALSA_VOLUME_CONTROL)." % (card, controls.strip().replace("\n", "\n    ")))
            return
        current = parse_amixer_percent(out)
        self.state["pcm"] = {"card": card, "percent_before": current}
        self.say("PCM is at %s%% now." % current)
        if current is not None and current <= self.args.volume:
            self.say("OK: that is already at or below %d%%." % self.args.volume)
            return
        self.run(["amixer", "-c", str(card), "sset", "PCM", "%d%%" % self.args.volume],
                 "Set PCM to %d%%" % self.args.volume)
        self.run(["alsactl", "store"], "Save the mixer levels so they survive a reboot")
        self.save_state()

    def restart_mopidy(self):
        self.step("Restart Mopidy")
        self.run(["systemctl", "restart", "mopidy"], "Restart Mopidy")
        if self.dry:
            return
        for _ in range(30):
            try:
                MPDSocket("127.0.0.1", 6600, timeout=2).close()
                self.say("OK: Mopidy answers on port 6600.")
                return
            except MPDError:
                time.sleep(1)
        self.fail("Mopidy did not come back within 30 seconds. See: journalctl -u mopidy -n 40. "
                  "You can undo this with: bash pi_install_audio.sh --rollback")

    def verify_audio(self):
        self.step("Check that both users can play and record")
        if self.dry:
            self.act("Play 1 second of silence as %s and as mopidy, and record 1 second as %s"
                     % (self.app_user, self.app_user))
            return
        tests = [
            ("play as %s (feedback sounds)" % self.app_user, self.app_user,
             ["aplay", "-D", "feedback", "-q", "-d", "1", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", "48000", "/dev/zero"]),
            ("play as mopidy (music)", "mopidy",
             ["aplay", "-D", "default", "-q", "-d", "1", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", "48000", "/dev/zero"]),
            ("record as %s" % self.app_user, self.app_user,
             ["arecord", "-D", "default", "-q", "-d", "1", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", "48000", "/dev/null"]),
        ]
        for label, user, argv in tests:
            rc, out = sh(as_user(user, argv), timeout=30)
            if rc == 0:
                self.say("OK: %s" % label)
            else:
                self.fail("%s failed: %s" % (label, out.strip()[:300]))

    # ---- Part B -----------------------------------------------------
    def part_b(self):
        self.step("Mopidy settings ([audio], [mpd], [file])")
        self.open_snapshot()
        live = read_text(MOPIDY_CONF)
        if live is None:
            raise Stop("Cannot read %s (is Mopidy installed, and are you root?)." % MOPIDY_CONF)
        new = ini_edit.apply_sections(live, read_text(REF_MOPIDY), ["audio", "mpd", "file"])
        if new == live:
            self.say("OK: /etc/mopidy/mopidy.conf already has these settings.")
            return
        diff = mask_secrets(ini_edit.unified_diff(live, new, str(MOPIDY_CONF)))
        self.say("These lines would change (no [spotify] lines are touched):\n" + diff)
        st = os.stat(str(MOPIDY_CONF))
        self.state["mopidy_conf"] = {"existed": True, "mode": stat.S_IMODE(st.st_mode),
                                     "uid": st.st_uid, "gid": st.st_gid}
        self.backup_file(MOPIDY_CONF, "mopidy.conf.orig")
        self.act("Write the new /etc/mopidy/mopidy.conf (same owner and permissions)")
        if self.dry:
            return
        tmp = MOPIDY_CONF.with_name(MOPIDY_CONF.name + ".new")
        tmp.write_text(new)
        os.chown(str(tmp), st.st_uid, st.st_gid)
        os.chmod(str(tmp), stat.S_IMODE(st.st_mode))
        os.replace(str(tmp), str(MOPIDY_CONF))
        self.save_state()
        failures_before = len(self.failures)
        self.restart_mopidy()
        rc, state = sh(["systemctl", "is-active", "mopidy"])
        if rc != 0 or len(self.failures) > failures_before:
            self.say("Mopidy is not healthy after the change, so I'm putting the old settings back.")
            shutil.copy2(str(self.snapshot / "mopidy.conf.orig"), str(MOPIDY_CONF))
            os.chown(str(MOPIDY_CONF), st.st_uid, st.st_gid)
            sh(["systemctl", "restart", "mopidy"])
            self.fail("Mopidy did not start with the new settings; the old file is back. "
                      "Look at: journalctl -u mopidy -n 40")
        rc, out = sh("journalctl -u mopidy -n 15 --no-pager 2>&1 | tail -n 15")
        self.say("Last Mopidy log lines:\n    " + mask_secrets(out.strip()).replace("\n", "\n    "))

    # ---- Undo ---------------------------------------------------------
    def rollback(self, folder=None, everything=False):
        snapshots = sorted(p for p in STATE_ROOT.glob("*") if (p / "state.json").exists()) if STATE_ROOT.exists() else []
        if not snapshots:
            raise Stop("Nothing to undo: no saved setups in %s." % STATE_ROOT)
        chosen = [Path(folder)] if folder else (snapshots[::-1] if everything else [snapshots[-1]])
        for snap in chosen:
            self.step("Undoing the setup saved in %s" % snap)
            self.undo_one(snap)
        left = [s for s in snapshots if s not in chosen]
        if left and not folder:
            self.say("\n%d earlier setup(s) remain. Run --rollback again (or --rollback --all-setups) "
                     "to undo them too." % len(left))

    def undo_one(self, snap):
        state = json.loads((snap / "state.json").read_text())
        asound = state.get("asound")
        if asound:
            self.act("Restore /etc/asound.conf (it was: %s)" % asound["kind"])
            if not self.dry:
                try:
                    if asound["kind"] == "file":
                        shutil.copy2(str(snap / "asound.conf.orig"), str(ASOUND))
                    elif asound["kind"] == "symlink":
                        if ASOUND.exists() or ASOUND.is_symlink():
                            ASOUND.unlink()
                        os.symlink(asound["target"], str(ASOUND))
                    elif asound["kind"] == "absent" and ASOUND.exists():
                        ASOUND.unlink()
                except OSError as exc:
                    self.fail("could not restore /etc/asound.conf: %s" % exc)
        conf = state.get("mopidy_conf")
        if conf and (snap / "mopidy.conf.orig").exists():
            self.act("Restore /etc/mopidy/mopidy.conf")
            if not self.dry:
                try:
                    shutil.copy2(str(snap / "mopidy.conf.orig"), str(MOPIDY_CONF))
                    os.chown(str(MOPIDY_CONF), conf["uid"], conf["gid"])
                    os.chmod(str(MOPIDY_CONF), conf["mode"])
                except OSError as exc:
                    self.fail("could not restore /etc/mopidy/mopidy.conf: %s" % exc)
        pcm = state.get("pcm")
        if pcm and pcm.get("percent_before") is not None:
            self.run(["amixer", "-c", str(pcm["card"]), "sset", "PCM", "%d%%" % pcm["percent_before"]],
                     "Put the PCM volume back to %d%%" % pcm["percent_before"])
            self.run(["alsactl", "store"], "Save the mixer levels")
        for user, groups_then in (state.get("groups_before") or {}).items():
            if "audio" not in groups_then:
                self.run(["gpasswd", "-d", user, "audio"], "Remove %s from the audio group again" % user)
        if state.get("mopidy_in_app_group_before") is False:
            self.run(["gpasswd", "-d", "mopidy", self.app_user],
                     "Remove mopidy from the '%s' group again" % self.app_user)
        for item in state.get("modes_before") or []:
            self.act("Put the mode of %s back to %o" % (item["path"], item["mode"]))
            if not self.dry:
                os.chmod(item["path"], item["mode"])
        for item in state.get("folders_before") or []:
            if item.get("existed"):
                self.act("Put the owner and mode of %s back" % item["path"])
                if not self.dry:
                    os.chown(item["path"], item["uid"], item["gid"])
                    os.chmod(item["path"], item["mode"])
        if any(k in state for k in ("asound", "mopidy_conf", "pcm")):
            self.run(["systemctl", "restart", "mopidy"], "Restart Mopidy")
        self.say("(Packages that were installed are left in place; they are harmless.)")

    # ---- Summary --------------------------------------------------------
    def summary(self):
        self.say("\n" + "=" * 60)
        if self.failures:
            self.say("FINISHED WITH PROBLEMS:")
            for item in self.failures:
                self.say("  - " + item)
            self.say("Send me this output. To undo: bash pi_install_audio.sh --rollback")
        else:
            self.say("DONE%s." % (" (preview only, nothing was changed)" if self.dry else ""))
        for item in self.warnings:
            self.say("  note: " + item)
        if not self.failures and not self.dry:
            self.say("Next: run the quick check (pi_smoke_test.py) and play a song.")
        return 1 if self.failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument("--mopidy-conf", action="store_true", help="Part B: edit the live Mopidy settings")
    parser.add_argument("--all", action="store_true", help="Part A and Part B together")
    parser.add_argument("--rollback", nargs="?", const="", metavar="FOLDER",
                        help="undo the newest run (or the given saved folder)")
    parser.add_argument("--all-setups", dest="all_setups", action="store_true",
                        help="with --rollback: undo every saved setup, newest first")
    parser.add_argument("--card", type=int, help="sound card number (default: found with aplay -l)")
    parser.add_argument("--volume", type=int, default=SAFE_VOLUME_PERCENT, help="safe PCM volume in percent")
    parser.add_argument("--app-user", default="iot-proj")
    parser.add_argument("--repo", default="/home/iot-proj/IOT-project--Smart-Speaker")
    parser.add_argument("--ignore-hat-service", action="store_true",
                        help="go ahead even if the HAT's boot script rewrites /etc/asound.conf")
    args = parser.parse_args()

    setup = Setup(args)
    try:
        if args.rollback is not None:
            if not is_root() and not args.dry_run:
                raise Stop("Undo needs root. Use the .sh wrapper or sudo.")
            setup.rollback(args.rollback or None, everything=args.all_setups)
            return setup.summary()
        do_b = args.mopidy_conf or args.all
        do_a = args.all or not args.mopidy_conf
        setup.preflight(do_a, do_b)
        if do_a:
            setup.part_a()
        if do_b:
            setup.part_b()
        return setup.summary()
    except Stop as exc:
        print("\nSTOPPED: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
