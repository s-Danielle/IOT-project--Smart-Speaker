"""Tests for the helper scripts in scripts/pi.

These tests only call pure Python functions, talk to a fake Mopidy on a localhost
socket, and syntax-check the shell scripts. They never run a Pi script or any
system command (systemctl, sudo, aplay, journalctl...).

Run from the repo root:   python -m pytest tests -q
"""

import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PI_SCRIPTS = REPO / "scripts" / "pi"
sys.path.insert(0, str(PI_SCRIPTS))

import ini_edit  # noqa: E402
import pi_common  # noqa: E402
import pi_install_audio  # noqa: E402
import pi_smoke_test  # noqa: E402
import spotify_check  # noqa: E402

# --------------------------------------------------------------------------
# ini_edit: changes only the lines it means to change
# --------------------------------------------------------------------------

LIVE_CONF = """\
# Mopidy config for the speaker
[core]
cache_dir = $XDG_CACHE_DIR/mopidy

[audio]
# old value
mixer = software
output = autoaudiosink

[mpd]
enabled = true
connection_timeout = 60

[http]
hostname = 127.0.0.1

[spotify]
enabled = true
client_id = ID-SHOULD-STAY-SECRET
client_secret = SECRET-SHOULD-STAY-SECRET
bitrate = 160
"""

REFERENCE_CONF = """\
[audio]
mixer = none
output = alsasink device=default

[mpd]
hostname = 127.0.0.1
port = 6600
connection_timeout = 86400

[file]
enabled = true
media_dirs =
    /home/iot-proj/music
    /home/iot-proj/IOT-project--Smart-Speaker/Main/local_files/recordings

[spotify]
client_id = PLACEHOLDER
client_secret = PLACEHOLDER
"""


def apply_ref(text=LIVE_CONF):
    return ini_edit.apply_sections(text, REFERENCE_CONF, ["audio", "mpd", "file"])


def test_ini_edit_sets_the_wanted_values():
    new = apply_ref()
    assert ini_edit.read_section(new, "audio")["mixer"] == ["none"]
    assert ini_edit.read_section(new, "audio")["output"] == ["alsasink device=default"]
    mpd = ini_edit.read_section(new, "mpd")
    assert mpd["connection_timeout"] == ["86400"]
    assert mpd["port"] == ["6600"]
    assert mpd["hostname"] == ["127.0.0.1"]
    assert mpd["enabled"] == ["true"]  # an existing key we don't touch stays


def test_ini_edit_adds_a_missing_section_with_a_list():
    new = apply_ref()
    file_section = ini_edit.read_section(new, "file")
    assert file_section["enabled"] == ["true"]
    assert file_section["media_dirs"] == [
        "/home/iot-proj/music",
        "/home/iot-proj/IOT-project--Smart-Speaker/Main/local_files/recordings",
    ]


def test_ini_edit_never_touches_the_spotify_section():
    new = apply_ref()
    assert ini_edit.read_section(new, "spotify") == ini_edit.read_section(LIVE_CONF, "spotify")
    # byte for byte
    old_block = LIVE_CONF[LIVE_CONF.index("[spotify]"):]
    assert old_block in new


def test_ini_edit_keeps_comments_and_other_sections():
    new = apply_ref()
    assert "# Mopidy config for the speaker" in new
    assert "# old value" in new
    assert "[http]\nhostname = 127.0.0.1" in new
    assert "cache_dir = $XDG_CACHE_DIR/mopidy" in new


def test_ini_edit_is_idempotent():
    once = apply_ref()
    assert apply_ref(once) == once


def test_ini_edit_replaces_a_multiline_value_and_keeps_the_next_key():
    text = "[file]\nmedia_dirs =\n    /a\n    /b\nenabled = true\n"
    new = ini_edit.set_values(text, "file", {"media_dirs": ["/x"]})
    assert new == "[file]\nmedia_dirs = /x\nenabled = true\n"
    again = ini_edit.set_values(text, "file", {"media_dirs": ["/x", "/y"]})
    assert again == "[file]\nmedia_dirs =\n    /x\n    /y\nenabled = true\n"


