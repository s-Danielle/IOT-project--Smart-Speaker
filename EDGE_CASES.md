# Smart Speaker - Edge Cases

This document outlines edge cases that are handled by the Smart Speaker system, demonstrating device robustness.

---

## NFC Chip Handling

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 1 | Unknown/new chip scanned | Auto-registers chip with default name, notifies user to assign song via app |
| 2 | Same chip scanned twice | Ignores duplicate scan, plays "same chip" feedback sound |
| 3 | Chip scanned during recording | Blocks action, plays blocked sound, continues recording |
| 4 | Chip has no song assigned | Loads chip (enables recording), blocks playback until song assigned |
| 5 | Chip references deleted song | Server cascades delete - clears chip assignment automatically |

## Button Interactions

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 6 | Record button held exactly 3 seconds | Starts recording (threshold check with `RECORD_HOLD_DURATION`) |
| 7 | Record button released before 3 seconds | Cancels countdown, does not start recording |
| 8 | Play/Pause pressed with no chip loaded | Blocks action, plays blocked sound |
| 9 | Stop long-press triggered multiple times | `_stop_long_press_triggered` flag prevents repeated execution. It is cleared whenever the button is up, in every state, so it can never swallow the next press |
| 10 | Volume buttons during recording | Blocks action, plays blocked sound |

## Audio Playback

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 11 | Mopidy connection lost mid-playback | Auto-reconnects via `_execute()` wrapper with retry logic |
| 12 | Spotify track slow to load (buffering) | Waits up to 20 seconds (`MAX_WAIT_FOR_PLAYBACK`; a song normally starts in about 3.4 s), then stops Mopidy, shows an error and goes back to idle |
| 13 | Track ends naturally | Detects via `_check_playback_finished()`, returns to IDLE_CHIP_LOADED |
| 14 | Brief playback interruption (<2s) | Ignores transient stops (`MIN_PLAYBACK_DURATION` check) |

## Voice Recording

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 15 | Recording canceled (Stop button) | Deletes temp file, restores previous state (PLAYING resumes) |
| 16 | Recording started while music playing | Pauses music, tracks state, resumes on cancel |
| 17 | Special characters in chip name | Sanitizes filename to alphanumeric only |

## Parental Controls

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 18 | Quiet hours span midnight (21:00-07:00) | Correctly detects overnight range with time comparison logic |
| 19 | Volume exceeds parental limit | Caps volume immediately (checked every 2s, on play/resume, and on volume up) |
| 20 | Chip in blacklist | Blocks scan, plays blocked sound |
| 21 | Whitelist mode enabled | Only allows chips explicitly in whitelist |
| 22 | Daily usage limit reached | Blocks new playback (Play, resume, voice, latest recording and voice jokes alike); counts only the time music really played, not the wait for a song to load (resets daily) |

## Recording Limits

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 23 | Insufficient disk space before recording | Checks free space (`MIN_DISK_SPACE_MB`), blocks if below threshold |
| 24 | Recording exceeds max duration | Auto-saves after `MAX_RECORDING_DURATION` (5 minutes default) |

## Network & Connectivity

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 25 | No WiFi at boot (not configured, or the router is slow) | Starts AP mode ("SmartSpeaker-Setup") after 30 seconds. If nobody is connected to the hotspot, it tries the saved network again every 2 minutes |
| 26 | Health LED status indication | Shows green (OK), blue blink (no server), red (hardware fail) |

## Hardware Resilience

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 27 | I2C device communication errors | Tracks consecutive failures, marks failed after threshold (5 errors) |
| 28 | Mopidy returns unexpected state | Uses cached state, logs warning, continues operation |

---

