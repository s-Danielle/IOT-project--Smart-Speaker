#!/usr/bin/env python3
"""A quick automatic health check for the Smart Speaker. Run it ON THE PI.

    python3 pi_smoke_test.py                       # all checks
    python3 pi_smoke_test.py --stable-seconds 30   # also watch for restarts for 30 s
    python3 pi_smoke_test.py --only data --save-data snapshot.json
    python3 pi_smoke_test.py --compare-data snapshot.json
    python3 pi_smoke_test.py --watch 7200          # the 2-hour soak test

It only reads (and, if you ask, plays a short beep). Each line is PASS, WARN
(look at it, not necessarily a problem), FAIL or SKIP. The exit code is 1 if
anything FAILED.

Checks: services, I2C buttons/LED chips, audio setup, the speaker's API and data,
recent errors in the logs, the clock.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    status_word,
    to_float,
)

ESSENTIAL_UNITS = ["smart_speaker_server", "smart_speaker", "smart_speaker_health", "mopidy"]
OPTIONAL_UNITS = ["smart_speaker_wifi"]
REPO = os.environ.get("REPO", "/home/iot-proj/IOT-project--Smart-Speaker")
API = os.environ.get("SPEAKER_API", "http://localhost:8080")


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, name, detail=""):
        self.rows.append((status, name, detail))
        print("[%s] %s%s" % (status_word(status), name, (" - " + detail) if detail else ""), flush=True)

    def count(self, status):
        return sum(1 for row in self.rows if row[0] == status)

    def summary(self):
        print("")
        print("%d passed, %d warnings, %d failed, %d skipped" % (
            self.count("PASS"), self.count("WARN"), self.count("FAIL"), self.count("SKIP")))
        return 1 if self.count("FAIL") else 0


# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------


def unit_installed(unit):
    return sh(["systemctl", "cat", unit])[0] == 0


def unit_sample(unit):
    _, active = sh(["systemctl", "is-active", unit])
    _, restarts = sh(["systemctl", "show", "-p", "NRestarts", "--value", unit])
    _, started = sh(["systemctl", "show", "-p", "ExecMainStartTimestampMonotonic", "--value", unit])
    return {
        "active": active.strip(),
        "restarts": int(restarts.strip() or 0) if restarts.strip().isdigit() else 0,
        "started": started.strip(),
    }


def check_services(report, stable_seconds):
    units = ESSENTIAL_UNITS + OPTIONAL_UNITS
    first = {}
    for unit in units:
        if not unit_installed(unit):
            if unit in ESSENTIAL_UNITS:
                report.add("FAIL", "service %s" % unit, "not installed")
            else:
                report.add("SKIP", "service %s" % unit, "not installed")
            continue
        first[unit] = unit_sample(unit)
    if stable_seconds and first:
        print("   (watching the services for %d seconds to catch crash loops...)" % stable_seconds, flush=True)
        time.sleep(stable_seconds)
    for unit, before in first.items():
        after = unit_sample(unit) if stable_seconds else before
        if after["active"] != "active":
            if unit in OPTIONAL_UNITS and after["active"] in ("inactive",):
                report.add("PASS", "service %s" % unit, "finished (it only runs at boot)")
            else:
                report.add("FAIL", "service %s" % unit, "is %s" % after["active"])
        elif after["started"] != before["started"] or after["restarts"] != before["restarts"]:
            report.add("FAIL", "service %s" % unit, "restarted during the check (crash loop?)")
        elif after["restarts"] > 0:
            report.add("WARN", "service %s" % unit,
                       "running, but systemd counts %d automatic restart(s) since it was started" % after["restarts"])
        else:
            report.add("PASS", "service %s" % unit, "running, no restarts")


# --------------------------------------------------------------------------
# I2C
# --------------------------------------------------------------------------


def read_i2c_byte(address):
    """Read one byte (what the speaker's own services do all day). None if it fails."""
    if have("i2cget"):
        rc, out = sh(["i2cget", "-y", "1", "0x%02x" % address])
        if rc == 0 and out.strip().startswith("0x"):
            return int(out.strip(), 16)
        return None
    try:
        from smbus2 import SMBus  # type: ignore

        with SMBus(1) as bus:
            return bus.read_byte(address)
    except Exception:
        return None


def check_i2c(report):
    value = read_i2c_byte(0x20)
    if value is None:
        report.add("FAIL", "buttons chip 0x20", "no answer on I2C bus 1 (wiring, address strap, or I2C is off)")
    elif (value & 0x3F) != 0x3F:
        low = [str(bit) for bit in range(6) if not value & (1 << bit)]
        report.add("WARN", "buttons chip 0x20", "answers (0x%02x) but button bit(s) %s read as pressed: held down or stuck?"
                   % (value, ",".join(low)))
    else:
        report.add("PASS", "buttons chip 0x20", "answers, all 6 buttons read released (0x%02x)" % value)
    value = read_i2c_byte(0x21)
    if value is None:
        report.add("FAIL", "LED chip 0x21", "no answer on I2C bus 1")
    else:
        report.add("PASS", "LED chip 0x21", "answers (0x%02x)" % value)
    # The NFC reader is NOT probed: its thread polls it all day and a stray read could confuse it.
    ok, text = recent_log("smart_speaker", "6 hours ago")
    if not ok:
        report.add("SKIP", "NFC reader", "controller log not readable here (run with sudo)")
    elif "PN532 initialized successfully" in text:
        report.add("PASS", "NFC reader", "the controller log says the PN532 started")
    else:
        report.add("WARN", "NFC reader", "no 'PN532 initialized' line in the controller log of the last 6 hours")


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------


def recent_log(unit, since):
    rc, out = sh(["journalctl", "-u", unit, "--since", since, "--no-pager", "-o", "short-iso"], timeout=30)
    if rc != 0 or "not seeing messages from other users" in out:
        return False, ""
    return True, out


def check_logs(report, minutes=10):
    total = 0
    readable = False
    for unit in ("smart_speaker", "smart_speaker_server", "smart_speaker_health", "mopidy"):
        ok, text = recent_log(unit, "%d min ago" % minutes)
        if ok:
            readable = True
            hits = text.count("Traceback")
            total += hits
            if hits:
                report.add("FAIL", "log %s" % unit, "%d traceback(s) in the last %d minutes" % (hits, minutes))
    for path in ("/var/log/smart_speaker/controller.log", "/var/log/smart_speaker_server.log",
                 "/var/log/smart_speaker_health.log", "/var/log/smart_speaker_wifi.log"):
        if os.access(path, os.R_OK):
            readable = True
            rc, out = sh(["tail", "-n", "300", path])
            hits = out.count("Traceback")
            if hits:
                report.add("WARN", "log file %s" % os.path.basename(path),
                           "%d traceback(s) in its last 300 lines (may be old)" % hits)
    if not readable:
        report.add("SKIP", "recent errors in the logs", "logs not readable by this user (run with sudo)")
    elif total == 0:
        report.add("PASS", "recent errors in the logs", "no tracebacks in the last %d minutes" % minutes)


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------


def check_audio(report, beep_uri=None):
    try:
        mpd = MPDSocket(timeout=3)
        status = mpd.status()
        report.add("PASS", "Mopidy (MPD, port 6600)", "answers, state=%s" % status.get("state", "?"))
    except MPDError as exc:
        report.add("FAIL", "Mopidy (MPD, port 6600)", str(exc))
        mpd = None

    rc, out = sh(["aplay", "-l"])
    card = pick_card(out) if rc == 0 else None
    if card is None:
        report.add("FAIL", "sound card", "aplay -l shows no card")
    else:
        report.add("PASS", "sound card", "card %s" % card)
        rc, out = sh(["amixer", "-c", str(card), "sget", "PCM"])
        if rc == 0:
            report.add("PASS", "volume control 'PCM'", "present, now %s%%" % parse_amixer_percent(out))
        else:
            report.add("FAIL", "volume control 'PCM'", "missing on card %s: the volume buttons would do nothing" % card)

    rc, out = sh("aplay -L 2>/dev/null | grep -x feedback")
    if rc == 0:
        report.add("PASS", "audio setup", "the 'feedback' sound path exists (/etc/asound.conf is in place)")
    else:
        report.add("WARN", "audio setup", "no 'feedback' sound path: /etc/asound.conf is not the shared-audio version yet")

    if beep_uri and mpd is not None:
        beep_over_music(report, mpd, beep_uri)
    if mpd is not None:
        mpd.close()


def beep_over_music(report, mpd, uri):
    sound = os.path.join(REPO, "Main", "assets", "sounds", "swipe.wav")
    try:
        mpd.command("clear")
        mpd.command("add", uri)
        mpd.command("play")
        time.sleep(4)
        before = to_float(mpd.status().get("elapsed"))
        rc, out = sh(["aplay", "-q", "-D", "feedback", sound], timeout=15)
        time.sleep(1)
        status = mpd.status()
        after = to_float(status.get("elapsed"))
        mpd.command("stop")
        if rc != 0:
            report.add("FAIL", "beep over music", "aplay failed: %s" % out.strip()[:200])
        elif status.get("state") != "play" or after <= before:
            report.add("FAIL", "beep over music", "the music stopped or stalled when the beep played")
        else:
            report.add("PASS", "beep over music", "the beep played and the music kept going (did you hear both?)")
    except MPDError as exc:
        report.add("FAIL", "beep over music", str(exc))


def check_mopidy_reads(report):
    paths = [os.path.join(REPO, "Main", "local_files", "recordings"),
             os.path.join(REPO, "Main", "local_files", "uploads")]
    for path in paths:
        if not os.path.exists(path):
            report.add("WARN", "mopidy can read %s" % os.path.basename(path), "the folder does not exist yet")
            continue
        if is_root():
            argv = as_user("mopidy", ["test", "-r", path])
        elif sh(["sudo", "-n", "true"])[0] == 0:
            argv = ["sudo", "-n", "-u", "mopidy", "test", "-r", path]
        else:
            report.add("SKIP", "mopidy can read %s" % os.path.basename(path), "needs sudo")
            continue
        x_argv = argv[:-2] + ["-x", path]
        if sh(argv)[0] == 0 and sh(x_argv)[0] == 0:
            report.add("PASS", "mopidy can read %s" % os.path.basename(path), "yes")
        else:
            report.add("FAIL", "mopidy can read %s" % os.path.basename(path),
                       "no: recordings and uploads would not play through Mopidy")


# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------


def check_clock(report):
    rc, out = sh(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "Timezone", "-p", "TimeUSec"])
    info = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    year = time.localtime().tm_year
    if year < 2025:
        report.add("FAIL", "clock", "the year is %d: the Pi has no clock battery and has not synced yet" % year)
    elif info.get("NTPSynchronized") != "yes":
        report.add("WARN", "clock", "not synced with the internet yet (quiet hours and daily limit use this clock)")
    else:
        report.add("PASS", "clock", "synced, time zone %s" % info.get("Timezone", "?"))