def test_ini_edit_inserts_before_the_blank_line_that_ends_a_section():
    text = "[mpd]\nenabled = true\n\n[http]\nx = 1\n"
    new = ini_edit.set_values(text, "mpd", {"port": "6600"})
    assert new == "[mpd]\nenabled = true\nport = 6600\n\n[http]\nx = 1\n"


def test_ini_edit_handles_a_file_without_a_final_newline():
    new = ini_edit.set_values("[audio]\nmixer = software", "audio", {"mixer": "none"})
    assert new == "[audio]\nmixer = none\n"


def test_ini_edit_diff_shows_no_neighbouring_secret_lines():
    new = apply_ref()
    diff = ini_edit.unified_diff(LIVE_CONF, new, "mopidy.conf")
    assert "SECRET-SHOULD-STAY-SECRET" not in diff
    assert "ID-SHOULD-STAY-SECRET" not in diff
    assert "+mixer = none" in diff


# --------------------------------------------------------------------------
# pi_install_audio: the pure parts
# --------------------------------------------------------------------------

ASOUND_REF = (REPO / "services" / "audio" / "asound.conf").read_text()


def test_render_asound_leaves_card_0_alone():
    assert pi_install_audio.render_asound(ASOUND_REF, 0) == ASOUND_REF
    assert pi_install_audio.render_asound(ASOUND_REF, None) == ASOUND_REF


def test_render_asound_points_at_another_card_only_in_real_lines():
    new = pi_install_audio.render_asound(ASOUND_REF, 2)
    real = [l for l in new.splitlines() if not l.lstrip().startswith("#")]
    assert 'pcm "hw:2,0"' in "\n".join(real)
    assert "card 2" in "\n".join(real)
    assert 'hw:0,0"' not in "\n".join(real)
    # the explanatory comments keep their original wording
    assert [l for l in new.splitlines() if l.lstrip().startswith("#")] == \
        [l for l in ASOUND_REF.splitlines() if l.lstrip().startswith("#")]


def test_pyalsaaudio_requirement_comes_from_requirements_txt():
    text = (REPO / "requirements.txt").read_text()
    assert pi_install_audio.pyalsaaudio_requirement(text) == "pyalsaaudio==0.11.0"
    assert pi_install_audio.pyalsaaudio_requirement("") == "pyalsaaudio==0.11.0"
    assert pi_install_audio.pyalsaaudio_requirement("a==1\npyalsaaudio==9.9.9\n") == "pyalsaaudio==9.9.9"


def test_hat_script_detection(tmp_path):
    quiet = tmp_path / "quiet"
    quiet.write_text("#!/bin/sh\n# nothing about asound.conf here? it is in a comment: /etc/asound.conf\nmodprobe x\n")
    loud = tmp_path / "loud"
    loud.write_text("#!/bin/sh\ncp /etc/voicecard/a.conf /etc/asound.conf\n")
    assert pi_install_audio.hat_rewrites_asound([str(quiet)]) is None
    path, line = pi_install_audio.hat_rewrites_asound([str(quiet), str(loud)])
    assert path == str(loud) and "cp /etc/voicecard" in line
    assert pi_install_audio.hat_rewrites_asound([str(tmp_path / "missing")]) is None


# --------------------------------------------------------------------------
# pi_common
# --------------------------------------------------------------------------

APLAY = """\
**** List of PLAYBACK Hardware Devices ****
card 0: seeed2micvoicec [seeed-2mic-voicecard], device 0: bcm2835-i2s-wm8960-hifi wm8960-hifi-0 [bcm2835-i2s-wm8960-hifi wm8960-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
"""