## Failures that used to hang or go silent

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 29 | Mopidy refuses a link ("directory or file not found") | `AudioPlayer.play_uri()` says so; the speaker shows an error at once and stays idle (it used to show PLAYING over silence for a minute) |
| 30 | A song is accepted but never starts | After `MAX_WAIT_FOR_PLAYBACK` Mopidy is stopped (so it cannot start late), an error is shown, the speaker goes back to idle and no usage is counted |
| 31 | NFC reader missing or loose at boot | The speaker still starts (buttons, app and music work). The NFC thread retries every 5 s and logs once a minute |
| 32 | Speech service unreachable | A voice command gives up after `PTT_TRANSCRIBE_TIMEOUT` (8 s) instead of freezing the controller |
| 33 | PTT button stuck down | Treated as let go after `PTT_MAX_HOLD` (10 s): the mic is released and the music restored |
| 34 | A button is held down when a program starts | The LED code never writes the button pins low, so the button does not stay "pressed" |
| 35 | Several programs light the LEDs at once | They share one record of the pin states, so no program switches off another one's light |
| 36 | `pyalsaaudio` is missing | The controller still starts; the volume buttons do nothing and an error is logged |
| 37 | The sound card powers up loud | The volume is lowered to `VOLUME_DEFAULT` or the parental limit at start-up, never raised |
| 38 | The server (root) creates the recordings folder | It hands `recordings` and `uploads` to the speaker's user, so recordings can be saved |
| 39 | The Spotify login or lookup fails | Mopidy now logs Mopidy-Spotify's messages and the system log survives a reboot, so the cause can be read afterwards (`docs/SPOTIFY.md`) |
| 40 | Power is cut, or the program crashes, while the data file is being saved | The new content is written to a temporary file and renamed over the real one, and the previous version is kept as `server_data.json.bak`. A half-written file can no longer replace the good one |
| 41 | The data file is damaged or missing (hand editing, a full SD card) | The server puts the last good copy (`.bak`) back at start-up (or on the next read), logs `[STORAGE]`, and keeps the damaged file as `server_data.json.corrupt-<time>` (the newest 3). If there is no good copy it starts empty and keeps the damaged file |
| 42 | A chip that was deleted in the app came back after a restart | The old `config/tags.json` is imported only on the very first run, not at every start |
| 43 | A chip is given a song that is not in the library | The server answers 400 and leaves the chip alone (it used to store a dead link, and the chip then played nothing) |
| 44 | A song is renamed | Every chip that uses it shows the new name (the name always comes from the song) |
| 45 | The app sends a setting of the wrong kind (`"volume_limit": "loud"`, a time like `25:00`) | The server answers 400 with the reason, and nothing is saved |
| 46 | A chip number in lower case (older tools wrote it that way) | Chip numbers are compared without regard to case, so it is the same chip |
| 47 | The app asks for today's usage on a new day | It reports 0 seconds without rewriting the data file (it used to rewrite the whole file) |
| 48 | A chip is tapped | The controller asks the server about that one chip (`GET /chips/lookup?uid=`) and gets the chip with its song link. It used to download the whole chip list and the whole library on every tap. A server that cannot be reached is an error (the chip is not re-registered), and an unknown chip is registered |
| 49 | SQLite: the program is killed in the middle of a save | A save is all or nothing (write-ahead log, every save forced to the card). 250 random kills of a writing program, with saves of 1 and of 40 rows, left the database sound every time. (A real power cut is tested on the speaker, `BRINGUP.md` step 7) |
| 50 | SQLite: the database file is damaged | It checks itself at start-up (integrity check). If it fails, the damaged files are kept as `server_data.db.corrupt-<time>` and the copy `server_data.db.bak` (made at start-up and once a day, so up to a day old) is put back. With no good copy it starts empty and keeps the damaged files |
| 51 | SQLite: a song is deleted while chips use it | The database clears those chips' links itself; a chip can never point at a song that is not there |
| 52 | SQLite: the same chip number in another case | The database allows each number once, whatever its case |
| 53 | Moving the data from JSON to SQLite (and back) | Done by the server at start-up when `SPEAKER_STORAGE` changes. The new copy is built under another name and compared row by row with the old one before it is put in place; a mismatch undoes it and the old copy keeps being used. Repeated chip numbers or ids, chips pointing at missing songs, and entries of the wrong kind are cleaned up and listed in the log. The old copy is kept under a dated name |
| 54 | Two programs save to the SQLite database at the same moment | The second waits (up to 5 seconds) instead of failing with "database is locked" |
| 55 | The controller is stuck in its loop (the process exists, nothing happens) | It rewrites `/run/smart_speaker/status.json` every second with a clock that cannot be fooled by a wrong date. After 20 seconds without a new write the health light blinks red and `/health` answers 503. Systemd alone cannot tell (it only knows the process exists) |
| 56 | The controller stopped or is restarting | Its status folder is removed with it, so `/status` says "not running" at once, and the app does not show the last song as still playing |
| 57 | A song is accepted but a Spotify problem keeps it from playing | The status keeps `last_play` (`failed` with Mopidy's reason, or the wait that ran out), so the app can say so without anyone reading logs. A later good play clears it |
| 58 | A website open in a browser on your network tries to change the speaker (reboot, delete a chip, change the parental limit) | The speaker no longer answers with `Access-Control-Allow-Origin: *`, so other sites cannot read it, and every change needs the `X-Speaker-Token` header, which a site cannot add without the speaker's permission (its preflight is refused with 403) |
| 59 | Another device on the network sends a change without the token, or with a wrong one | 401, nothing changes, and one `[SECURITY]` line is logged (at most one per device per 30 seconds). The token is compared in constant time and is never logged |
| 60 | Someone sends a very large request (a 2 GB "upload", a huge JSON body) | Refused up front with 413 and not read: 64 KB for JSON, 8 KB for the WiFi form, 30 MB for a song |
| 61 | The speaker sets up WiFi from a phone that just joined the hotspot | The WiFi setup routes are open while the hotspot is up, so no token is needed; everything else (reboot, forget WiFi, logs) still is |
| 62 | The token cannot be saved (the program folder is read-only) | The server logs an error and keeps a token nobody can read, so changes from other devices are refused until it is fixed. The controller and health monitor, on the speaker itself, are unaffected |
| 63 | `/debug/run-main` (started a second controller next to the service, fighting it for the buttons and the sound card) | Removed |
| 64 | The app's Developer Tools run `git pull` or `git status` | The server runs as root; it now runs git as the owner of the program folder (`sudo -u iot-proj -H git ...`), so git does not refuse over "dubious ownership" and does not leave root-owned files in the repository for the next `pi_update.sh` to trip over |
| 65 | `/tmp` is full or read-only, so the shared LED file fails | A light change falls back to a private copy and logs once. It used to raise out of `set_light()` and end the controller's main loop |
| 66 | A request body that is not JSON, not an object, or has a bad `Content-Length` (on any route) | 400 with the reason. Before, some routes dropped the connection with a traceback in the log |
| 67 | A user submits the WiFi setup form at the moment the 2-minute retry fires | The retry asks the server (over localhost) whether the setup page is joining a network and waits if so; it no longer tears the hotspot down or puts it back in the middle of the user's connect |
| 68 | A chip with no song, or a blocked chip, is tapped and Play pressed | Not recorded as a failed play: `/health` and the app only warn when Mopidy actually refused the link or could not be reached |
| 69 | `SPEAKER_STORAGE=sqlite` and the database exists but cannot be opened (made by a newer version, disk error) | The server stops with a clear message instead of falling back to a JSON file that may be out of date. Set `SPEAKER_STORAGE=json` to move the data out of SQLite on purpose |
| 70 | Moving the data out of SQLite: the JSON is written but the database cannot be put aside | The new JSON file is removed again and the speaker carries on with the database, so there is never a second live copy |
| 71 | The web app is deployed for the first time, or the folder on the Pi is empty | `deploy_web.sh` keeps a previous app only if it has an `index.html`, so the first deploy works and `--undo` can never swap an empty folder in |

---

## References

- Button timing constants: `Main/config/settings.py`
- Recording limits: `Main/config/settings.py` (`MAX_RECORDING_DURATION`, `MIN_DISK_SPACE_MB`)
- State machine logic: `Main/core/controller.py`
- Parental controls: `Main/core/controller.py` (`_check_quiet_hours`, `_check_chip_allowed`, `_check_daily_limit`)
- Daily usage tracking: `Main/server.py` (`get_daily_usage`, `add_daily_usage`)
- Hardware health: `Main/utils/hardware_health.py`
- LEDs and their shared state: `Main/hardware/leds.py`, `Main/ui/lights.py`
- WiFi setup mode: `Main/wifi_provisioner.py`, `Main/hardware/wifi_manager.py`
- Spotify problems and how they were debugged: `docs/SPOTIFY.md`
