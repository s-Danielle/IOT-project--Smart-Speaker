#!/usr/bin/env python3
"""Try a few links on the Pi's Mopidy and report what happened.

Run it ON THE PI (it makes sound, so YOU run it, not me):

    python3 /tmp/pi/spotify_check.py > /tmp/spotify.txt
    sudo python3 /tmp/pi/spotify_check.py > /tmp/spotify.txt   # adds the log analysis

Progress is shown on the screen. The results table and a ready-to-paste
entry for docs/SPOTIFY.md go to the output file.

For each link it clears Mopidy's queue, adds the link, plays it and checks the
status every half second. It stops each link after a few seconds of real
progress, so the speaker is loud for only about 5 seconds per link. TURN THE
SPEAKER VOLUME DOWN FIRST.

It changes nothing on the system. It only stops the current music and clears
Mopidy's queue.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pi_common import (  # noqa: E402
    MPDAck,
    MPDError,
    MPDSocket,
    as_user,
    classify_log,
    have,
    mask_secrets,
    now_iso,
    read_mopidy_log,
    sh,
    to_float,
)

DEFAULT_TRACK = "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"  # "Surprise", the repo's default library song
DEFAULT_LOCAL = "file:///home/iot-proj/lights.mp3"  # the repo's default local song
BOGUS_URI = "spotify:track:0000000000000000000000"
SPOTIFY_TYPES = ("track", "playlist", "album", "artist", "episode", "show")


def log(message):
    """Progress goes to stderr so it still shows when stdout is redirected."""
    print(message, file=sys.stderr, flush=True)


def to_spotify_uri(text):
    """Turn an open.spotify.com link into a spotify: URI (same rule as the app)."""
    text = (text or "").strip()
    if not text or text.startswith("spotify:"):
        return text
    parsed = urlparse(text)
    if parsed.netloc.endswith("open.spotify.com"):
        parts = [p for p in parsed.path.split("/") if p]
        # Links can start with /intl-xx/
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if len(parts) >= 2 and parts[0] in SPOTIFY_TYPES:
            return "spotify:%s:%s" % (parts[0], parts[1])
    return text


# --------------------------------------------------------------------------
# Facts about this Pi (read only)
# --------------------------------------------------------------------------


def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def gather_facts():
    facts = {}
    try:
        with open("/proc/device-tree/model", "rb") as handle:
            facts["model"] = handle.read().decode("utf-8", "replace").strip("\x00\n ")
    except OSError:
        facts["model"] = "unknown"
    rc, out = sh("uname -m")
    facts["arch"] = first_line(out)
    rc, out = sh("grep PRETTY_NAME /etc/os-release")
    facts["os"] = out.split("=", 1)[-1].strip().strip('"') if rc == 0 else "unknown"

    rc, out = sh(as_user("mopidy", ["mopidy", "--version"]), timeout=30)
    facts["mopidy"] = first_line(out) if rc == 0 else "not found (%s)" % first_line(out)

    rc, out = sh(["python3", "-m", "pip", "show", "mopidy-spotify"])
    version = ""
    for line in out.splitlines():
        if line.lower().startswith("version:"):
            version = line.split(":", 1)[1].strip()
    facts["mopidy_spotify"] = version or "not installed for system python3"

    plugin = "not found"
    if have("gst-inspect-1.0"):
        rc, out = sh(as_user("mopidy", ["gst-inspect-1.0", "spotifyaudiosrc"]), timeout=60)
        if rc == 0:
            plugin = "found"
            for line in out.splitlines():
                if re.match(r"\s*Version\s", line):
                    plugin = "found, " + line.strip()
                    break
    facts["gst_plugin_spotify"] = plugin
    rc, out = sh("dpkg -l 2>/dev/null | grep -i gst-plugin-spotify")
    if rc == 0 and out.strip():
        facts["gst_plugin_package"] = " ".join(out.split()[1:3])

    # Credentials file: size, age and owner only. Never its contents.
    creds = []
    for base in ("/var/lib/mopidy", os.path.expanduser("~")):
        rc, out = sh(
            ["find", base, "-maxdepth", "6", "-name", "credentials.json", "-printf",
             "%p|%s|%TY-%Tm-%Td|%u:%g|%m\\n"],
            timeout=20,
        )
        if rc == 0:
            for line in out.splitlines():
                if "|" in line:
                    path, size, day, owner, mode = line.split("|")
                    creds.append("%s (%s bytes, modified %s, owner %s, mode %s)" % (path, size, day, owner, mode))
    facts["credentials_file"] = creds or ["none found (or not readable by this user)"]
    return facts


# --------------------------------------------------------------------------
# One test
# --------------------------------------------------------------------------


def run_case(mpd, label, uri, timeout, play_seconds, expect_failure=False):
    result = {
        "label": label,
        "uri": uri,
        "expect_failure": expect_failure,
        "outcome": "",
        "first_sound_s": None,
        "progress_s": 0.0,
        "mpd_message": "",
        "state_trace": "",
        "causes": [],
        "log_note": "",
    }
    window_start = now_iso()
    started = time.monotonic()
    states = []
    try:
        mpd.command("clear")
        try:
            mpd.command("add", uri)
        except MPDAck as ack:
            result["outcome"] = "ADD_FAILED"
            result["mpd_message"] = ack.raw
            result["fail_after_s"] = round(time.monotonic() - started, 1)
            return finish_case(mpd, result, window_start)
        mpd.command("play")
        best = 0.0
        while True:
            elapsed_wall = time.monotonic() - started
            status = mpd.status()
            state = status.get("state", "?")
            elapsed = to_float(status.get("elapsed"))
            if not states or states[-1] != state:
                states.append(state)
            best = max(best, elapsed)
            if elapsed >= 0.5 and result["first_sound_s"] is None:
                result["first_sound_s"] = round(elapsed_wall, 1)
            if status.get("error"):
                result["mpd_message"] = status["error"]
            result["progress_s"] = round(best, 1)
            if best >= play_seconds:
                result["outcome"] = "PASS"
                break
            if state == "stop" and elapsed_wall > 1.0:
                result["outcome"] = "PLAYBACK_FAILED"
                result["fail_after_s"] = round(elapsed_wall, 1)
                break
            if status.get("error"):
                result["outcome"] = "PLAYBACK_FAILED"
                result["fail_after_s"] = round(elapsed_wall, 1)
                break
            if elapsed_wall > timeout:
                result["outcome"] = "NO_PROGRESS" if best < 0.5 else "PLAYBACK_FAILED"
                result["fail_after_s"] = round(elapsed_wall, 1)
                break
            time.sleep(0.5)
    except MPDAck as ack:
        # Mopidy answered, but refused a command (for example "play" on an empty queue).
        result["outcome"] = "PLAYBACK_FAILED"
        result["mpd_message"] = ack.raw
        result["fail_after_s"] = round(time.monotonic() - started, 1)
        return finish_case(mpd, result, window_start)
    except MPDError as exc:
        # The connection itself broke.
        result["outcome"] = "CONNECT_FAILED"
        result["mpd_message"] = str(exc)
        return result
    result["state_trace"] = ">".join(states)
    return finish_case(mpd, result, window_start)


def finish_case(mpd, result, window_start):
    try:
        mpd.command("stop")
    except MPDError:
        pass
    time.sleep(1.0)  # let the log catch up
    ok, text, note = read_mopidy_log(since=window_start)
    if ok:
        result["causes"] = classify_log(text)
    result["log_note"] = note if not ok else ""
    return result


def verdict_word(result):
    if result["outcome"] == "PASS":
        return "PASS"
    if result["expect_failure"]:
        return "FAILED AS EXPECTED"
    return result["outcome"].replace("_", " ")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def short_cause(result):
    if result["causes"]:
        return result["causes"][0]["id"]
    if result["outcome"] != "PASS" and result["mpd_message"]:
        return mask_secrets(result["mpd_message"])[:60]
    return ""


def render_table(results):
    rows = [("Test", "Result", "First sound", "Progress", "Likely cause in the log")]
    for result in results:
        first = "%.1fs" % result["first_sound_s"] if result["first_sound_s"] is not None else "-"
        rows.append(
            (
                result["label"],
                verdict_word(result),
                first,
                "%.1fs" % result["progress_s"],
                short_cause(result),
            )
        )
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    lines = []
    for index, row in enumerate(rows):
        lines.append("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
        if index == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def overall(results):
    by_label = {r["label"]: r for r in results}
    local = by_label.get("local file (control)")
    track = by_label.get("known Spotify track")
    if any(r["outcome"] == "CONNECT_FAILED" for r in results):
        return 2, "Could not talk to Mopidy at all. Check: systemctl status mopidy"
    if local is not None and local["outcome"] != "PASS":
        return 2, ("The local file did NOT play, so the problem is in the sound setup or Mopidy, "
                   "not (only) Spotify. Fix that first.")
    if track is not None and track["outcome"] != "PASS":
        return 1, "A local file plays but the Spotify track does not: the problem is Spotify-specific."
    if track is not None and track["outcome"] == "PASS":
        return 0, "The Spotify track plays."
    return 1, "No Spotify track result. Something was skipped."


def markdown_entry(facts, results, verdict_text, mpd_version, label):
    lines = []
    lines.append("### %s - %s (made by spotify_check.py)" % (now_iso(), label))
    lines.append("")
    lines.append("- Pi: %s, %s, %s" % (facts.get("model"), facts.get("os"), facts.get("arch")))
    lines.append("- Mopidy: %s. Mopidy-Spotify: %s. Spotify plugin: %s%s." % (
        facts.get("mopidy"), facts.get("mopidy_spotify"), facts.get("gst_plugin_spotify"),
        " (package %s)" % facts["gst_plugin_package"] if facts.get("gst_plugin_package") else ""))
    for line in facts.get("credentials_file", []):
        lines.append("- Credentials file: %s" % line)
    lines.append("- MPD protocol: %s" % mpd_version)
    lines.append("")
    lines.append("| Test | Link | Result | First sound | Progress |")
    lines.append("|---|---|---|---|---|")
    for result in results:
        first = "%.1fs" % result["first_sound_s"] if result["first_sound_s"] is not None else "-"
        lines.append("| %s | `%s` | %s | %s | %.1fs |" % (
            result["label"], result["uri"], verdict_word(result), first, result["progress_s"]))
    lines.append("")
    lines.append("**What the log said:**")
    seen = {}
    for result in results:
        for cause in result["causes"]:
            seen.setdefault(cause["id"], cause)
    if seen:
        for cause in seen.values():
            lines.append("- %s: %s `%s`" % (cause["id"], cause["meaning"], cause["example"]))
    else:
        notes = sorted({r["log_note"] for r in results if r["log_note"]})
        lines.append("- Nothing matched the known error messages." + (" (%s)" % "; ".join(notes) if notes else ""))
    lines.append("")
    lines.append("**Verdict:** %s" % verdict_text)
    lines.append("")
    lines.append("**What we tried:** _(write here)_")
    lines.append("")
    lines.append("**What happened / next step:** _(write here)_")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Choosing what to test
# --------------------------------------------------------------------------


def library_uris(port=8080):
    try:
        with urllib.request.urlopen("http://localhost:%d/library" % port, timeout=3) as response:
            return [item.get("uri", "") for item in json.load(response)]
    except (urllib.error.URLError, OSError, ValueError):
        return []


def local_path(uri):
    parsed = urlparse(uri)
    return unquote(parsed.path) if parsed.scheme == "file" else None


def ask(prompt, enabled):
    if not enabled:
        return ""
    try:
        print(prompt, end="", file=sys.stderr, flush=True)
        return to_spotify_uri(sys.stdin.readline())
    except (EOFError, KeyboardInterrupt):
        return ""


def build_cases(args, interactive):
    library = library_uris()
    track = args.track
    if not track:
        spotify_tracks = [u for u in library if u.startswith("spotify:track:")]
        track = spotify_tracks[0] if spotify_tracks else DEFAULT_TRACK

    local = args.local
    if not local:
        candidates = [u for u in library if u.startswith("file://")] + [DEFAULT_LOCAL]
        for candidate in candidates:
            path = local_path(candidate)
            if path and os.path.exists(path):
                local = candidate
                break

    album = args.album or ask("Paste a Spotify ALBUM link (Enter to skip): ", interactive)
    own = args.own_playlist or ask("Paste a PLAYLIST link that your account OWNS (Enter to skip): ", interactive)
    other = args.other_playlist or ask(
        "Paste a PLAYLIST link that someone ELSE owns (Enter to skip): ", interactive)

    cases = []
    if local:
        cases.append(("local file (control)", local, False))
    else:
        log("No local file found to use as the control. Pass one with --local file:///path/to/song.mp3")
    cases.append(("known Spotify track", track, False))
    if album:
        cases.append(("Spotify album", album, False))
    if own:
        cases.append(("Spotify playlist you own", own, False))
    if other:
        cases.append(("Spotify playlist someone else owns", other, False))
    cases.append(("made-up link (should fail)", args.bogus or BOGUS_URI, True))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6600)
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds to wait for each link")
    parser.add_argument("--play-seconds", type=float, default=4.0,
                        help="seconds of real progress that count as a pass")
    parser.add_argument("--track", help="Spotify track link or URI (default: from the library)")
    parser.add_argument("--album")
    parser.add_argument("--own-playlist")
    parser.add_argument("--other-playlist")
    parser.add_argument("--local", help="file:///path to a local song")
    parser.add_argument("--bogus", help="a link that should not exist")
    parser.add_argument("--no-ask", action="store_true", help="do not ask for album/playlist links")
    parser.add_argument("--yes", action="store_true", help="do not pause before the first sound")
    parser.add_argument("--label", default="check", help="short name for the log entry, e.g. 'baseline at 770ceae'")
    parser.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    args = parser.parse_args()

    interactive = sys.stdin.isatty() and not args.no_ask
    try:
        mpd = MPDSocket(args.host, args.port)
    except MPDError as exc:
        print("CONNECT FAILED: %s" % exc)
        print("Check: systemctl status mopidy")
        return 2

    log("Gathering facts about this Pi...")
    facts = gather_facts()
    cases = build_cases(args, interactive)

    log("")
    log("This will STOP whatever is playing and clear Mopidy's queue.")
    log("It plays about %d seconds from each of %d links. Turn the speaker volume DOWN." %
        (int(args.play_seconds) + 1, len(cases)))
    if not args.yes:
        for left in range(5, 0, -1):
            log("Starting in %d... (Ctrl-C to cancel)" % left)
            time.sleep(1)

    results = []
    try:
        for label, uri, expect_failure in cases:
            log("-> %s: %s" % (label, uri))
            result = run_case(mpd, label, uri, args.timeout, args.play_seconds, expect_failure)
            log("   %s%s" % (verdict_word(result),
                             " (first sound after %.1fs)" % result["first_sound_s"]
                             if result["first_sound_s"] is not None else ""))
            results.append(result)
            if result["outcome"] == "CONNECT_FAILED":
                break
    except KeyboardInterrupt:
        log("Cancelled.")
    finally:
        try:
            mpd.command("stop")
        except MPDError:
            pass
        mpd.close()

    code, verdict_text = overall(results)

    print("Spotify check on %s" % now_iso())
    print("Pi: %s | %s | %s" % (facts.get("model"), facts.get("os"), facts.get("arch")))
    print("Mopidy: %s | Mopidy-Spotify: %s | Spotify plugin: %s" % (
        facts.get("mopidy"), facts.get("mopidy_spotify"), facts.get("gst_plugin_spotify")))
    for line in facts.get("credentials_file", []):
        print("Credentials file: %s" % line)
    print("")
    print(render_table(results))
    print("")
    print("Verdict: %s" % verdict_text)
    print("")
    for result in results:
        if result["outcome"] != "PASS" and (result["causes"] or result["mpd_message"] or result["log_note"]):
            print("[%s]" % result["label"])
            if result["mpd_message"]:
                print("  Mopidy said: %s" % mask_secrets(result["mpd_message"]))
            for cause in result["causes"][:3]:
                print("  Log (%dx %s): %s" % (cause["count"], cause["id"], cause["example"]))
                print("    Meaning: %s" % cause["meaning"])
                print("    What to do: %s" % cause["advice"])
            if result["log_note"]:
                print("  Log note: %s" % result["log_note"])
            print("")
    print("---- paste this into docs/SPOTIFY.md (under 'Log') ----")
    print(markdown_entry(facts, results, verdict_text, mpd.version, args.label))

    if args.json:
        with open(args.json, "w") as handle:
            json.dump({"facts": facts, "results": results, "verdict": verdict_text, "exit_code": code},
                      handle, indent=2)
        log("Wrote %s" % args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