def test_parse_aplay_and_pick_card():
    cards = pi_common.parse_aplay_l(APLAY)
    assert [c["card"] for c in cards] == [0, 1]
    assert cards[0]["id"] == "seeed2micvoicec"
    assert pi_common.pick_card(APLAY) == 0
    swapped = APLAY.replace("card 0: seeed2micvoicec", "card 3: seeed2micvoicec")
    assert pi_common.pick_card(swapped) == 3
    assert pi_common.pick_card("**** nothing ****") is None


def test_parse_amixer_percent():
    text = "Simple mixer control 'PCM',0\n  Front Left: Playback 120 [94%] [0.00dB]\n"
    assert pi_common.parse_amixer_percent(text) == 94
    assert pi_common.parse_amixer_percent("no volume here") is None


def test_mask_secrets():
    masked = pi_common.mask_secrets("client_secret = abc123\npassword: hunter2\nok line\n")
    assert "abc123" not in masked and "hunter2" not in masked and "ok line" in masked
    long_token = "x" * 60
    assert long_token not in pi_common.mask_secrets("token-ish " + long_token)


def test_classify_log_finds_the_known_spotify_problems():
    log = "\n".join([
        "2026-10-03T10:00:01 mopidy[1]: ERROR Unable to load audio item: FaultyRequest(INVALID_CREDENTIALS)",
        "2026-10-03T10:00:02 mopidy[1]: WARNING login5.spotify.com/v3/login returned 503 Service Unavailable",
        "2026-10-03T10:00:03 mopidy[1]: INFO normal line",
    ])
    found = {item["id"]: item for item in pi_common.classify_log(log)}
    assert "login5_invalid_credentials" in found
    assert "login5_503" in found
    assert found["login5_503"]["count"] == 1
    assert pi_common.classify_log("all quiet\n") == []


# --------------------------------------------------------------------------
# A fake Mopidy (MPD protocol) so spotify_check.run_case can run offline
# --------------------------------------------------------------------------


class FakeMopidy:
    """behaviour: good | add_fails | stops | stuck | never_plays

    Like the real Mopidy with a Spotify link: after `play` it keeps saying
    "state: stop" for `start_delay` seconds while the stream loads (3.4 s on the
    Pi), and `add` takes `add_delay` seconds (a real lookup, about 2 s).
    """

    def __init__(self, behaviour, start_delay=0.0, add_delay=0.0):
        self.behaviour = behaviour
        self.start_delay = start_delay
        self.add_delay = add_delay
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.commands = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.server.accept()
        reader = conn.makefile("rb")
        conn.sendall(b"OK MPD 0.19.0\n")
        played_at = None
        queue = []
        while True:
            raw = reader.readline()
            if not raw:
                return
            line = raw.decode().strip()
            self.commands.append(line)
            name = line.split(" ", 1)[0]
            if name == "clear":
                queue = []
                conn.sendall(b"OK\n")
            elif name == "add":
                if self.behaviour == "add_fails":
                    conn.sendall(b"ACK [50@0] {add} No such song\n")
                else:
                    time.sleep(self.add_delay)
                    queue.append(line)
                    conn.sendall(b"OK\n")
            elif name == "play":
                played_at = time.monotonic()
                conn.sendall(b"OK\n")
            elif name == "stop":
                played_at = None
                conn.sendall(b"OK\n")
            elif name == "status":
                reply = ""
                if played_at is None:
                    reply = "state: stop\n"
                else:
                    age = time.monotonic() - played_at - self.start_delay  # time since the audio really started
                    if age < 0 or self.behaviour == "never_plays":
                        reply = "state: stop\n"  # still loading, or never loads
                    elif self.behaviour == "stops" and age > 1.2:
                        reply = "state: stop\n"
                    elif self.behaviour == "stuck":
                        reply = "state: play\nelapsed: 0.000\n"
                    else:
                        reply = "state: play\nelapsed: %.3f\n" % max(0.0, age - 0.3)
                conn.sendall((reply + "OK\n").encode())
            else:
                conn.sendall(b"ACK [5@0] {} unknown command\n")


