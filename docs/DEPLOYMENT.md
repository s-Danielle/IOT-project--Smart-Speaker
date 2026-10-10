# How the finished speaker gets onto the Pi

The checklist with every command and check is [BRINGUP.md](../BRINGUP.md), step 5 (the Pi) and step 6 (the app). This page is the reasoning: what is deployed in what order, why, and how each part is undone.

## The rule that decides the order

Some changes can be undone by switching to another git commit. Some cannot. They are deployed separately, the ones that cannot be undone that way **first**, and each kind has its own tool:

| Phase | What | Tool | Undone by | The Pi runs |
|---|---|---|---|---|
| **1. System** | service files, the saved system log (journald), log rotation, Mopidy's log setting | `pi_install_system.sh`, `pi_install_audio.sh --mopidy-conf` | `--rollback` of each (they save every file they replace) | the old code |
| **2. Code** | the git checkout and the Python packages | `pi_update.sh <branch, tag or commit>` | `pi_update.sh --undo`, or any other commit | the new code |
| **2b. App** | the web app on the Pi, the Android app | `scripts/deploy_web.sh`, `flutter build apk` | `deploy_web.sh --undo`; keep the old APK | the new code |
| **3. Data** | JSON file becomes a SQLite database (a switch, off by default) | `SPEAKER_STORAGE` (BRINGUP 5.22) | set it back; both copies are kept | the new code |
| **4. WiFi setup** | tests that take the Pi off the network | TESTING_WIFI_AND_WEB.md | the phone | the new code |

The data comes last because it is the one change that code switching does not cover: a Pi that has been on SQLite, switched back to old code, would find no JSON file.

## What keeps this safe

1. **System files work with the old code and the new.** Phase 1 runs while the Pi is still on the old commit, and the old code must be happy with it. (Checked: the new service file only adds a folder and the venv's Python; the journal and log-rotation files are inert for old code.) Whoever changes a system file later must keep that true.
2. **The new code needs them.** The controller's status file lives in `/run/smart_speaker/`, which the new service file creates. Without it the health light would show a dead controller. So `pi_update.sh` **checks** that the system files match the target commit, and stops, with the exact command to run, if they do not. It never installs them. (`--allow-system-drift` overrides this, for bisecting across commits that differ in their system files.)
3. **Code updates are only code.** `pi_update.sh` saves a snapshot of the data, installs the Python packages for the new code *before* switching, switches, restarts, runs the quick check and compares the data. `--undo` returns to the previous commit. Because nothing else changed, **any** commit is a valid place to stand, so a regression is found by halving the range: `git log --oneline pi/audio-stack..pi/fixes`, then `pi_update.sh <commit>` each time.
4. **The app tolerates an older speaker.** The new app against an older server still reads everything and uploads songs (it finds the new library entry by its link when the speaker does not return an id), and says so if the speaker is too old to have a token. So rolling the Pi's code back does not strand the phone. The other way round: an old app against the new server can look but not change anything until it has the token, which is the point of the token.
5. **Tags, not branch tips.** Once reviewed, the commit to deploy gets a tag (`rc1`, later `v1.0`) and the Pi is updated to the tag, so "what is on the Pi" is one name.

## The order, start to finish

1. **Finish and review** (this stage): all code on `pi/fixes`, the tests green, a review of the whole diff, the findings fixed. Tag `rc1` (a candidate, not a release). Push.
2. **Phase 1** on the Pi: `push_to_pi.sh`, `pi_install_system.sh --dry-run`, `pi_install_system.sh`, the Mopidy settings, the checks, a reboot. Then **let it run with the old code**, ideally a day. Anything odd comes from Phase 1 alone.
3. **Phase 2**: `pi_update.sh --dry-run rc1`, `pi_update.sh rc1`, then the hardware and behaviour checks (BRINGUP 5.10 to 5.20), including the frozen-controller drill and the NFC-reader-missing drill.
4. **2b, the app**: only after Phase 2 is green. `flutter analyze`, `deploy_web.sh` (keeps the previous web app), build the APK (keep the old one), type the token into each phone and browser (BRINGUP step 6).
5. **Phase 3**, only if everything above has run well for a while: switch to SQLite, use it, reboot, rehearse the way back, switch again. If it passes, flip `DEFAULT_STORAGE` to `sqlite` in `Main/storage/__init__.py` (a one-word code change, so it goes through Phase 2 as a new tag).
6. **Phase 4**: the WiFi setup tests, last, because they leave the Pi off the network until the phone puts it back.
7. **Final tests** (BRINGUP step 7: the walkthrough, power pulls, the 2-hour soak, the failure drills). Then a full copy of the SD card, merge to `main`, tag `v1.0`, and put the Pi on `v1.0`.

## Where everything goes wrong, and the way back

| If this goes wrong | Do this |
|---|---|
| a service file or the journal setting misbehaves | `bash /tmp/pi/pi_install_system.sh --rollback` |
| Mopidy's settings | `bash /tmp/pi/pi_install_audio.sh --rollback` |
| the new code misbehaves | `bash /tmp/pi/pi_update.sh --undo` (or a named commit) |
| the new web app misbehaves | `scripts/deploy_web.sh --undo` |
| the new Android app misbehaves | install the APK you kept |
| SQLite misbehaves | `SPEAKER_STORAGE=json` and restart the server (it carries the data back and checks it) |
| nothing works and you want everything as it was | undo in this order: data, code, system files (BRINGUP 5, "Undo, in the order that matters"), then the SD-card copy as the last resort |

## What was never run on the Pi

The code and scripts are covered by automated tests on the development computer, but these first run on the Pi in the phases above: the system installer and its rollback, the shared LED file on the real I2C bus, the NFC reader retry, the WiFi retry in setup mode, the status file and `/health`, the token (from a real phone), SQLite on the SD card and the persistent journal. The Android app has been analysed but not built.
