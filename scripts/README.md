# scripts

Two folders, split by where the script runs.

## dev/ : run on the development machine

| Script | What it does |
|---|---|
| `push_to_pi.sh [user@host]` | Copies everything in `pi/`, plus the service files and `requirements.txt`, to `/tmp/pi` on the Pi. Changes nothing else on the Pi. |
| `deploy_web.sh [--undo] [user@host]` | Builds the Flutter web app and copies it to the Pi. `--undo` puts the previous one back. |
| `install_flutter.sh` | Installs the Flutter SDK (Arch-based Linux). |

## pi/ : run on the Pi

Every file here lands flat in `/tmp/pi` after `push_to_pi.sh`, and the scripts find each other by sitting in the same folder. Do not add subfolders here without changing `push_to_pi.sh` and the paths in `BRINGUP.md`.

**Install and update** (each has `--dry-run` and an undo)

| Script | What it does |
|---|---|
| `pi_install_system.sh` | Service files, the saved system log, log rotation. |
| `pi_install_audio.sh` | Shared sound card, and the Mopidy settings (`--mopidy-conf`). |
| `pi_update.sh` | Switches the code to a branch or tag, restarts, runs the quick check. |
| `pi_backup.sh` | Backs up the data and the system files the scripts change, and restores them. |
| `wifi_forget.sh` | Forgets the saved WiFi networks, to test the WiFi setup from the start. |

**Look and check** (read only, except where noted)

| Script | What it does |
|---|---|
| `pi_report.sh` | Collects facts about the Pi into one text file. |
| `pi_smoke_test.py` | Quick health check, data snapshot and comparison, long soak test. |
| `spotify_check.py` | Tries Spotify and local songs through Mopidy. Makes sound. |
| `db_export_json.py` | Checks the SQLite database and writes a readable JSON copy. |

**Hardware by hand** (run in front of the speaker)

| Script | What it does |
|---|---|
| `test_buttons.py` | Guided test of the 6 buttons. |
| `test_leds.py` | Guided test of the status lights. |
| `test_ptt.py`, `install_ptt_deps.sh` | Push-to-talk voice commands: install what they need, then test. |
| `monitor_gpio.py` | Prints GPIO 12 and 13 until Ctrl-C. |

**Helpers used by the others:** `pi_common.py`, `ini_edit.py`.

The automatic tests for these are in `tests/` (`test_pi_scripts.py`, `test_pi_install_system.py`).