@pytest.fixture(autouse=True)
def no_journal(monkeypatch):
    monkeypatch.setattr(spotify_check, "read_mopidy_log", lambda since=None, max_lines=4000: (False, "", "test"))


def run_with(behaviour, timeout=6, start_delay=0.0, add_delay=0.0):
    fake = FakeMopidy(behaviour, start_delay=start_delay, add_delay=add_delay)
    mpd = pi_common.MPDSocket("127.0.0.1", fake.port, timeout=3)
    try:
        return spotify_check.run_case(mpd, "t", "spotify:track:abc", timeout=timeout, play_seconds=1.0), fake
    finally:
        mpd.close()


def result_row(label, outcome, **extra):
    row = {"label": label, "uri": "x", "expect_failure": False, "outcome": outcome, "lookup_s": None,
           "first_sound_s": None, "progress_s": 0.0, "needed_s": 4.0, "mpd_message": "", "state_trace": "",
           "causes": [], "log_note": "", "fail_after_s": 2.0}
    row.update(extra)
    return row


def test_mpd_client_quotes_and_reads_replies():
    fake = FakeMopidy("good")
    mpd = pi_common.MPDSocket("127.0.0.1", fake.port, timeout=3)
    assert mpd.version == "0.19.0"
    mpd.command("add", 'a "quoted" link')
    assert fake.commands[-1] == 'add "a \\"quoted\\" link"'
    with pytest.raises(pi_common.MPDError):
        pi_common.MPDSocket("127.0.0.1", 1, timeout=0.5)  # nothing listens on port 1
    mpd.close()


def test_run_case_pass():
    result, fake = run_with("good")
    assert result["outcome"] == "PASS"
    assert result["first_sound_s"] is not None
    assert fake.commands[:3] == ["clear", 'add "spotify:track:abc"', "play"]
    assert fake.commands[-1] == "stop"


def test_run_case_add_failed():
    result, _ = run_with("add_fails")
    assert result["outcome"] == "ADD_FAILED"
    assert "No such song" in result["mpd_message"]


def test_run_case_playback_stops_by_itself():
    result, _ = run_with("stops")
    assert result["outcome"] == "PLAYBACK_FAILED"
    assert result["state_trace"].endswith("play>stop")
    assert "stopped by itself" in spotify_check.explain(result)


def test_run_case_waits_for_a_slow_spotify_start():
    # Real Mopidy says "stop" for a few seconds while a Spotify song loads. The first version of the
    # script gave up after 1 s of that, then stopped the music itself (a split second of sound).
    result, fake = run_with("good", start_delay=1.6, add_delay=0.5)
    assert result["outcome"] == "PASS"
    assert result["lookup_s"] >= 0.5
    assert result["first_sound_s"] >= 2.0
    assert result["state_trace"] == "stop>play"
    assert fake.commands.count("stop") == 1  # only the script's own stop, after the pass


def test_run_case_gives_up_when_the_music_never_starts():
    result, _ = run_with("never_plays", timeout=1.5)
    assert result["outcome"] == "NO_PROGRESS"
    assert result["state_trace"] == "stop"
    assert "never said 'play'" in spotify_check.explain(result)


def test_explain_says_something_for_every_outcome():
    add = result_row("t", "ADD_FAILED", mpd_message="ACK [50@0] {add} directory or file not found")
    assert "refused to add" in spotify_check.explain(add)
    assert "directory or file not found" in spotify_check.explain(add)
    assert "broke" in spotify_check.explain(result_row("t", "CONNECT_FAILED"))
    stuck = result_row("t", "NO_PROGRESS", state_trace="stop>play")
    assert "never moved" in spotify_check.explain(stuck)
    errored = result_row("t", "PLAYBACK_FAILED", mpd_message="some error")
    assert "some error" in spotify_check.explain(errored)
    short = result_row("t", "PLAYBACK_FAILED", state_trace="play", progress_s=1.5)
    assert "only 1.5s" in spotify_check.explain(short)


