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
| `MAX_WAIT_FOR_PLAYBACK` | 60.0 | seconds | Max time to wait for Mopidy to confirm playback started |
| `MIN_PLAYBACK_DURATION` | 2.0 | seconds | Minimum playback time before considering track "finished" |
| `STATUS_POLL_INTERVAL` | 0.5 | seconds | Minimum time between Mopidy status polls (caching) |

---

## I2C Addresses

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PCF8574_ADDRESS` | 0x20 | Button expander I2C address |
| `PCF8574_RGB_ADDRESS` | 0x21 | RGB LED expander I2C address |
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

---

## Volume Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `VOLUME_STEP` | 10 | Volume change per button press (0-100 scale) |
| `VOLUME_DEFAULT` | 50 | Default volume level on startup |

---

## Audio Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SAMPLE_RATE` | 44100 | Audio sample rate in Hz |
| `CHANNELS` | 1 | Number of audio channels (mono) |
| `AUDIO_FORMAT` | "S16_LE" | Audio format (16-bit signed, little-endian) |

---

## Network Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SERVER_HOST` | "localhost" | REST API server bind address |
| `SERVER_PORT` | 8080 | Internal API port (hardware ↔ server) |
| `MOPIDY_HOST` | "localhost" | Mopidy server address |
| `MOPIDY_PORT` | 6680 | Mopidy HTTP JSON-RPC port (deprecated) |
| `MPD_PORT` | 6600 | MPD protocol port (used by python-mpd2) |

---

## NFC Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `NFC_TIMEOUT` | 0.05 | NFC read timeout in seconds (non-blocking) |

---

## Recording Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `RECORDING_DEVICE` | "" | ALSA recording device (empty = default) |

---

## PTT (Push-to-Talk) Voice Command Settings

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PTT_ENABLED` | True | Enable/disable PTT feature |
| `PTT_LISTEN_DURATION` | 2.5 | Seconds to listen for voice command |
| `PTT_WAKE_PHRASE` | "hi speaker" | Required phrase before command |

**Note:** PTT uses Google Speech API and requires an internet connection.

---

## File Paths

Defined in `Main/config/paths.py`:

| Path | Description |
|------|-------------|
| `TAGS_JSON` | `Main/config/tags.json` - NFC chip to song mappings |
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
