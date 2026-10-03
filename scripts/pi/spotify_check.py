#!/usr/bin/env python3
"""Try a few links on the Pi's Mopidy and report what happened.

Run it ON THE PI (it makes sound, so YOU run it, not me):

    sudo python3 /tmp/pi/spotify_check.py --label "what this run is" > /tmp/spotify.txt

Without sudo it still works, but it can't read the date of the credentials file
or all of Mopidy's log.

Progress is shown on the screen. The results table and a ready-to-paste
entry for docs/SPOTIFY.md go to the output file.

For each link it clears Mopidy's queue, adds the link, plays it and checks the
status four times a second. A Spotify song takes several seconds to start (3.4
seconds were measured on this Pi) and Mopidy says "stop" all that time, so the
script waits up to --timeout seconds for the music to start moving. It stops
each link after a few seconds of real progress, so the speaker is loud for only
about 5 seconds per link. TURN THE SPEAKER VOLUME DOWN FIRST.

If there is no local song to use as the control, it writes a quiet 6-second
test tone to /tmp and deletes it at the end. It changes nothing else on the
system: it only stops the current music and clears Mopidy's queue.
"""

import argparse
import json
import math
import os
import re
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from urllib.parse import unquote, urlparse

sys.dont_write_bytecode = True  # a root run must not leave root-owned .pyc files in /tmp/pi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pi_common import (  # noqa: E402
    MPDAck,
    MPDError,
    MPDSocket,
    as_user,
    classify_log,
    have,
    is_root,
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
POLL_SECONDS = 0.25

TEMP_FILES = []  # files this run made; main() deletes them at the end


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
    if not creds:
        creds = ["none found"] if is_root() else ["not checked: run this script with sudo to look in /var/lib/mopidy"]
    facts["credentials_file"] = creds
    return facts


# --------------------------------------------------------------------------
# A local sound to compare Spotify with
# --------------------------------------------------------------------------


def write_control_tone(path, seconds=6.0, rate=22050, hz=440.0, level=0.2):
    """Write a quiet test tone, so there is always a local sound to compare Spotify with."""
    frames = int(seconds * rate)
    fade = max(1, int(0.1 * rate))
    samples = []
    for i in range(frames):
        edge = min(1.0, i / fade, (frames - 1 - i) / fade)
        samples.append(struct.pack("<h", int(32767 * level * edge * math.sin(2 * math.pi * hz * i / rate))))
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(samples))


def make_control_tone():
    """Make a test tone that Mopidy can read. Returns a file:// link, or None if it can't be made."""
    try:
        handle, path = tempfile.mkstemp(prefix="spotify_check_control_", suffix=".wav")
        os.close(handle)
        TEMP_FILES.append(path)  # so main() deletes it even if something below fails
        write_control_tone(path)
        os.chmod(path, 0o644)  # Mopidy runs as another user and must be able to read it
    except OSError:
        return None
    return "file://" + path


# --------------------------------------------------------------------------
# One test
# --------------------------------------------------------------------------