# --------------------------------------------------------------------------
# The speaker's API and data
# --------------------------------------------------------------------------


def api_get(path, timeout=5):
    with urllib.request.urlopen(API + path, timeout=timeout) as response:
        return json.load(response)


def fetch_data():
    """The three things the app edits, in a form that is easy to compare."""
    chips = api_get("/chips")
    library = api_get("/library")
    parental = api_get("/settings/parental")
    return {
        "chips": {item["id"]: item for item in chips},
        "library": {item["id"]: item for item in library},
        "parental": parental,
    }


def digest(obj):
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def check_api(report):
    try:
        status = api_get("/status")
        if status.get("connected") is True:
            report.add("PASS", "speaker API /status", "answers%s" % (
                ", storage=%s" % status["storage"] if "storage" in status else ""))
        else:
            report.add("WARN", "speaker API /status", "answers, but not connected=true: %s" % status)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        report.add("FAIL", "speaker API /status", "no answer at %s (%s)" % (API, exc))
        return
    try:
        data = fetch_data()
        report.add("PASS", "speaker data", "%d chips, %d songs (chips %s, library %s, parental %s)" % (
            len(data["chips"]), len(data["library"]),
            digest(data["chips"]), digest(data["library"]), digest(data["parental"])))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        report.add("FAIL", "speaker data", "could not read the data: %s" % exc)


