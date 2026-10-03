# Smart Speaker - Parameters Documentation

This file documents all hardcoded parameters in the project that require recompilation/restart to change.

## Main Configuration File

All parameters are defined in `Main/config/settings.py`

---

## Timing Parameters

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| `LOOP_INTERVAL` | 0.05 | seconds | Main loop polling interval (50ms) |
| `RECORD_HOLD_DURATION` | 5.0 | seconds | How long to hold Record button to arm recording |
| `CLEAR_CHIP_HOLD_DURATION` | 3.0 | seconds | How long to hold Stop button to clear chip |
| `PLAY_LATEST_HOLD_DURATION` | 2.0 | seconds | How long to hold Play/Pause to play latest recording |
| `MAX_WAIT_FOR_PLAYBACK` | 20.0 | seconds | Max time to wait for Mopidy to confirm playback started; after that the speaker shows an error. A Spotify song starts about 3.4 s after Play (measured, see `docs/SPOTIFY.md`) |
| `MIN_PLAYBACK_DURATION` | 2.0 | seconds | Minimum playback time before considering track "finished" |
| `STATUS_POLL_INTERVAL` | 0.5 | seconds | Minimum time between Mopidy status polls (caching) |

---

## I2C Addresses

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PCF8574_ADDRESS` | 0x20 | Button expander I2C address |
| `LED_EXPANDER_ADDRESS` (in `Main/hardware/leds.py`) | 0x21 | RGB LED expander I2C address |
| `PN532_I2C_ADDRESS` | 0x24 | NFC reader I2C address |

---

## Button Pin Mappings

Buttons are connected to PCF8574 at address 0x20 (active-low logic).

| Parameter | Value | PCF8574 Pin | Function |
|-----------|-------|-------------|----------|
| `BUTTON_PLAY_PAUSE_BIT` | 0 | P0 | Play/Pause button |
| `BUTTON_RECORD_BIT` | 1 | P1 | Record button |
| `BUTTON_STOP_BIT` | 2 | P2 | Stop button |
| `BUTTON_VOLUME_UP_BIT` | 3 | P3 | Volume Up button |
| `BUTTON_VOLUME_DOWN_BIT` | 4 | P4 | Volume Down button |
| `BUTTON_PTT_BIT` | 5 | P5 | Push-to-Talk button |
| - | 6 | P6 | Speaker LED Red (divided LED) |
| - | 7 | P7 | (unused) |

---

## LED Pin Mappings

3 RGB LEDs with pin order **B, G, R** (not R, G, B):

| LED | Pins | Expander | Description |
|-----|------|----------|-------------|
| Light 1 (Health) | P0=B, P1=G, P2=R | 0x21 | Device health status |
| Light 2 (PTT) | P3=B, P4=G, P5=R | 0x21 | Push-to-talk feedback |
| Light 3 (Speaker) | P6=B, P7=G (0x21), P6=R (0x20) | Divided | Player/speaker status |

**Note:** Light 3 is a "divided LED" - its red pin is on the button expander (0x20) at P6.

**Shared state:** the controller, the PTT light, the health monitor and the WiFi service all drive these LEDs, and Light 1, Light 2 and half of Light 3 share one chip. They share one record of which pins are on, kept in `/tmp/smart_speaker_leds.json` (change the path with the `SPEAKER_LED_STATE` environment variable), so one program never switches off another one's light. On 0x20 only P6 is ever driven; P0-P5 (the buttons) are always written high.

---

## Volume Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `VOLUME_STEP` | 10 | Volume change per button press (0-100 scale) |
| `VOLUME_DEFAULT` | 50 | Fallback if the ALSA mixer cannot be opened |
| `ALSA_CARD` | 0 | ALSA card index for volume (`seeed2micvoicec`) |
| `ALSA_VOLUME_CONTROL` | "PCM" | Mixer control written by the volume buttons |

At start-up the volume is lowered to `VOLUME_DEFAULT` or the parental volume limit, whichever is lower. It is never raised: if it is already quieter it is left alone.

---

## Audio Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `FEEDBACK_PCM` | "feedback" | ALSA PCM for UI WAVs (`aplay -D feedback`) |

---

## Network Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SERVER_HOST` | "localhost" | Address the controller uses to reach the REST API server |
| `SERVER_PORT` | 8080 | Internal API port (hardware ↔ server) |
| `MOPIDY_HOST` | "localhost" | Mopidy server address |
| `MPD_PORT` | 6600 | MPD protocol port (used by python-mpd2) |

---

## NFC Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `NFC_TIMEOUT` | 0.3 | NFC read timeout in seconds. With no chip on the reader this is also the pace of the NFC thread. If the reader is missing the speaker still starts and retries every 5 s |

---

## Recording Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `RECORDING_DEVICE` | "" | ALSA recording device (empty = default) |
| `MAX_RECORDING_DURATION` | 300.0 | Seconds; a recording that long is saved automatically |
| `MIN_DISK_SPACE_MB` | 100 | Free disk space needed before a recording may start |

---

## PTT (Push-to-Talk) Voice Command Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PTT_ENABLED` | True | Enable/disable PTT feature |
| `PTT_LISTEN_DURATION` | 5.0 | Seconds to listen for a voice command (fixed-length mode) |
| `PTT_WAKE_PHRASE` | "hi speaker" | Required phrase before command |
| `PTT_MAX_HOLD` | 10.0 | Seconds; holding PTT longer counts as letting go, so a stuck button cannot keep the mic open and the music paused |
| `PTT_TRANSCRIBE_TIMEOUT` | 8.0 | Seconds to wait for the speech service in total; after that the command fails (the controller waits that long at most) |

**Note:** PTT uses Google Speech API and requires an internet connection.

---

## File Paths

Defined in `Main/config/paths.py`:

| Path | Description |
|------|-------------|
| `TAGS_JSON` | `Main/config/tags.json` - old NFC chip list (chips and songs now live in `Main/server_data.json`, owned by the server) |
| `SOUNDS_DIR` | `Main/assets/sounds/` - Audio feedback files |
| `RECORDINGS_DIR` | `Main/local_files/recordings/` - User recordings |

---

## How to Modify Parameters

1. Open `Main/config/settings.py`
2. Change the desired parameter value
3. Restart the affected service:
   ```bash
   sudo systemctl restart smart_speaker
   # or
   sudo systemctl restart smart_speaker_server
   ```

**Note:** Some parameters (like I2C addresses) require hardware changes as well.