def run_case(mpd, label, uri, timeout, play_seconds, expect_failure=False):
    """Play one link and report what Mopidy did.

    `timeout` counts from the `play` command, not from the lookup. Mopidy keeps
    saying "stop" while a Spotify song loads, so "stop" only means failure
    once Mopidy has said "play" first.
    """
    result = {
        "label": label,
        "uri": uri,
        "expect_failure": expect_failure,
        "outcome": "",
        "lookup_s": None,
        "first_sound_s": None,
        "progress_s": 0.0,
        "needed_s": play_seconds,
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
            result["lookup_s"] = result["fail_after_s"]
            return finish_case(mpd, result, window_start)
        result["lookup_s"] = round(time.monotonic() - started, 1)
        mpd.command("play")
        play_sent = time.monotonic()
        seen_play = False
        best = 0.0
        while True:
            now = time.monotonic()
            since_play = now - play_sent
            status = mpd.status()
            state = status.get("state", "?")
            elapsed = to_float(status.get("elapsed"))
            if not states or states[-1] != state:
                states.append(state)
                result["state_trace"] = ">".join(states)
            if state == "play":
                seen_play = True
            best = max(best, elapsed)
            if elapsed >= 0.5 and result["first_sound_s"] is None:
                result["first_sound_s"] = round(now - started, 1)
            if status.get("error"):
                result["mpd_message"] = status["error"]
            result["progress_s"] = round(best, 1)
            if best >= play_seconds:
                result["outcome"] = "PASS"
                break
            if status.get("error"):
                result["outcome"] = "PLAYBACK_FAILED"
                result["fail_after_s"] = round(since_play, 1)
                break
            if seen_play and state == "stop":
                # It started, then stopped by itself before the time was up.
                result["outcome"] = "PLAYBACK_FAILED"
                result["fail_after_s"] = round(since_play, 1)
                break
            if since_play > timeout:
                result["outcome"] = "NO_PROGRESS" if best < 0.5 else "PLAYBACK_FAILED"
                result["fail_after_s"] = round(since_play, 1)
                break
            time.sleep(POLL_SECONDS)
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
    if result["outcome"] == "CONNECT_FAILED":
        return "CONNECT FAILED"
    if result["expect_failure"]:
        return "PLAYED (should not have)" if result["outcome"] == "PASS" else "FAILED AS EXPECTED"
    if result["outcome"] == "PASS":
        return "PASS"
    return result["outcome"].replace("_", " ")


def explain(result):
    """One plain sentence for every result that is not a pass."""
    outcome = result["outcome"]
    after = result.get("fail_after_s") or 0.0
    trace = result.get("state_trace") or "nothing"
    said = mask_secrets(result["mpd_message"]) if result["mpd_message"] else ""
    if outcome == "ADD_FAILED":
        return "Mopidy refused to add the link after %.1fs%s." % (after, ": " + said if said else "")
    if outcome == "CONNECT_FAILED":
        return "The connection to Mopidy broke%s." % (": " + said if said else "")
    parts = trace.split(">")
    if outcome == "NO_PROGRESS":
        if "play" in parts:
            return ("Mopidy said 'play' but the music never moved within %.1fs (what Mopidy reported over time: %s)."
                    % (after, trace))
        return ("Mopidy never said 'play' within %.1fs after the play command (what Mopidy reported over time: %s)."
                % (after, trace))
    if said:
        return "Mopidy reported an error %.1fs after the play command: %s." % (after, said)
    if "play" in parts and parts[-1] == "stop":
        return ("Mopidy started playing, then stopped by itself %.1fs after the play command (what Mopidy reported "
                "over time: %s). The music reached %.1fs, and %.0fs were needed."
                % (after, trace, result["progress_s"], result["needed_s"]))
    return ("The music reached only %.1fs of the %.0fs needed (what Mopidy reported over time: %s)."
            % (result["progress_s"], result["needed_s"], trace))


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def seconds(value):
    return "%.1fs" % value if value is not None else "-"


def short_cause(result):
    if result["causes"]:
        return result["causes"][0]["id"]
    if result["outcome"] != "PASS" and result["mpd_message"]:
        return mask_secrets(result["mpd_message"])[:60]
    if result["outcome"] not in ("PASS", "") and result["state_trace"]:
        return "Mopidy state: %s" % result["state_trace"]
    return ""


def render_table(results):
    rows = [("Test", "Result", "Lookup", "First sound", "Progress", "Likely cause in the log")]
    for result in results:
        rows.append(
            (
                result["label"],
                verdict_word(result),
                seconds(result["lookup_s"]),
                seconds(result["first_sound_s"]),
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


def legend(play_seconds):
    return ("Lookup: how long Mopidy took to accept (or refuse) the link. First sound: from sending the link until "
            "the music started moving (it includes the lookup). Progress: how far the music got; %.0fs counts as a pass."
            % play_seconds)


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
        if local is None:
            return 1, ("The Spotify track did not play. No local sound was tested as a control, so this can't tell "
                       "a Spotify problem from a sound problem yet.")
        return 1, "A local file plays but the Spotify track does not: the problem is Spotify-specific."
    if track is not None and track["outcome"] == "PASS":
        if local is None:
            return 0, "The Spotify track plays. (No local sound was tested as a control.)"
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
    lines.append("| Test | Link | Result | Lookup | First sound | Progress |")
    lines.append("|---|---|---|---|---|---|")
    for result in results:
        lines.append("| %s | `%s` | %s | %s | %s | %.1fs |" % (
            result["label"], result["uri"], verdict_word(result), seconds(result["lookup_s"]),
            seconds(result["first_sound_s"]), result["progress_s"]))
    lines.append("")
    lines.append("**What happened:**")
    problems = [r for r in results if r["outcome"] != "PASS"]
    if problems:
        for result in problems:
            lines.append("- %s: %s" % (result["label"], explain(result)))
    else:
        lines.append("- Everything played.")
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
    if not local:
        local = make_control_tone()
        if local:
            log("No local song found, so a quiet 6-second test tone is the control.")
        else:
            log("No local song found and a test tone could not be made. Pass a song with --local file:///path/to/song.mp3")

    album = args.album or ask("Paste a Spotify ALBUM link (Enter to skip): ", interactive)
    own = args.own_playlist or ask("Paste a PLAYLIST link that your account OWNS (Enter to skip): ", interactive)
    other = args.other_playlist or ask(
        "Paste a PLAYLIST link that someone ELSE owns (Enter to skip): ", interactive)

    cases = []
    if local:
        cases.append(("local file (control)", local, False))
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
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="seconds to wait for the music to start moving, counted after the lookup")
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
    parser.add_argument("--label", default="check", help="short name for the log entry, e.g. 'baseline at 45a4eae'")
    parser.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    args = parser.parse_args()

    interactive = sys.stdin.isatty() and not args.no_ask
    try:
        mpd = MPDSocket(args.host, args.port)
    except MPDError as exc:
        print("CONNECT FAILED: %s" % exc)
        print("Check: systemctl status mopidy")
        return 2

    if not is_root():
        log("Note: not running as root, so the credentials file and part of Mopidy's log can't be read. "
            "For the full check use: sudo python3 %s" % os.path.abspath(__file__))
    log("Gathering facts about this Pi...")
    facts = gather_facts()
    cases = build_cases(args, interactive)

    log("")
    log("This will STOP whatever is playing and clear Mopidy's queue.")
    log("It plays about %d seconds from each of %d links. Turn the speaker volume DOWN." %
        (int(args.play_seconds) + 1, len(cases)))

    results = []
    try:
        if not args.yes:
            for left in range(5, 0, -1):
                log("Starting in %d... (Ctrl-C to cancel)" % left)
                time.sleep(1)
        for label, uri, expect_failure in cases:
            log("-> %s: %s" % (label, uri))
            if uri.startswith("spotify:"):
                log("   (a Spotify song takes several seconds to start)")
            result = run_case(mpd, label, uri, args.timeout, args.play_seconds, expect_failure)
            log("   %s%s" % (verdict_word(result),
                             " (first sound after %.1fs)" % result["first_sound_s"]
                             if result["first_sound_s"] is not None else ""))
            if result["outcome"] != "PASS":
                log("   %s" % explain(result))
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
        for path in TEMP_FILES:
            try:
                os.remove(path)
            except OSError:
                pass

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
    print(legend(args.play_seconds))
    print("")
    print("Verdict: %s" % verdict_text)
    print("")
    for result in results:
        if result["outcome"] != "PASS":
            print("[%s]" % result["label"])
            print("  What happened: %s" % explain(result))
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
