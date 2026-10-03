# What is wrong in the README

A list for whoever fixes the README. Delete this file when that is done. The README itself has not been changed. Line numbers are those of the README on the day this was written (2026-10-03), and the facts come from the code and from the Pi.

## The hardware

| Line | What the README says | What is true |
|---|---|---|
| 40 | Raspberry Pi 4/5 | A Raspberry Pi **Zero 2 W**: 2.4 GHz WiFi only (a 5 GHz-only network is invisible to it), about 415 MB of memory |
| 48 | 5V 3A USB-C power supply | The Zero 2 W has a micro-USB power port. Use a good 5 V supply of 2.5 A or more: a weak one causes random glitches |
| 41 | ReSpeaker 2-Mic Pi HAT | A ReSpeaker 2-Mic **v2.0** (TLV320AIC3x chip), loaded by `dtoverlay=respeaker-2mic-v2_0` in `/boot/firmware/config.txt`. There is no seeed-voicecard driver script on this Pi |
| 44 | RGB LEDs, common cathode, 3 | 3 LEDs are installed (confirmed Oct 3). Whether they are common cathode is still to be confirmed in BRINGUP step 4.3 |
| 64 | Wiring diagram | `assets/diagrams/wiring_diagram.png` shows a Pi Zero and **2** RGB LEDs. The code and the real build use 3 (Health, PTT and the divided Speaker LED). The picture needs redrawing |

## Software versions

| Line | What the README says | What is true |
|---|---|---|
| 239, 259, 278 | Python 3.7+ | The Pi has Python 3.13.5 and the code uses syntax from Python 3.10 (`str \| None`), so say 3.10+ |
| 258 | Raspberry Pi OS Bookworm | Debian 13 "trixie" (Raspberry Pi OS based on it), 64-bit |
| 260 | Mopidy 3.4+ | The Pi runs Mopidy 4.0.1, mopidy-mpd 4.0.0, Mopidy-Spotify 5.0.0 and gst-plugin-spotify 0.15.0-alpha.1 |
| (missing) | Nothing about Spotify login | Spotify needs a Premium account, a Web API login (https://auth.mopidy.com/spotify/, redone about every 6 months) and a separate streaming login. See `docs/SPOTIFY.md` |
| 249 | RPi.GPIO listed as a key library | No speaker code imports it (buttons and LEDs go through I2C). It is only in `requirements.txt` |

## Installing

| Line | What the README says | What is true |
|---|---|---|
| 289 | `pip3 install -r requirements.txt` | Raspberry Pi OS refuses system-wide pip installs, and the services run from the `venv` folder. Use `bash Main/setup.sh`, which makes the venv and installs into it (rewritten on the `pi/fixes` branch) |
| 302 | `cd Main && python3 main.py` | `cd Main && ../venv/bin/python main.py` (the system Python lacks the libraries). Stop the service first |
| 324-332 | Sudoers entries use `/bin/systemctl` and `/sbin/reboot` | On this system the paths are `/usr/bin/systemctl` and `/usr/sbin/reboot`. The health monitor also runs `systemctl restart smart_speaker_health`, which the list lacks. (`iot-proj` already has passwordless sudo on this Pi, so nothing fails today.) |
| 334-367 | Audio configuration by hand, "back up the seeed-voicecard `/etc/asound.conf`" | There is no `/etc/asound.conf` on this Pi. Use `scripts/pi/pi_install_audio.sh` (it previews, backs up and can undo), described in `BRINGUP.md`. The Mopidy part now also copies `[loglevels]` |
| 352 | merge `[audio]`, `[mpd]`, `[file]` | and `[loglevels]` |

## How it behaves

| Line | What the README says | What is true |
|---|---|---|
| 19, 3 | NFC tags "instantly play" music | A tap **loads** the chip (green flash, chime). **Play** starts it. (`USER_STORIES.md` already says this) |
| 377-384 | Button table, "Long Press (3s)" | Record: **hold 5 s** starts recording (`RECORD_HOLD_DURATION`), and a short press only saves while recording. Play/Pause: hold 2 s plays the latest recording. Stop: a short press stops or cancels (and unloads an idle chip), hold 3 s **unloads the chip**; it does not clear the song assignment (the voice command "clear" does that) |
| (missing) | Volume long presses | Hold Volume Up for 5 s to **reboot**, Volume Down for 5 s to **restart the services** (health monitor) |
| 388-394 | Four voice commands | Also: "shut up" (mute), "happy birthday", "play despacito", "what is our grade" and "kill yourself" / "reboot" (reboots the Pi). Wake phrases: "hi speaker", "hey speaker", "hi", "hey" |
| 427 | `/health` "Health check" | It returns `{}` today. A real one is planned |
| 420-461 | API endpoint list | Missing: `GET /usage/today`, `POST /usage/add`, `DELETE /chips/{id}/assignment`, `POST /chips`. The `/debug/*` endpoints have no password and the server allows requests from any website (planned fix: a token) |
| 522, 529 | Hardware log is `/var/log/smart_speaker.log` | The current code writes `/var/log/smart_speaker/controller.log` (it rotates itself). The old code on the Pi still uses `/var/log/smart_speaker.log` |
| 494 | It waits 30 s, then opens the hotspot | Still true, and now, if nobody is using the hotspot, it tries the saved network again every 2 minutes |
| 398-416 | LED table | "Blue blinking" appears twice for the health light (no server/internet, and AP mode). Check it against `Main/health_monitor.py` before keeping it |

## What is missing from the lists

| Line | Add |
|---|---|
| 153-233 | `Main/hardware/nfc_service.py`, `mic_session.py`, `chip_store.py`, `wifi_manager.py`, `captive_responder.py`, `health.py`, `Main/utils/`, `Main/setup.sh`, `scripts/pi/` (the helper scripts for testing and updating the Pi), `scripts/monitor_gpio.py`, `scripts/install-flutter.sh`, `tests/`, `docs/`, `BRINGUP.md`, `EDGE_CASES.md`, `pytest.ini` |
| 547-552 | `BRINGUP.md` (the checklist for bringing the Pi up), `docs/SPOTIFY.md` (how Spotify works here and the debugging log), `EDGE_CASES.md` |
| 146 | The project poster is still the blank template (a team job, not code) |
