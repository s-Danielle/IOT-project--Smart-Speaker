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
