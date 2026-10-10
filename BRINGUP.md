# Bring-up checklist: from "device off" to "finished"

Tick the boxes as you go. This is the tick-box version of the plan, in the same style as [TESTING_WIFI_AND_WEB.md](TESTING_WIFI_AND_WEB.md).

**How it works**
- Commands are for the Pi unless the line says "on this computer".
- Anything that changes the Pi is a command **you** run. I only read.
- Every script that changes something has a preview (`--dry-run`) and an undo. Run the preview first and read it.
- When something fails, stop and tell me the lines it printed. Don't improvise a fix.
- Never paste `credentials.json`, the `SECRETS` file or `/etc/mopidy/mopidy.conf` anywhere.

The branch `pi/audio-stack` is on GitHub (pushed Oct 3). Push it again after any new commit here, because the Pi switches code by pulling from GitHub.

---

## Step 1: before power-on (the Pi is OFF, about 30 minutes)

- [ ] **1.1** Confirm you can push branches to GitHub, or tell me where to push.
- [ ] **1.2** *(Recommended, once, 30-60 minutes.)* Make a full copy of the SD card before any change. It's the undo for everything.
- [ ] **1.3** Power supply: 5 V rated 2.5 A or better. A weak supply causes random glitches.
- [ ] **1.4** Wiring against [assets/diagrams/wiring_diagram.png](assets/diagrams/wiring_diagram.png):
  - [ ] the HAT is fully seated
  - [ ] the two PCF8574 chips are set to **0x20** (buttons) and **0x21** (LEDs)
  - [ ] the NFC reader's mode switches are set to **I2C**
  - [ ] the I2C cable chain is intact
  - [ ] the NFC reader is on 5 V as drawn, with a common ground for buttons, LEDs and Pi
  - [ ] no stray wire strands or shorts
- [x] **1.5** LEDs: how many RGB LEDs are installed? The diagram says 2 (Connectivity on P0-2, Speaker on P3-5). The code drives 3 (Health, PTT and a split Speaker LED). Label each with tape and tell me. Note whether they're common-cathode and whether they have resistors.
  - **Answer (Oct 3): 3 LEDs are installed**, so the code is right and the wiring diagram is out of date. Which LED is which, and the colour order, are checked in 4.3.
