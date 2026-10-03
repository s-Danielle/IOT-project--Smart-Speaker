"""Shared helpers for the scripts in scripts/pi.

Standard library only, so they run on the Pi's system Python without
installing anything. Used by spotify_check.py, pi_smoke_test.py and
pi_install_audio.py.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time

# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------


def _colour_on(stream=sys.stdout):
    return stream.isatty() and os.environ.get("NO_COLOR") is None


_CODES = {"green": "32", "red": "31", "yellow": "33", "blue": "34", "bold": "1", "dim": "2"}


def paint(text, colour, stream=sys.stdout):
    if not _colour_on(stream):
        return text
    return "\033[%sm%s\033[0m" % (_CODES[colour], text)


def status_word(word):
    """PASS / WARN / FAIL / SKIP coloured when printing to a terminal."""
    colours = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "dim", "INFO": "blue"}
    return paint(word, colours.get(word, "bold"))


# --------------------------------------------------------------------------
# Running commands
# --------------------------------------------------------------------------


def sh(cmd, timeout=20, input_text=None):
    """Run a command (list, or string run through the shell).

    Returns (returncode, combined stdout+stderr). Never raises:
    127 means "command not found", 124 means "timed out".
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout
    except FileNotFoundError:
        return 127, "command not found: %s" % (cmd if isinstance(cmd, str) else cmd[0])
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss: %s" % (timeout, cmd)
    except Exception as exc:  # pragma: no cover - defensive
        return 1, "error running %s: %s" % (cmd, exc)


def have(program):
    return shutil.which(program) is not None


def is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def as_user(user, argv):
    """Prefix argv so it runs as another user (only works as root)."""
    if is_root() and have("runuser"):
        return ["runuser", "-u", user, "--"] + list(argv)
    return list(argv)


# --------------------------------------------------------------------------
# Tiny MPD client (Mopidy speaks the MPD protocol on port 6600)
# --------------------------------------------------------------------------


class MPDError(Exception):
    pass


class MPDAck(MPDError):
    """The server answered 'ACK [code@n] {command} message'."""

    _RE = re.compile(r"^ACK \[(\d+)@(\d+)\] \{(.*?)\} ?(.*)$")

    def __init__(self, code, command, message, raw):
        super().__init__(raw)
        self.code = code
        self.command = command
        self.message = message
        self.raw = raw

    @classmethod
    def parse(cls, text):
        match = cls._RE.match(text)
        if match:
            return cls(int(match.group(1)), match.group(3), match.group(4), text)
        return cls(0, "", text, text)


def _mpd_quote(arg):
    return '"' + str(arg).replace("\\", "\\\\").replace('"', '\\"') + '"'