def test_run_case_no_progress():
    result, _ = run_with("stuck", timeout=2.0)
    assert result["outcome"] == "NO_PROGRESS"
    assert result["first_sound_s"] is None


def test_overall_verdicts():
    ok = [result_row("local file (control)", "PASS"), result_row("known Spotify track", "PASS")]
    assert spotify_check.overall(ok)[0] == 0
    spotify_down = [result_row("local file (control)", "PASS"), result_row("known Spotify track", "PLAYBACK_FAILED")]
    assert spotify_check.overall(spotify_down)[0] == 1
    audio_down = [result_row("local file (control)", "NO_PROGRESS"), result_row("known Spotify track", "NO_PROGRESS")]
    assert spotify_check.overall(audio_down)[0] == 2


def test_overall_does_not_claim_a_local_song_played_when_none_was_tested():
    code, text = spotify_check.overall([result_row("known Spotify track", "PLAYBACK_FAILED")])
    assert code == 1
    assert "A local file plays" not in text
    assert "control" in text
    code, text = spotify_check.overall([result_row("known Spotify track", "PASS")])
    assert code == 0
    assert "control" in text


def test_control_tone_is_a_readable_wav(tmp_path):
    import wave

    path = tmp_path / "tone.wav"
    spotify_check.write_control_tone(str(path), seconds=0.5)
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert abs(handle.getnframes() / handle.getframerate() - 0.5) < 0.01


def test_control_tone_can_be_read_by_the_mopidy_user():
    uri = spotify_check.make_control_tone()
    try:
        assert uri.startswith("file:///")
        mode = os.stat(uri[len("file://"):]).st_mode
        assert mode & 0o044 == 0o044  # Mopidy runs as another user and must be able to read it
    finally:
        for path in spotify_check.TEMP_FILES:
            os.remove(path)
        spotify_check.TEMP_FILES.clear()


def test_smoke_test_waits_for_slow_music():
    fake = FakeMopidy("good", start_delay=1.0)
    mpd = pi_common.MPDSocket("127.0.0.1", fake.port, timeout=3)
    mpd.command("add", "x")
    mpd.command("play")
    assert pi_smoke_test.wait_for_music(mpd, seconds=8) is True
    mpd.close()


def test_smoke_test_gives_up_when_the_music_never_starts():
    fake = FakeMopidy("never_plays")
    mpd = pi_common.MPDSocket("127.0.0.1", fake.port, timeout=3)
    mpd.command("play")
    assert pi_smoke_test.wait_for_music(mpd, seconds=1.0) is False
    mpd.close()


def test_to_spotify_uri():
    assert spotify_check.to_spotify_uri("https://open.spotify.com/track/ABC123?si=xyz") == "spotify:track:ABC123"
    assert spotify_check.to_spotify_uri("https://open.spotify.com/intl-de/playlist/XYZ") == "spotify:playlist:XYZ"
    assert spotify_check.to_spotify_uri("spotify:album:1") == "spotify:album:1"
    assert spotify_check.to_spotify_uri("file:///a.mp3") == "file:///a.mp3"
    assert spotify_check.to_spotify_uri("") == ""


# --------------------------------------------------------------------------
# pi_smoke_test: the data comparison
# --------------------------------------------------------------------------


def snapshot():
    return {
        "chips": {
            "chipA": {"id": "chipA", "uid": "AAAA", "name": "A", "song_id": "s1", "song_name": "Old name"},
            "chipB": {"id": "chipB", "uid": "BBBB", "name": "B", "song_id": None, "song_name": None},
        },
        "library": {"s1": {"id": "s1", "name": "New name", "uri": "spotify:track:1"}},
        "parental": {"enabled": False, "volume_limit": 100},
    }


