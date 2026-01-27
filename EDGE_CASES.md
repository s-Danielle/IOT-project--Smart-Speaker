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
| 9 | Stop long-press triggered multiple times | `_stop_long_press_triggered` flag prevents repeated execution |
| 10 | Volume buttons during recording | Blocks action, plays blocked sound |

## Audio Playback

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 11 | Mopidy connection lost mid-playback | Auto-reconnects via `_execute()` wrapper with retry logic |
| 12 | Spotify track slow to load (buffering) | Waits up to 60 seconds (`MAX_WAIT_FOR_PLAYBACK`) before timeout |
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
| 22 | Daily usage limit reached | Blocks new playback, tracks playtime (resets daily) |

## Recording Limits

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 23 | Insufficient disk space before recording | Checks free space (`MIN_DISK_SPACE_MB`), blocks if below threshold |
| 24 | Recording exceeds max duration | Auto-saves after `MAX_RECORDING_DURATION` (5 minutes default) |

## Network & Connectivity

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 25 | No WiFi configured at boot | Starts AP mode ("SmartSpeaker-Setup") after 30 seconds |
| 26 | Health LED status indication | Shows green (OK), blue blink (no server), red (hardware fail) |

## Hardware Resilience

| # | Edge Case | How It's Handled |
|---|-----------|------------------|
| 27 | I2C device communication errors | Tracks consecutive failures, marks failed after threshold (5 errors) |
| 28 | Mopidy returns unexpected state | Uses cached state, logs warning, continues operation |

---

## References

- Button timing constants: `Main/config/settings.py`
- Recording limits: `Main/config/settings.py` (`MAX_RECORDING_DURATION`, `MIN_DISK_SPACE_MB`)
- State machine logic: `Main/core/controller.py`
- Parental controls: `Main/core/controller.py` (`_check_quiet_hours`, `_check_chip_allowed`, `_check_daily_limit`)
- Daily usage tracking: `Main/server.py` (`get_daily_usage`, `add_daily_usage`)
- Hardware health: `Main/utils/hardware_health.py`