def save_data(report, path):
    try:
        data = fetch_data()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        report.add("FAIL", "data snapshot", "the API did not answer: %s" % exc)
        return False
    data["taken"] = now_iso()
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
    os.chmod(path, 0o600)
    report.add("PASS", "data snapshot", "saved %d chips and %d songs to %s" % (
        len(data["chips"]), len(data["library"]), path))
    return True


def compare_data(report, path):
    try:
        with open(path) as handle:
            before = json.load(handle)
    except (OSError, ValueError) as exc:
        report.add("SKIP", "data compared with the snapshot", "cannot read %s (%s)" % (path, exc))
        return
    try:
        now = fetch_data()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        report.add("FAIL", "data compared with the snapshot", "the API did not answer: %s" % exc)
        return
    problems, notes = diff_data(before, now)
    for note in notes:
        report.add("WARN", "data compared with the snapshot", note)
    if problems:
        for problem in problems:
            report.add("FAIL", "data compared with the snapshot", problem)
    else:
        report.add("PASS", "data compared with the snapshot",
                   "same %d chips, %d songs and parental settings as at %s" % (
                       len(now["chips"]), len(now["library"]), before.get("taken", "?")))


def diff_data(before, now):
    """Return (problems, notes). A changed song_name alone is a note: the new
    storage looks the name up from the song, so a stale name gets fixed."""
    problems, notes = [], []
    for kind in ("chips", "library"):
        old, new = before.get(kind, {}), now.get(kind, {})
        for item_id in sorted(set(old) - set(new)):
            problems.append("%s: %s is missing now" % (kind, item_id))
        for item_id in sorted(set(new) - set(old)):
            problems.append("%s: %s is new" % (kind, item_id))
        for item_id in sorted(set(old) & set(new)):
            if old[item_id] == new[item_id]:
                continue
            fields = sorted(k for k in set(old[item_id]) | set(new[item_id])
                            if old[item_id].get(k) != new[item_id].get(k))
            if kind == "chips" and fields == ["song_name"]:
                notes.append("chip %s: song_name changed from %r to %r (the name is now taken from the song)" % (
                    item_id, old[item_id].get("song_name"), new[item_id].get("song_name")))
            else:
                problems.append("%s %s changed in: %s" % (kind, item_id, ", ".join(fields)))
    if before.get("parental") != now.get("parental"):
        problems.append("parental settings are different")
    return problems, notes