- [ ] **1.6** Buttons: 6 buttons to ground, in this order: Play/Pause, Record, Stop, Vol+, Vol-, PTT. None stuck.
- [ ] **1.7** The speaker is on the HAT's 3.5 mm jack and powered over USB. The mic holes are uncovered.
- [ ] **1.8** Logistics: 4 NFC tags and the demo phone nearby. Tell me which **2.4 GHz** WiFi the Pi should join (the Zero 2 W can't use 5 GHz). If its old network is gone, we use the `SmartSpeaker-Setup` hotspot, which is itself test 1 in [TESTING_WIFI_AND_WEB.md](TESTING_WIFI_AND_WEB.md).
- [ ] **1.9** Answer these Spotify questions (see [docs/SPOTIFY.md](docs/SPOTIFY.md)):
  - What exactly went wrong last time? The error you saw, whether it was silence, a stall or a failure to start, roughly when, and any log or screenshot you kept.
  - Which Spotify account does the speaker use, and is its Premium active?
  - Where did `client_id` and `client_secret` come from: https://auth.mopidy.com/spotify/ (Mopidy's own app), or an app you made at developer.spotify.com? If it's your own app, whose account owns it, and is that account Premium?
  - When did you last authorize Mopidy-Spotify? (The Web API login expires about every 6 months.)
  - Did the Aug 13 `credentials.json` ever get copied to the Pi, and did playback work afterwards?
  - What kinds of Spotify links are in the library (tracks, albums, playlists, and whose playlists)?
  - Does anything else play on that account while the speaker does? Spotify allows one active stream per account.
  - **Update (Oct 3):** the old logs answer the first question (every Spotify tap on Sep 5 failed at the first step and the speaker sat silent for a minute; see [docs/SPOTIFY.md](docs/SPOTIFY.md)). The library holds only track links (seventh question: nothing to answer). The Aug 13 question is probably "yes, and it worked": `pi_report.sh` will confirm it from the date of the credentials file. The rest are still open.
- [ ] **1.10** Make sure one chip plays a **local file** (upload an MP3 in the app and assign it). It's the control for every Spotify test, and the backup for the demo.

---

## Step 2: power on and test the Pi as it is today (about 60 minutes)

The Pi runs old code: commit `45a4eae` from Jul 24, which is 4 commits behind GitHub's `main` (a read-only look on Oct 3 showed this). We want to know what works before we change anything.

**Where we are (Oct 3):** the Pi is on, on the same WiFi as this computer, and a Spotify song played fine on the old code. So 2.5 is now about measuring (how long a song takes to start, which kinds of link work) rather than finding a failure.

- [ ] **2.1** Power on and watch Light 1 for about 90 seconds (yellow pulse, then blue or green). Tell me anything odd, especially lights flickering or going dark every few seconds.
- [x] **2.2** *On this computer*, in the repo folder, copy the helper scripts to the Pi (it only writes `/tmp/pi` on the Pi). Use `rpi2.local`: plain `rpi2` does not resolve from this computer.
  ```
  scripts/pi/push_to_pi.sh iot-proj@rpi2.local
  ```
- [x] **2.3** On the Pi, collect the facts (sudo is only used to read root-only files and the Mopidy log; nothing is changed):
  ```
  sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt
  ```
- [ ] **2.4** *(skipped for now, Oct 3: we go on without it; do it after step 3 instead)* A quick physical test of what works today (10 minutes). Tell me pass or fail for each:
  - [ ] all 6 buttons
  - [ ] all 4 tags
  - [ ] play a Spotify chip and the local-file chip
  - [ ] Vol+ and Vol-
  - [ ] PTT
  - [ ] record and save
  - [ ] open the app
- [x] **2.5** Test Spotify. **Turn the speaker volume down first.** Nothing else may play on that Spotify account meanwhile.
  ```
  sudo python3 /tmp/pi/spotify_check.py --label "baseline at 45a4eae" > /tmp/spotify.txt
  ```
  It asks for an album link and two playlist links (one you own, one you don't). Press Enter to skip any of them. It counts down 5 seconds, then plays about 5 seconds from each link. The progress shows on screen and the results go to the file.

  **Oct 3:** the first version said "PLAYBACK FAILED" because it didn't wait for Spotify to load, and it was run without `sudo`. It's fixed. Copy the scripts again (2.2), then run it with `sudo`. A Spotify song takes a few seconds to start, so each Spotify link now takes about 10 seconds. If there's no local song it plays a quiet test tone as the control.

  **Result (Oct 3, 14:13): pass.** The test tone and the Spotify song both played; the song started about 3.4 seconds after the play command. Details are in [docs/SPOTIFY.md](docs/SPOTIFY.md). Re-run it after each change in steps 3 and 4 and compare.
- [ ] **2.6** *(skipped by choice, Oct 3: no backup. `pi_update.sh --undo` and `pi_install_audio.sh --rollback` still work.)* Back everything up (it asks for your sudo password for a few root-only files):
  ```
  bash /tmp/pi/pi_backup.sh
  ```
- [ ] **2.7** Tell me it's done. I read `/tmp/report.txt` and `/tmp/spotify.txt` (or you paste them to me), and we look at the Spotify result together before going on.

---

## Step 3: bring over the audio changes (about 45 minutes)

**Part 0: catch the Pi up to GitHub's `main` (SKIPPED, Oct 3)**

We tried it and it failed: GitHub's `main` is broken (its Recorder is missing the `mic_session` fix, which is commit 6574a9c on `pi/audio-stack`), so the controller crashed and restarted every 5 seconds. We ran `pi_update.sh --undo` and went straight to Part A. Do not use `main` for the Pi until it has been fixed (that is a step-5 job).
- [x] **3.0** *(tried Oct 3, failed for the reason above, undone)* Preview, then switch, then repeat the quick physical test from 2.4:
  ```
  bash /tmp/pi/pi_update.sh --dry-run main
  bash /tmp/pi/pi_update.sh main
  ```

Part A changes settings only. The code from Part 0 still runs, so a problem with the shared audio shows up before the new audio code is involved.

**Part A: sound card sharing**
- [x] **3.1** Preview. It changes nothing; read what it says it would do:
  ```
  bash /tmp/pi/pi_install_audio.sh --dry-run
  ```
- [x] **3.2** Run it for real (it asks for sudo). It ends with `DONE`, after checking that both users can play and record:
  ```
  bash /tmp/pi/pi_install_audio.sh
  ```
- [x] **3.3** A song still plays. Run Spotify test again; it must be no worse than in step 2:
  ```
  sudo python3 /tmp/pi/spotify_check.py --label "after the sound-sharing change" > /tmp/spotify-3a.txt
  ```

**Part B: the new code and the Mopidy settings**
- [x] **3.4** Preview the code switch:
  ```
  bash /tmp/pi/pi_update.sh --dry-run pi/audio-stack
  ```
- [x] **3.5** Switch the code. It installs the Python packages first, stops if there are local edits it doesn't expect, restarts the services and runs the quick check:
  ```
  bash /tmp/pi/pi_update.sh pi/audio-stack
  ```
  Note: this removes the old committed `Unit-tests/.venv` folder from the Pi. The services don't use it. For the old test scripts use the app's venv: `/home/iot-proj/IOT-project--Smart-Speaker/venv/bin/python`.
- [x] **3.6** The Mopidy settings (preview first, then for real):
  ```
  bash /tmp/pi/pi_install_audio.sh --mopidy-conf --dry-run
  bash /tmp/pi/pi_install_audio.sh --mopidy-conf
  ```
- [x] **3.7** Check it works:
  - [x] `python3 /tmp/pi/pi_smoke_test.py --stable-seconds 60` has no FAIL lines
  - [x] the controller log says "Mixer initialized" and "Feedback player initialized" (`journalctl -u smart_speaker -n 50`)
  - [x] a beep plays over music without cutting it off: `python3 /tmp/pi/pi_smoke_test.py --only audio --beep-over-music file:///path/to/a/local/song.mp3`
  - [x] Vol+ and Vol- change the level: `amixer -c0 sget PCM`
- [x] **3.8** Spotify again, and a beep over a Spotify song (play a Spotify chip, then tap the same chip again: the music must keep going):
  ```
  sudo python3 /tmp/pi/spotify_check.py --label "after the new code" > /tmp/spotify-3b.txt
  ```

**Undo, if something is wrong**
- Code: `bash /tmp/pi/pi_update.sh --undo`
- Sound setup and Mopidy settings: `bash /tmp/pi/pi_install_audio.sh --rollback`
- Anything from the backup: `bash /tmp/pi/pi_backup.sh --list`, then `bash /tmp/pi/pi_backup.sh --restore <folder> --dry-run`

---

## Step 4: hardware tests (about 90 minutes)

*(Done: on Oct 3 the user reported the hardware tests as good. No per-test numbers were reported, so if a later problem looks like hardware, redo the matching test.)*

Stop the speaker's services first, so the tests have the bus to themselves:
```
sudo systemctl stop smart_speaker smart_speaker_health
```

- [x] **4.1** `sudo i2cdetect -y 1` shows 0x20, 0x21, 0x24 and the HAT's sound chip (shown as `UU` or 0x18).
- [x] **4.2** `python3 /tmp/pi/test_buttons.py`: all 6 buttons register and none reads as pressed when idle.
- [x] **4.3** `python3 /tmp/pi/test_leds.py`: every light shows every colour. Tell me which physical LED is which, and whether the colour order is blue-green-red as the code assumes.
- [x] **4.4** NFC (from the repo folder, with the app's Python):
  ```
  cd /home/iot-proj/IOT-project--Smart-Speaker
  venv/bin/python Unit-tests/test_pn532.py
  venv/bin/python Unit-tests/read_card.py
  ```
  Tap each of the 4 tags and write down the IDs. Leave one tag on the reader for 10 seconds and tell me whether it causes repeated swipe sounds.
- [x] **4.5** Audio: `bash Unit-tests/BasicSound.sh` (you should hear "front center"), `bash Unit-tests/RecordShortAudio.sh` (records 5 seconds; play it back with `aplay recording_*.wav`). Check the volume at 10%, 50% and 90% (`amixer -c0 sset PCM 10%`, and so on; **start low**) and tell me if the loudest is safe for hearing.
- [x] **4.6** PTT: `cd /home/iot-proj/IOT-project--Smart-Speaker/Main && ../venv/bin/python ../scripts/test-ptt.py`
- [x] **4.7** Start the services again (`sudo systemctl start smart_speaker smart_speaker_health`) and start a song. Watch the lights for 60 seconds while the health monitor runs, and tell me about any flicker. Note CPU and memory in `top` while Spotify starts.
- [x] **4.8** Play Spotify continuously for 20 minutes. Listen for dropouts, search the Mopidy log for `xrun` and `underrun` (`journalctl -u mopidy | grep -iE "xrun|underrun"`), and note CPU and memory.

---

## Step 5: install the fixes, in phases (about 90 minutes, spread over a day or more)

The fixes live on the branch `pi/fixes`, which has to be on GitHub first (the Pi pulls code from there). Do this after step 4, so the hardware tests were done on the plain audio build and any new problem is clearly the fixes' fault. Everything here is covered by more than 800 automatic tests on the development computer, but **none of it has run on the Pi yet**.

It is done in phases, **in this order**, because some changes can be undone by switching to another commit and some cannot:

| Phase | What changes | How it is undone | The Pi runs |
|---|---|---|---|
| **1. System files** | the service files, the saved system log, log rotation, Mopidy's log setting | `pi_install_system.sh --rollback` and `pi_install_audio.sh --rollback` (each saved the old files first) | the **old** code, unchanged |
| **2. Code** | only files in the git checkout, and the Python packages | `pi_update.sh --undo`, or switch to **any** commit or tag (so a regression can be found by bisecting) | the new code |
| **3. Data** | the data file becomes a SQLite database (optional, a switch) | set `SPEAKER_STORAGE=json`; both copies are kept | the new code |
| **4. WiFi setup mode** | tests that take the Pi off the network | the phone and TESTING_WIFI_AND_WEB.md | the new code |

Phase 1 comes first on purpose: it is made so that the **old code runs happily with it**, and the new code **needs** it (the controller's status file lives in a folder the new service file creates). `pi_update.sh` never installs system files; it only checks that they are in place and stops if they are not. The app (step 6) comes after Phase 2, because the app and the server move together.

**Part A: Phase 1, the system files** (the code stays on the old commit, `bb089ff` or whatever you run now)
- [ ] **5.1** *On this computer*, in your project folder on `pi/fixes` (pushed to GitHub), copy the helper scripts and the system files to the Pi (it only writes `/tmp/pi`):
  ```
  scripts/pi/push_to_pi.sh iot-proj@rpi2.local
  ```
- [ ] **5.2** Preview. It lists the six system files and says for each one `ok`, `CHANGES` or `NEW`, and which services it would restart. Expect: the server and WiFi service files `ok`; the controller's and health monitor's service files `CHANGES`; the journal setting and log rotation `NEW`. It changes nothing:
  ```
  bash /tmp/pi/pi_install_system.sh --dry-run
  ```
- [ ] **5.3** Install. It saves the old files first (in `/var/lib/smart-speaker-setup/system-rollback/`), installs, restarts the controller and the health monitor (the music stops for a few seconds) and the system log service, and checks that they came back:
  ```
  bash /tmp/pi/pi_install_system.sh
  ```
- [ ] **5.4** Mopidy's settings gain a `[loglevels]` section (so Spotify's own messages reach the Mopidy log). Preview, then for real:
  ```
  bash /tmp/pi/pi_install_audio.sh --mopidy-conf --dry-run
  bash /tmp/pi/pi_install_audio.sh --mopidy-conf
  ```
- [ ] **5.5** Phase 1 landed, and nothing broke (the Pi still runs the OLD code):
  - [ ] `bash /tmp/pi/pi_install_system.sh --check` says all 6 system files match
  - [ ] `systemctl is-active smart_speaker smart_speaker_server smart_speaker_health mopidy` says `active` four times, and `systemctl show -p NRestarts --value smart_speaker smart_speaker_health` says `0` for both (counted since the restart in 5.3)
  - [ ] `ls -ld /run/smart_speaker` shows a folder owned by `iot-proj` (systemd makes it for the controller; it stays empty until Phase 2, because the old code does not write a status file)
  - [ ] `systemctl cat smart_speaker_health | grep ExecStart` shows the venv's Python (`.../venv/bin/python`)
  - [ ] `cat /etc/logrotate.d/smart_speaker` and `ls /etc/systemd/journald.conf.d/` show the two new files
  - [ ] the health light (Light 1) is green, `python3 /tmp/pi/pi_smoke_test.py --stable-seconds 30` is green
- [ ] **5.6** `sudo reboot`, wait 90 seconds. `journalctl --list-boots` shows two or more boots (the system log now survives a reboot: this is the first time), the services are active with 0 restarts, and the quick check above is green again.
- [ ] **5.7** Use the speaker as you normally do (taps, Spotify, the buttons, a recording) **for a while, ideally a day**, with the old code still running. Anything new that goes wrong now comes from Phase 1 and nothing else. Tell me about anything odd, then go on to Phase 2.

**Undo Phase 1:** `bash /tmp/pi/pi_install_system.sh --rollback` (puts the old service files back, removes the two new files, restarts) and, for Mopidy, `bash /tmp/pi/pi_install_audio.sh --rollback`.

**Part B: Phase 2, the code** (nothing here touches the system files. If something goes wrong: `bash /tmp/pi/pi_update.sh --undo`; or to find which change did it, go to a commit in between with `bash /tmp/pi/pi_update.sh <commit>` and halve the range each time, like `git bisect`. List the commits with `git log --oneline pi/audio-stack..pi/fixes`.)
- [ ] **5.8** Preview. It lists what would change, and checks that the system files from Phase 1 are in place (it prints "System files: match what the new code expects"; if it says they differ, it stops and tells you to do Phase 1 first). It changes nothing:
  ```
  bash /tmp/pi/pi_update.sh --dry-run pi/fixes
  ```
- [ ] **5.9** Switch the code (it installs the Python packages first, switches, restarts the three services and runs the quick check; the check must end green). Only code changes here, so everything in this phase can be undone by going back to a commit:
  ```
  bash /tmp/pi/pi_update.sh pi/fixes
  ```
- [ ] **5.10** Your data is safe and unchanged, and the program folders are right. The server now saves its data file in a way a power cut cannot damage (see `EDGE_CASES.md`, cases 40 to 47):
  - [ ] the quick check in 5.9 said the chips, library and settings match what they were before (it compares them; paste the line if it doesn't)
  - [ ] open the app: the chips, the library and the settings look the same as before
  - [ ] rename a chip in the app, then `ls -l /home/iot-proj/IOT-project--Smart-Speaker/Main/server_data.json*` shows the file and a new `server_data.json.bak`
  - [ ] `grep STORAGE /var/log/smart_speaker_server.log | tail -n 5` says "data file opened" (and nothing about damage)
  - [ ] a chip you deleted earlier does not come back after `sudo systemctl restart smart_speaker_server`
  - [ ] `ls -ld /home/iot-proj/IOT-project--Smart-Speaker/Main/local_files/recordings` is owned by `iot-proj`, not `root` (the server now hands the folder to the speaker's user)

**Part B continued: what you should now see and hear** (tell me pass or fail for each; paste the log lines for any fail with `journalctl -u smart_speaker -n 80`)
- [ ] **5.11** Lights: with the health monitor running, watch all three lights for 60 seconds. No flicker, no light going dark for a moment. After a Vol+ or Vol- press, the speaker light (Light 3) goes back to its normal colour. (Before: it stayed dark.)
- [ ] **5.12** A tap **loads** the chip (green flash and chime) and **Play** starts it. Tap the same chip again while it plays: the music must keep going.
- [ ] **5.13** A song that can't start: in the app give a chip the made-up link `spotify:track:0000000000000000000000`, tap it and press Play. You should get the error sound and a red flash within a few seconds, and the speaker goes back to "chip loaded". (Before: 60 seconds of silent "playing".)
- [ ] **5.14** Stop button: hold Stop for 3 seconds (the chip is unloaded). Then tap a chip, press Play, and short-press Stop: the music must stop. (Before: the first short press after a long press was ignored.)
- [ ] **5.15** Recording: hold Record for 5 seconds (the recording light turns **red**), speak, short-press Record. You hear the "saved" chime to the end, and a `[RECORDING]` entry appears in the library. Hold Play for 2 seconds: it plays back.
- [ ] **5.16** Parental controls, from the app, one at a time:
  - [ ] cap the volume at 40, press Vol+ many times: it stops at 40
  - [ ] set quiet hours around now: a chip tap + Play is refused with the error sound, and so is Play/Pause resuming a paused song
  - [ ] set a daily limit of 2 minutes: after 2 minutes of music it is refused
  - [ ] put every setting back to normal afterwards
- [ ] **5.17** Voice: hold PTT and say "hi speaker, clear" with a chip loaded: the chip's song link is cleared (check the app) and only then the music stops. Say a command with the internet off or the microphone covered: the speaker answers within about 10 seconds and the buttons still work.
- [ ] **5.18** The status file and the health check (the speaker now proves it is alive, and says what it is doing):
  - [ ] `cat /run/smart_speaker/status.json` shows the state, the chip, the volume, the version (the git commit) and `last_play`. Run it twice a few seconds apart: the `monotonic` number must go up (it is rewritten every second)
  - [ ] `curl -s -w '\n%{http_code}\n' localhost:8080/health` shows `"ok": true` and `200`. `curl -s localhost:8080/status` shows the same controller information, `storage`, and today's `usage`
  - [ ] with the made-up link from 5.13, `/health` is still `ok` but `warnings` says the last song could not be played, with Mopidy's reason, and `last_play` in the status says `failed`
  - [ ] **Freeze the controller** to prove a stuck one is noticed: `sudo systemctl kill --signal=SIGSTOP smart_speaker`. Within about 25 seconds `curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/health` says `503` and the health light (Light 1) blinks red. Then `sudo systemctl kill --signal=SIGCONT smart_speaker`: within a few seconds it says `200` again and the light is green. (Before, a stuck controller looked fine because systemd only asks whether the process exists.)
- [ ] **5.19** The API token (changes from other devices now need a secret; the speaker itself, and the WiFi setup hotspot, do not):
  - [ ] after the first start of the new server, `ls -l /home/iot-proj/IOT-project--Smart-Speaker/SECRETS` shows a file owned by `iot-proj` (mode `-rw-------`), and `grep SECURITY /var/log/smart_speaker_server.log | tail -n 3` says a new API token was created. **Never paste the token or the file.** Read the token on the speaker with `grep DEBUG_TOKEN /home/iot-proj/IOT-project--Smart-Speaker/SECRETS` and type it into the app's Settings
  - [ ] from **this computer** (another device on the network): `curl -s -o /dev/null -w '%{http_code}\n' http://rpi2.local:8080/chips` says `200` (reading is open) and `curl -s -o /dev/null -w '%{http_code}\n' -X POST http://rpi2.local:8080/usage/add -d '{"seconds":0}'` says `401` (changing is not)
  - [ ] `curl -s -o /dev/null -w '%{http_code}\n' http://rpi2.local:8080/debug/system` says `401`, and with the header `-H "X-Speaker-Token: <the token>"` it says `200`
  - [ ] the controller and the health light still work (they call the server from the speaker itself, which needs no token): tap a chip, press Play, and the health light stays green
  - [ ] in the app (after the new app is installed, see step 6 below): without the token, changing a chip says the token is missing; with the token typed into Settings, it works
- [ ] **5.20** The speaker without its NFC reader. Switch the Pi off (`sudo shutdown -h now`), unplug the reader's cable, power it on. The buttons, the lights and the music (started from the app) must all work, and the controller log says the reader was not found and that it will keep trying. Then, **only if you are comfortable plugging it back in with the Pi on**, plug it in again: within about 5 seconds the next tag is read, with no restart. (Otherwise shut down, plug it in and power on: that still proves it comes back.)

**Part C: Phase 3, the database (SQLite)** (do this only after Phase 2 has run well for a while) (the data moves out of the JSON file into a database that a power cut cannot damage; this is a switch you turn on, look at, rehearse turning off, and turn on again)

How it works: the setting `SPEAKER_STORAGE` is `json` (what you have been running) or `sqlite`. When the server starts and finds the setting has changed, it moves your data across by itself, **checks every row against the original**, and keeps the old copy under a dated name (`server_data.json.migrated-<date>` or `server_data.db.exported-<date>`). If the check fails it undoes itself and carries on with the old copy, and says so in the log. There is only ever one live copy of the data, so the two can't drift apart.

- [ ] **5.21** Take a snapshot of what the app sees now, to compare with later (it hashes the chips, library and settings):
  ```
  python3 /tmp/pi/pi_smoke_test.py --only data --save-data /tmp/data-json.json
  ```
- [ ] **5.22** Switch to SQLite:
  ```
  sudo mkdir -p /etc/systemd/system/smart_speaker_server.service.d
  printf '[Service]\nEnvironment=SPEAKER_STORAGE=sqlite\n' | sudo tee /etc/systemd/system/smart_speaker_server.service.d/storage.conf
  sudo systemctl daemon-reload
  sudo systemctl restart smart_speaker_server
  ```
  Then check:
  - [ ] `grep STORAGE /var/log/smart_speaker_server.log | tail -n 8` says the JSON data was moved into the database and the old file was kept as `server_data.json.migrated-...`, with no line saying it failed
  - [ ] `curl -s localhost:8080/status` shows `"storage": "sqlite"`
  - [ ] `ls -l /home/iot-proj/IOT-project--Smart-Speaker/Main/server_data*` shows `server_data.db` (with `-wal` and `-shm` files next to it, which is normal), `server_data.db.bak`, and the `.migrated-` JSON copy, and **no** plain `server_data.json`
  - [ ] `python3 /tmp/pi/db_export_json.py` says the database passes its own check and shows your chip and song counts
  - [ ] `python3 /tmp/pi/pi_smoke_test.py --only api --compare-data /tmp/data-json.json` says the data matches
  - [ ] the app shows the same chips, library and settings as before
- [ ] **5.23** Use it: rename a chip and assign a different song in the app, tap that chip, press Play. Add a song from the app. Everything works as before, and the controller log shows no errors about the chip lookup (`journalctl -u smart_speaker -n 50`).
- [ ] **5.24** `sudo reboot`. After 90 seconds the changes from 5.23 are still there and `/status` still says `sqlite`. (The real power-cut test is in step 7.)
- [ ] **5.25** Rehearse the way back. Switch to JSON:
  ```
  printf '[Service]\nEnvironment=SPEAKER_STORAGE=json\n' | sudo tee /etc/systemd/system/smart_speaker_server.service.d/storage.conf
  sudo systemctl daemon-reload
  sudo systemctl restart smart_speaker_server
  ```
  - [ ] the log says the data was moved back into the JSON file, and the database was kept as `server_data.db.exported-...`
  - [ ] `/status` shows `"storage": "json"`, and the changes you made in 5.23 are still there in the app
  - [ ] `ls /home/iot-proj/IOT-project--Smart-Speaker/Main/server_data*` shows `server_data.json` and **no** `server_data.db`
- [ ] **5.26** Switch to SQLite again (same commands as 5.22 with `sqlite`) and check the changes are still there. If everything passed, **leave it on SQLite** and tell me: I then make SQLite the default in the code, so this setting file is no longer needed. (If something failed, set it back to `json`, tell me what the log said, and nothing is lost: both copies are kept.)

**Part D: Phase 4, WiFi setup mode** (do this **last**: SSH stops working while the Pi is in setup mode, and you will need the phone to put it back on the network)
- [ ] **5.27** Tests 1 and 2 in [TESTING_WIFI_AND_WEB.md](TESTING_WIFI_AND_WEB.md). These were written for the old code, so a pass here is also the first proof that the hotspot is detected correctly.
- [ ] **5.28** Test 6 in the same file: the router comes back after the speaker (a power cut at home). The Pi must rejoin the home network by itself within about 2 minutes, with nobody touching the hotspot.

**Undo, in the order that matters**
- The data (Phase 3) first, if the Pi has been on SQLite: set `SPEAKER_STORAGE=json` as in 5.25. A code switch does not move data by itself.
- Then the code (Phase 2): `bash /tmp/pi/pi_update.sh --undo`.
- Then the system files (Phase 1), only if they themselves are the problem: `bash /tmp/pi/pi_install_system.sh --rollback`. They are made so that the old code works with them, so there is normally no need.
- Mopidy settings: `bash /tmp/pi/pi_install_audio.sh --rollback`.

---

## Step 6: the app: the token, the status and the fixes (about 45 minutes)

Do this after Phase 2 of step 5 (the code), because the app talks to the new server. (The new app also works against the old server, so a rollback of the Pi's code does not strand it. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).) The app code could not be built on the development computer (Flutter was not run there). I did run Dart's analyzer over `flutter_app/lib` on a scratch copy and it reported **no issues**, which catches mistakes in types and names but is not the same as a build, so 6.1 is still yours to run.

- [ ] **6.1** *On this computer.* Check the app compiles: `cd flutter_app && flutter analyze`. It should say "No issues found". If it prints errors, paste them to me and I fix them before you build anything.
- [ ] **6.2** *On this computer.* Build the web app and put it on the Pi (this only replaces the web app's files in `Main/web_app` on the Pi, after keeping the old ones as `Main/web_app.prev`; no service restarts. To go back: `scripts/deploy_web.sh --undo`):
  ```
  scripts/deploy_web.sh iot-proj@rpi2.local
  ```
- [ ] **6.3** Open `http://rpi2.local:8080` in a browser on any computer or phone on the network:
  - [ ] the home screen shows a second card saying what the speaker is doing ("Waiting for a chip", "Ready: <chip>", "Playing", "Paused", "Recording"), the volume and "Played today". Tap a chip on the speaker, press Play: the card follows within about 5 seconds
  - [ ] with the made-up link from 5.13 the card shows an orange "The last song could not be played" with Mopidy's reason; a later good play clears it
  - [ ] stop the controller (`sudo systemctl stop smart_speaker` on the Pi): within about 25 seconds the card says "The speaker is not running". Start it again
- [ ] **6.4** The token. In the app go to Settings, **Speaker Token**, type the token (read it on the Pi with `grep DEBUG_TOKEN /home/iot-proj/IOT-project--Smart-Speaker/SECRETS`; do not paste it anywhere else), press **Check**: "The speaker accepted the token". With a wrong token it says "did not accept".
- [ ] **6.5** Without the token (clear the field, Save): changing a chip name or a setting shows "The speaker needs its token for this. Enter it in Settings." and changes nothing. Looking at chips, library and settings still works. Put the token back.
- [ ] **6.6** Library: upload a song from a file, give it a name. There is **one** new entry, with the name you chose (before, there were two: "[UPLOAD] <file>" and your name).
- [ ] **6.7** Developer Tools (needs the token): system info and logs show. WiFi, connect to the network the speaker is **already on** (a saved one): it says "Connected to ...", not "Failed" (before, it always said Failed, because the speaker answers "connecting" first). The old "Run Main" action is gone.
- [ ] **6.8** *Phone only.* **First copy the APK that is on your phone now (or your last build) somewhere safe**, so you can go back. Then build and install the Android app: `cd flutter_app && flutter build apk --release`, then install `build/app/outputs/flutter-apk/app-release.apk`. (The Android build no longer includes Firebase Analytics and Messaging, which nothing in the app used. That could not be built here: if the build fails, tell me what it says. `git revert` of the commit "App: remove the unused Firebase" puts it back.) In Settings, **Test Connection** works with `rpi2.local`. If it fails (Android's name lookup is the known weak spot), open Advanced Settings and type the speaker's address as `http://<its IP>:8080` (the IP is in `/tmp/report.txt` from `pi_report.sh`, or `hostname -I` on the Pi). Then repeat 6.4.
- [ ] **6.9** *Phone only.* The WiFi wizard: start Settings, WiFi Setup, let it join the speaker's setup hotspot, then go **back** before finishing. The phone returns to its normal WiFi and its internet works again (before, the app kept using the hotspot until you restarted it).

---

## Step 7: final tests (later)

**The walkthrough** (you do these on the speaker):

| Story | What you do | It's good when |
|---|---|---|
| 1 NFC playback | Scan an assigned tag, then press Play. Scan the same tag again while it plays. | Swipe sound and light on scan, music starts within the measured time after Play, the second scan doesn't stop the music |
| 2 and 5 chips and library | Assign a song, rename, delete (Android and web) | Changes survive a reboot |
| 3 recording | Hold Record 5 s, speak, short-press Record to save, hold Play 2 s | Countdown, music pauses, "saved" chime is heard, a `[RECORDING]` entry appears in the library, it plays back |
| 4 buttons | All 6, plus the long presses: Stop 3 s unloads the chip, Play 2 s plays the latest recording, Vol+ or Vol- held 5 s runs a service action | It does what it should. (I'll write the exact expected behavior here once step 4 is done, because the README table is out of date.) |
| 6 parental | Cap the volume at 40 and try to go above it. Set quiet hours around now. Set a 2-minute daily limit. | Blocked on **every** path, including resume and recordings |
| 7 whitelist | Allow only tag A, scan tag B | B is blocked |
| 8 voice | "hi speaker play/pause/stop/clear", a joke command, and a run with no internet | Bounded wait, the device stays responsive |
| 9 WiFi | [TESTING_WIFI_AND_WEB.md](TESTING_WIFI_AND_WEB.md) tests 1-5 | All pass (or test 5 is waived and written down) |
| 10 remote debugging | Logs, restart the controller, i2c, from the app | Works with the token, fails with 401 without it |
| New | The app shows what's playing, minutes used and whether the last play worked | Matches the speaker |
| Spotify | Pull the network mid-track and put it back; tap a made-up link; `systemctl restart mopidy` during playback; start playback on a phone using the same account | Error shown within the time limit (not 60 s), plays again once the cause is gone |
| Backup song | Unplug the WiFi and tap the local-file chip | It plays |

**System checks**
- [ ] Cold boot to fully working in 90 seconds or less, with zero restarts on every service. Time from cold boot to the first Spotify sound is measured too.
- [ ] Pull the power while idle, while playing and while writing to the library (3 times each). The Pi comes back and the data matches.
- [ ] Stop Mopidy during playback and start it again (the controller reconnects). Unplug the NFC reader (buttons and music still work, and the health light shows the fault).
- [ ] Leave it running for 2 hours: `python3 /tmp/pi/pi_smoke_test.py --watch 7200 --log /tmp/soak.log`, with regular Spotify taps.
- [ ] Make a full copy of the SD card of the final state.
- [ ] Before **every** demo, 2 days ahead: re-run `spotify_check.py`, check Premium is active (and on the account that owns the Spotify app), check how old the credentials are, and re-read the two upstream issues in [docs/SPOTIFY.md](docs/SPOTIFY.md). If it isn't green, we talk it over and, if needed, switch the demo to the local-file chip.

---

## Cheat sheet

| I want to... | Command |
|---|---|
| see what the Pi looks like | `sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt` |
| quick health check | `python3 /tmp/pi/pi_smoke_test.py --stable-seconds 30` |
| test Spotify | `sudo python3 /tmp/pi/spotify_check.py --label "..." > /tmp/spotify.txt` |
| switch the code to a branch or tag | `bash /tmp/pi/pi_update.sh <name>` (add `--dry-run` to preview) |
| undo the last code switch | `bash /tmp/pi/pi_update.sh --undo` |
| undo the sound and Mopidy settings | `bash /tmp/pi/pi_install_audio.sh --rollback` |
| back up / list / restore | `bash /tmp/pi/pi_backup.sh`, `--list`, `--restore <folder> --dry-run` |
| read the logs | `journalctl -u smart_speaker -u mopidy -n 100`; the controller's own log is `/var/log/smart_speaker.log` on the old code and `/var/log/smart_speaker/controller.log` on newer code |

If `/tmp/pi` is gone after a reboot, run `scripts/pi/push_to_pi.sh iot-proj@rpi2.local` again on this computer.
