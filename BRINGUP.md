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
- [ ] **3.7** Check it works:
  - [ ] `python3 /tmp/pi/pi_smoke_test.py --stable-seconds 60` has no FAIL lines
  - [x] the controller log says "Mixer initialized" and "Feedback player initialized" (`journalctl -u smart_speaker -n 50`)
  - [ ] a beep plays over music without cutting it off: `python3 /tmp/pi/pi_smoke_test.py --only audio --beep-over-music file:///path/to/a/local/song.mp3`
  - [ ] Vol+ and Vol- change the level: `amixer -c0 sget PCM`
- [ ] **3.8** Spotify again, and a beep over a Spotify song (play a Spotify chip, then tap the same chip again: the music must keep going):
  ```
  sudo python3 /tmp/pi/spotify_check.py --label "after the new code" > /tmp/spotify-3b.txt
  ```

**Undo, if something is wrong**
- Code: `bash /tmp/pi/pi_update.sh --undo`
- Sound setup and Mopidy settings: `bash /tmp/pi/pi_install_audio.sh --rollback`
- Anything from the backup: `bash /tmp/pi/pi_backup.sh --list`, then `bash /tmp/pi/pi_backup.sh --restore <folder> --dry-run`

---

## Step 4: hardware tests (about 90 minutes)

Stop the speaker's services first, so the tests have the bus to themselves:
```
sudo systemctl stop smart_speaker smart_speaker_health
```

- [ ] **4.1** `sudo i2cdetect -y 1` shows 0x20, 0x21, 0x24 and the HAT's sound chip (shown as `UU` or 0x18).
- [ ] **4.2** `python3 /tmp/pi/test_buttons.py`: all 6 buttons register and none reads as pressed when idle.
- [ ] **4.3** `python3 /tmp/pi/test_leds.py`: every light shows every colour. Tell me which physical LED is which, and whether the colour order is blue-green-red as the code assumes.
- [ ] **4.4** NFC (from the repo folder, with the app's Python):
  ```
  cd /home/iot-proj/IOT-project--Smart-Speaker
  venv/bin/python Unit-tests/test_pn532.py
  venv/bin/python Unit-tests/read_card.py
  ```
  Tap each of the 4 tags and write down the IDs. Leave one tag on the reader for 10 seconds and tell me whether it causes repeated swipe sounds.
- [ ] **4.5** Audio: `bash Unit-tests/BasicSound.sh` (you should hear "front center"), `bash Unit-tests/RecordShortAudio.sh` (records 5 seconds; play it back with `aplay recording_*.wav`). Check the volume at 10%, 50% and 90% (`amixer -c0 sset PCM 10%`, and so on; **start low**) and tell me if the loudest is safe for hearing.
- [ ] **4.6** PTT: `cd /home/iot-proj/IOT-project--Smart-Speaker/Main && ../venv/bin/python ../scripts/test-ptt.py`
- [ ] **4.7** Start the services again (`sudo systemctl start smart_speaker smart_speaker_health`) and start a song. Watch the lights for 60 seconds while the health monitor runs, and tell me about any flicker. Note CPU and memory in `top` while Spotify starts.
- [ ] **4.8** Play Spotify continuously for 20 minutes. Listen for dropouts, search the Mopidy log for `xrun` and `underrun` (`journalctl -u mopidy | grep -iE "xrun|underrun"`), and note CPU and memory.

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