def test_diff_data_identical():
    assert pi_smoke_test.diff_data(snapshot(), snapshot()) == ([], [])


def test_diff_data_song_name_refresh_is_only_a_note():
    after = snapshot()
    after["chips"]["chipA"]["song_name"] = "New name"
    problems, notes = pi_smoke_test.diff_data(snapshot(), after)
    assert problems == []
    assert len(notes) == 1 and "song_name" in notes[0]


def test_diff_data_real_differences_are_problems():
    after = snapshot()
    del after["chips"]["chipB"]
    after["library"]["s2"] = {"id": "s2", "name": "x", "uri": "y"}
    after["chips"]["chipA"]["uid"] = "CHANGED"
    after["parental"]["volume_limit"] = 50
    problems, _ = pi_smoke_test.diff_data(snapshot(), after)
    text = "\n".join(problems)
    assert "chipB is missing" in text
    assert "s2 is new" in text
    assert "chips chipA changed in: uid" in text
    assert "parental" in text


def test_digest_ignores_key_order():
    assert pi_smoke_test.digest({"a": 1, "b": 2}) == pi_smoke_test.digest({"b": 2, "a": 1})


# --------------------------------------------------------------------------
# The hardware test scripts must use the same pins as the controller
# --------------------------------------------------------------------------


def settings_value(name):
    text = (REPO / "Main" / "config" / "settings.py").read_text()
    return int(re.search(r"^%s\s*=\s*(0x[0-9a-fA-F]+|\d+)" % name, text, re.M).group(1), 0)


def test_button_test_uses_the_controller_pins():
    import test_buttons

    expected = [
        ("Play/Pause", settings_value("BUTTON_PLAY_PAUSE_BIT")),
        ("Record", settings_value("BUTTON_RECORD_BIT")),
        ("Stop", settings_value("BUTTON_STOP_BIT")),
        ("Volume up (Vol+)", settings_value("BUTTON_VOLUME_UP_BIT")),
        ("Volume down (Vol-)", settings_value("BUTTON_VOLUME_DOWN_BIT")),
        ("Push-to-talk (PTT)", settings_value("BUTTON_PTT_BIT")),
    ]
    assert test_buttons.BUTTONS == expected
    assert test_buttons.ADDRESS == settings_value("PCF8574_ADDRESS")


def test_led_test_uses_the_controller_pins():
    import test_leds

    leds = (REPO / "Main" / "hardware" / "leds.py").read_text()
    light1 = tuple(int(x) for x in re.search(r"LIGHT1_PINS = \(([\d, ]+)\)", leds).group(1).split(","))
    light2 = tuple(int(x) for x in re.search(r"LIGHT2_PINS = \(([\d, ]+)\)", leds).group(1).split(","))
    by_number = {l[0]: l for l in test_leds.LIGHTS}
    assert tuple(bit for _, bit in by_number[1][2:5]) == light1
    assert tuple(bit for _, bit in by_number[2][2:5]) == light2
    # Light 3: B = 0x21 P6, G = 0x21 P7, R = 0x20 P6 (see set_light in leds.py)
    assert by_number[3][2:5] == ((0x21, 6), (0x21, 7), (0x20, 6))
    assert test_leds.LED_ADDRESS == int(re.search(r"LED_EXPANDER_ADDRESS = (0x[0-9a-fA-F]+)", leds).group(1), 16)
    assert test_leds.BUTTONS_RELEASED == 0x3F


# --------------------------------------------------------------------------
# The scripts are only syntax-checked here. They are NEVER run on this machine:
# they are written for the Pi and call things like systemctl, sudo and aplay.
# Their first real run is the preview mode on the Pi.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(p.name for p in PI_SCRIPTS.glob("*.sh")))
def test_shell_scripts_have_valid_syntax(name):
    # `bash -n` only reads the file and checks the syntax. It does not run anything in it.
    result = subprocess.run(["bash", "-n", str(PI_SCRIPTS / name)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