class MPDSocket:
    """Just enough of the MPD protocol to add a URI, play it and read status."""

    def __init__(self, host="127.0.0.1", port=6600, timeout=5.0):
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise MPDError("cannot connect to MPD at %s:%s (%s)" % (host, port, exc))
        self.sock.settimeout(timeout)
        self.reader = self.sock.makefile("rb")
        greeting = self.reader.readline().decode("utf-8", "replace").strip()
        if not greeting.startswith("OK MPD"):
            raise MPDError("unexpected greeting from %s:%s: %r" % (host, port, greeting))
        self.version = greeting[len("OK MPD "):]

    def command(self, name, *args):
        """Send one command; return the reply as a list of (key, value)."""
        line = " ".join([name] + [_mpd_quote(a) for a in args]) + "\n"
        try:
            self.sock.sendall(line.encode("utf-8"))
            pairs = []
            while True:
                raw = self.reader.readline()
                if not raw:
                    raise MPDError("connection closed by MPD")
                text = raw.decode("utf-8", "replace").rstrip("\n")
                if text == "OK":
                    return pairs
                if text.startswith("ACK"):
                    raise MPDAck.parse(text)
                if ": " in text:
                    key, value = text.split(": ", 1)
                    pairs.append((key, value))
        except (socket.timeout, OSError) as exc:
            raise MPDError("MPD I/O problem: %s" % exc)

    def status(self):
        return dict(self.command("status"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# Parsing ALSA tool output
# --------------------------------------------------------------------------

_APLAY_CARD = re.compile(r"^card (\d+): (\S+) \[(.*?)\], device (\d+): (.*)$")


def parse_aplay_l(text):
    """Parse `aplay -l` into [{'card', 'id', 'name', 'device', 'desc'}]."""
    cards = []
    for line in text.splitlines():
        match = _APLAY_CARD.match(line.strip())
        if match:
            cards.append(
                {
                    "card": int(match.group(1)),
                    "id": match.group(2),
                    "name": match.group(3),
                    "device": int(match.group(4)),
                    "desc": match.group(5),
                }
            )
    return cards


def pick_card(aplay_text, preferred="seeed2micvoicec"):
    """Card number to use: the ReSpeaker HAT if present, else card 0, else None."""
    cards = parse_aplay_l(aplay_text)
    for card in cards:
        if preferred in card["id"] or preferred in card["name"]:
            return card["card"]
    if cards:
        return cards[0]["card"]
    return None


def parse_amixer_percent(text):
    """First '[NN%]' in `amixer sget` output, as an int (or None)."""
    match = re.search(r"\[(\d+)%\]", text)
    return int(match.group(1)) if match else None


# --------------------------------------------------------------------------
# Reading the Mopidy log
# --------------------------------------------------------------------------


def read_mopidy_log(since=None, max_lines=4000):
    """Return (ok, text, note). `since` is a 'YYYY-MM-DD HH:MM:SS' string.

    Tries the systemd journal first, then /var/log/mopidy/mopidy.log.
    """
    notes = []
    if have("journalctl"):
        cmd = ["journalctl", "-u", "mopidy", "--no-pager", "-o", "short-iso"]
        if since:
            cmd += ["--since", since]
        else:
            cmd += ["-n", str(max_lines)]
        rc, out = sh(cmd, timeout=30)
        if rc == 0 and "not seeing messages from other users" not in out:
            return True, out, "systemd journal"
        if "not seeing messages from other users" in out:
            notes.append("journal not readable by this user (run with sudo for the log analysis)")
        else:
            notes.append("journalctl failed (rc=%s)" % rc)
    log_path = "/var/log/mopidy/mopidy.log"
    if os.access(log_path, os.R_OK):
        try:
            with open(log_path, "r", errors="replace") as handle:
                lines = handle.readlines()[-max_lines:]
            return True, "".join(lines), log_path
        except OSError as exc:
            notes.append("cannot read %s: %s" % (log_path, exc))
    return False, "", "; ".join(notes) or "no Mopidy log found"


# --------------------------------------------------------------------------
# Error messages -> what they mean -> what to do
# (the same table is written up in docs/SPOTIFY.md)
# --------------------------------------------------------------------------

SIGNATURES = [
    {
        "id": "login5_invalid_credentials",
        "pattern": r"INVALID_CREDENTIALS|login5.*invalid",
        "meaning": "Spotify rejected Mopidy's login for streaming (reported since 2026-08-10, mopidy-spotify #437).",
        "advice": "Browsing works but nothing plays. Try the credentials.json workaround in docs/SPOTIFY.md; if it still fails the cause is upstream, so log it.",
    },
    {
        "id": "login5_503",
        "pattern": r"login5.*(503|Service Unavailable)|503 Service Unavailable",
        "meaning": "A Spotify-side problem reported on 2026-09-29 (librespot #1771).",
        "advice": "Nothing to do locally. Re-test later and log the date.",
    },
    {
        "id": "web_api_unauthorized",
        "pattern": r"\b401\b|Unauthorized|invalid_grant|refresh[ _]token|re-?authori[sz]e",
        "meaning": "The Spotify Web API login expired or was revoked (it lasts about 6 months).",
        "advice": "Re-authorize at mopidy.com/ext/spotify and update client_id/client_secret.",
    },
    {
        "id": "web_api_forbidden",
        "pattern": r"\b403\b|Forbidden",
        "meaning": "The developer app's owner may have lost Premium, or Spotify's Feb 2026 limits apply.",
        "advice": "Check the owner's Premium and the Spotify developer dashboard.",
    },
    {
        "id": "web_api_rate_limited",
        "pattern": r"\b429\b|Too Many Requests|rate.?limit",
        "meaning": "Spotify's rate limit.",
        "advice": "Wait a while and avoid repeated lookups.",
    },
    {
        "id": "spotify_plugin_missing",
        "pattern": r'no element "?spotifyaudiosrc|spotifyaudiosrc.*(not found|missing|unavailable)',
        "meaning": "The gst-plugin-spotify plugin is missing, or built for another CPU.",
        "advice": "Install the matching build and check with: gst-inspect-1.0 spotifyaudiosrc",
    },
    {
        "id": "illegal_instruction",
        "pattern": r"Illegal instruction",
        "meaning": "A program was built for a newer CPU than this Pi has.",
        "advice": "Install the build that matches this Pi (pi_report.sh records the CPU and OS).",
    },
    {
        "id": "alsa_busy",
        "pattern": r"Device or resource busy|audio open error",
        "meaning": "Something else holds the sound card (the shared audio setup may be missing).",
        "advice": "Check /etc/asound.conf and that only one program opens the card directly.",
    },
    {
        "id": "alsa_permission",
        "pattern": r"Permission denied.*(snd|alsa|pcm)|cannot open audio device",
        "meaning": "A user is not allowed to use the sound card.",
        "advice": "Check that iot-proj and mopidy are both in the 'audio' group.",
    },
    {
        "id": "audio_xrun",
        "pattern": r"xrun|underrun",
        "meaning": "The audio stream starved (dropouts).",
        "advice": "Note the CPU and memory use; a busy Pi Zero 2 W can cause this.",
    },
    {
        "id": "gstreamer_resource_not_found",
        "pattern": r"Resource not found|GStreamer error",
        "meaning": "GStreamer could not open the stream (often the symptom of a login or plugin problem).",
        "advice": "Look at the other lines around it for the real cause.",
    },
]

# One grep -E pattern for pi_report.sh and quick filtering.
LOG_FILTER_PATTERN = (
    r"login5|INVALID_CREDENTIALS|\b401\b|\b403\b|\b429\b|spotifyaudiosrc|xrun|underrun|"
    r"Traceback|ERROR|CRITICAL"
)


def mask_secrets(text):
    """Hide long token-like strings and values of secret-looking keys."""
    text = re.sub(
        r"(?i)((?:password|passwd|secret|token|api[_-]?key|auth[_-]?data|refresh[_-]?token|access[_-]?token)[A-Za-z_]*\s*[=:]\s*).*",
        r"\1********",
        text,
    )
    text = re.sub(r"[A-Za-z0-9_+/=\-]{40,}", "<masked>", text)
    return text


def classify_log(text):
    """Match log text against SIGNATURES.

    Returns [{'id', 'count', 'example', 'meaning', 'advice'}], most frequent first.
    """
    found = []
    lines = text.splitlines()
    for sig in SIGNATURES:
        regex = re.compile(sig["pattern"], re.IGNORECASE)
        hits = [line for line in lines if regex.search(line)]
        if hits:
            found.append(
                {
                    "id": sig["id"],
                    "count": len(hits),
                    "example": mask_secrets(hits[-1].strip())[:240],
                    "meaning": sig["meaning"],
                    "advice": sig["advice"],
                }
            )
    found.sort(key=lambda item: -item["count"])
    return found


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------


def now_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")
