# Changes since 4f466ad (7 July 2026)

## Features

### WiFi setup
- The setup hotspot (SmartSpeaker-Setup) opens whenever there is no network for 60 s, at boot or later. Before, it opened only at boot.
- While in setup mode with nobody connected, the speaker retries the saved network every 2 minutes.
- The setup page ends with a button, "My phone is back on WiFi – open the speaker". It looks for the speaker, then opens the web app. The app's wizard has the same button.
- The default speaker hostname is now `rpi2.local` (it was `smart-speaker-iot.local`).

### Web app and phone app
- The home screen shows the controller's state, the loaded chip, the volume and the minutes played today, refreshed every 4 s. It warns when the last song failed.
- Developer Tools and WiFi setup are hidden in the browser version.
- Fixed: an uploaded song created two library entries.
- Fixed: Developer Tools showed "Failed" for every WiFi connect.
- Fixed: closing the WiFi wizard early left the phone bound to the hotspot.
- Removed the "Run Main" action.
- Removed the unused Firebase (Analytics, Messaging) from the Android build.
- The web app is no longer tracked in git. `deploy_web.sh` keeps the previous version, and `--undo` swaps it back.

### Playing music
- A refused play command shows an error at once. The wait for playback to start went from 60 s to 20 s, and Mopidy is stopped on a timeout.
- Play, resume, the voice command "play", the latest recording and the easter eggs all go through one entry point. They all apply quiet hours, the daily limit and the volume cap. Before, some of them skipped these.
- Daily usage counts only time when Mopidy has confirmed playback and the microphone has not paused it.
- At start-up the volume is lowered to the default or the parental cap, and never raised.

### Buttons, voice and recording
- The speech request has an 8 s total time limit.
- Holding Push-to-Talk for more than 10 s counts as letting go.
- The microphone is released even when a voice command fails.
- Voice "clear" fixed: it keeps the chip id, accepts a 204 reply, and stops the music last.
- Stop button fixed: a second long press works, and no "blocked" beep on release.
- Fixed: the countdown sound cut off the "saved" chime.
- Recordings can be saved again (the folder had the wrong owner).

### Lights
- The red recording light is now shown while recording.
- The speaker light returns to the colour of the current state after a flash.
- All LEDs are switched off at boot and when the controller shuts down.
- A button held down at start-up no longer stays "pressed" until reboot.

### NFC
- A missing reader no longer blocks start-up. It retries every 5 s in the background.
- New lookup endpoint: `GET /chips/lookup?uid=`.

### Health and status
- `/health` returns `ok`, `problems`, `warnings`, `server` and `controller`, with HTTP 503 when something is wrong.
- `/status` shows what the speaker is doing and today's usage.
- The health light (Light 1) is driven by the freshness of the controller's status file, not by systemd.

### Data
- Storage is SQLite by default (it was a JSON file). Moving between the two is supported in both directions, and `db_export_json.py` exports to JSON.

## Technical enhancements

### Controller
- Rewritten with a monotonic clock for all timing.
- Takes its parts as options, so tests can drive it. `step()` runs one pass of the main loop.
- The controller writes `/run/smart_speaker/status.json` once a second and on every change.

### Audio
- Volume is set through the sound card's PCM control (`Mixer`, pyalsaaudio) and not through Mopidy.
- UI sounds play through `aplay`.
- `mic_session.py` makes sure the microphone is always released.
- Reference configs for ALSA dmix and Mopidy are in `services/audio/`.
- `AudioPlayer.play_uri()` returns whether Mopidy accepted the link, with the reason in `last_error`. A refused command is no longer treated as a lost connection.

### NFC
- Reading runs in its own thread (`nfc_service.py`), polling about 3 times per second (`NFC_TIMEOUT` 0.3 s).

### Lights
- All programs now share one LED state. It is kept in a small file in `/tmp` protected by `flock`, so a write by one program changes only its own light.
- Write errors are logged at most every 5 s.

### Server
- `server.py` reads and writes data only through `Main/storage/` (JSON and SQLite stores, with checked conversion between them).
- Idle connections are closed after 15 s.
- 4 worker threads, with a longer queue.
- Request bodies are limited: 64 KB for JSON, 8 KB for forms, 30 MB for uploads.
- Open CORS (`*`) is removed. One developer origin can be allowed with `SPEAKER_CORS_ORIGIN`.
- `/debug/run-main` is removed.
- Bad request bodies return 400 on every route.
- Successful `GET /status` and `GET /health` are no longer logged.
- If the database exists but cannot be opened, the server stops and does not fall back to old JSON.
- Replaced the `cgi` module, which Python 3.13 removed.
- Folders the server creates (recordings, uploads) now belong to the owner of the program folder, not root.
- Developer Tools run git as the owner of the program folder.

### WiFi
- The provisioner keeps running after boot, and stops its port-80 helper when setup is done.
- Time the setup page spends joining a network does not count as lost network.
- It finds `iwgetid` in `/usr/sbin` and falls back to NetworkManager for the SSID.

### Logs and services
- journald keeps its logs across reboots (capped at 40 MB), and the three logs systemd only appends to are rotated.
- Controller log: `/var/log/smart_speaker/controller.log`, which rotates itself.
- The health service uses the venv Python and runs unbuffered.
- Mopidy-Spotify's own log messages are enabled.

### Deployment
- `pi_install_system.sh` installs system files, with a preview, a backup and an undo.
- `pi_update.sh` only switches code. It keeps the deployed web app, restarts the WiFi service, and reports when `git fetch` fails.
- New Pi scripts: `pi_install_audio`, `pi_backup`, `pi_report`, `pi_smoke_test`, `spotify_check`, `test_buttons`, `test_leds`.
- Scripts are split into `scripts/dev` (runs on the laptop) and `scripts/pi` (runs on the Pi).

### Tests
- New `tests/` suite of about 30 files, using fakes for the Pi-only libraries. It covers storage, SQLite, the status file, WiFi, the recorder, the mic lock, LEDs, voice, actions and the Pi scripts.
- Removed the committed `Unit-tests/.venv` and other generated files.