# --------------------------------------------------------------------------
# The two-hour soak
# --------------------------------------------------------------------------


def read_meminfo():
    info = {}
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                info[key] = int(value.split()[0])
    except OSError:
        pass
    return info


def throttled_flags():
    if not have("vcgencmd"):
        return None
    rc, out = sh(["vcgencmd", "get_throttled"])
    match = re.search(r"0x([0-9a-fA-F]+)", out)
    return int(match.group(1), 16) if match else None


def temperature():
    if not have("vcgencmd"):
        return None
    rc, out = sh(["vcgencmd", "measure_temp"])
    match = re.search(r"([\d.]+)", out)
    return float(match.group(1)) if match else None


def watch(seconds, interval, log_path):
    """Print one line per interval, and a summary of the whole run at the end."""
    started = time.time()
    first = {u: unit_sample(u) for u in ESSENTIAL_UNITS if unit_installed(u)}
    min_mem, max_temp, ever_throttled = None, 0.0, 0
    rows = []
    print("Watching for %d seconds, one line every %d seconds. Ctrl-C stops early." % (seconds, interval))
    handle = open(log_path, "a") if log_path else None
    try:
        while time.time() - started < seconds:
            mem = read_meminfo().get("MemAvailable", 0) // 1024
            temp = temperature()
            flags = throttled_flags()
            load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
            states = {u: unit_sample(u) for u in first}
            restarts = sum(1 for u, s in states.items()
                           if s["started"] != first[u]["started"] or s["restarts"] != first[u]["restarts"])
            down = [u for u, s in states.items() if s["active"] != "active"]
            min_mem = mem if min_mem is None else min(min_mem, mem)
            if temp:
                max_temp = max(max_temp, temp)
            if flags:
                ever_throttled |= flags
            line = "%s  mem_free=%dMB  temp=%s  load=%.2f  throttled=%s  restarted=%d  down=%s" % (
                now_iso(), mem, ("%.1fC" % temp) if temp else "?", load,
                ("0x%x" % flags) if flags is not None else "?", restarts, ",".join(down) or "none")
            print(line, flush=True)
            rows.append(line)
            if handle:
                handle.write(line + "\n")
                handle.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped early.")
    finally:
        if handle:
            handle.close()
    print("")
    print("Soak summary: lowest free memory %s MB, hottest %.1f C, throttle flags ever set: 0x%x (0x0 is good)" % (
        min_mem, max_temp, ever_throttled))
    last = {u: unit_sample(u) for u in first}
    bad = [u for u in first if last[u]["started"] != first[u]["started"] or last[u]["restarts"] != first[u]["restarts"]]
    print("Services restarted during the run: %s" % (", ".join(bad) or "none"))
    return 1 if bad or ever_throttled & 0x7 else 0


# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["services", "i2c", "audio", "api", "data", "logs", "clock"],
                        help="run just one group of checks")
    parser.add_argument("--stable-seconds", type=int, default=0,
                        help="watch the services this long to catch restarts (default: 0)")
    parser.add_argument("--save-data", metavar="FILE", help="save the chips/library/settings for later comparison")
    parser.add_argument("--compare-data", metavar="FILE", help="compare the data with a saved snapshot")
    parser.add_argument("--beep-over-music", metavar="URI",
                        help="play this link (a local file is best), then a beep, and check the music kept going")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="soak mode: sample every --interval seconds")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--log", metavar="FILE", help="with --watch: also append the lines to this file")
    args = parser.parse_args()

    if args.watch:
        return watch(args.watch, args.interval, args.log)

    report = Report()
    print("Smart Speaker quick check, %s" % now_iso())

    def wanted(group):
        return args.only in (None, group)

    if args.only == "data":
        if args.save_data:
            return 0 if save_data(report, args.save_data) else 1
        check_api(report)
        return report.summary()

    if wanted("services"):
        check_services(report, args.stable_seconds)
    if wanted("i2c"):
        check_i2c(report)
    if wanted("audio"):
        check_audio(report, args.beep_over_music)
        check_mopidy_reads(report)
    if wanted("api"):
        check_api(report)
    if args.compare_data:
        compare_data(report, args.compare_data)
    if args.save_data:
        save_data(report, args.save_data)
    if wanted("logs"):
        check_logs(report)
    if wanted("clock"):
        check_clock(report)
    return report.summary()


if __name__ == "__main__":
    sys.exit(main())
