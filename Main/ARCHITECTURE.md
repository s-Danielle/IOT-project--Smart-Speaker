# Smart Speaker - Architecture Documentation

## 📋 Overview

This is a **Raspberry Pi IoT Smart Speaker** project that uses NFC chips to trigger music playback. Users can scan NFC tags to play associated songs from Spotify or local files, record audio clips, and control playback through physical buttons.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SMART SPEAKER                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │   NFC    │    │ Buttons  │    │  Audio   │    │   LED    │      │
│  │ Scanner  │    │ (PCF8574)│    │ (Mopidy) │    │ (APA102) │      │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘      │
│       │               │               │               │            │
│       └───────────────┴───────┬───────┴───────────────┘            │
│                               │                                     │
│                      ┌────────▼────────┐                           │
│                      │   Controller    │                           │
│                      │  (State Machine)│                           │
│                      └────────┬────────┘                           │
│                               │                                     │
│                      ┌────────▼────────┐                           │
│                      │   HTTP Server   │◄──── Flutter App          │
│                      │   (REST API)    │                           │
│                      └─────────────────┘                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Structure

```
Main/
├── main.py              # Entry point - starts the application
├── server.py            # HTTP REST API server for mobile app
├── requirements.txt     # Python dependencies
├── setup.sh             # Installation script
│
├── core/                # Core business logic
│   ├── controller.py    # Main event loop & state machine
│   ├── state.py         # State enums & data classes
│   └── actions.py       # Pure action handlers
│
├── hardware/            # Hardware abstraction layer
│   ├── nfc_scanner.py   # PN532 NFC reader
│   ├── buttons.py       # PCF8574 button expander
│   ├── audio_player.py  # Mopidy music player wrapper
│   ├── recorder.py      # Audio recording (arecord)
│   ├── chip_store.py    # NFC tag database (tags.json)
│   ├── health.py        # Hardware health checks
│   └── leds.py          # APA102 LED strip (disabled)
│
├── ui/                  # User feedback
│   ├── ui_controller.py # Combined sound + light feedback
│   ├── sounds.py        # WAV sound playback
│   └── lights.py        # LED patterns (disabled)
│
├── config/              # Configuration
│   ├── settings.py      # Constants & hardware addresses
│   ├── paths.py         # File path definitions
│   └── tags.json        # NFC chip → song mappings
│
├── utils/               # Utilities
│   ├── logger.py        # Timestamped logging
│   └── setup_check.py   # Dependency checker
│
├── assets/
│   └── sounds/          # UI sound effects (WAV files)
│
├── local_files/         # User files
│   ├── recordings/      # Saved audio recordings
│   └── uploads/         # Uploaded music files
│
└── Docs/                # Additional documentation
    ├── AI_Guidelines.txt
    ├── MOPIDY_SETUP.md
    └── States.txt
```

---

## 🎯 State Machine

The speaker operates as a finite state machine with **5 states**:

```
                    ┌──────────────────┐
                    │  IDLE_NO_CHIP    │◄─────────────────────────────┐
                    │  (No chip loaded)│                              │
                    └────────┬─────────┘                              │
                             │                                        │
                      Scan NFC chip                      Stop (long press 3s)
                             │                           from IDLE/PLAYING/PAUSED
                             ▼                                        │
                    ┌──────────────────┐                              │
      ┌────────────►│ IDLE_CHIP_LOADED │◄────────────┐                │
      │             │  (Ready to play) │             │                │
      │             └────────┬─────────┘             │                │
      │  ▲                   │                       │                │
      │  │            Play/Pause                   Stop               │
      │  │                   │                       │                │
      │  │                   ▼                       │                │
      │  │          ┌──────────────────┐             │                │
      │  │          │     PLAYING      │◄────┐       │                │
      │  │          │ (Music playing)  │     │       │                │
      │  │          └────────┬─────────┘     │       │                │
      │  │                   │               │       │                │
      │  │            Play/Pause        Play/Pause   │                │
      │  │                   │               │       │                │
      │  │                   ▼               │       │                │
      │  │          ┌──────────────────┐     │       │                │
      │  │          │     PAUSED       │─────┘       │                │
      │  │          │ (Music paused)   │─────────────┘                │
      │  │          └─────────┬────────┘                              │
      │  │                    │                                       │
      │  │                    │  Hold Record 3s                       │
      │  │                    │  (from any chip-loaded state)         │
      │  │                    ▼                                       │
      │  │          ┌──────────────────┐                              │
      │  │          │    RECORDING     │  (chip stays loaded!)        │
      │  │          │ (Recording audio)│                              │
      │  │          └─────────┬────────┘                              │
      │  │                    │                                       │
      │  │    Stop (short     │  Save or                              │
      │  │    OR long 3s)     │  Cancel                               │
      │  │    = Cancel        │                                       │
      │  │                    │                                       │
      │  └────────────────────┘                                       │
      │                                                               │
      │  Save recording (was playing/paused) → PAUSED                 │
      │  Save recording (was idle) → IDLE_CHIP_LOADED                 │
      │  Cancel recording → returns to previous state                 │
      └───────────────────────────────────────────────────────────────┘
```

> **Important:** Long press Stop (3s) clears chip from ALL states **EXCEPT RECORDING**.
> During recording, both short and long press Stop just cancel the recording and keep the chip loaded.

### State Descriptions

| State | Description |
|-------|-------------|
| `IDLE_NO_CHIP` | No NFC chip is loaded. Most actions are blocked. |
| `IDLE_CHIP_LOADED` | An NFC chip is scanned and ready. Can play or record. |
| `PLAYING` | Music is currently playing. |
| `PAUSED` | Music is paused, can be resumed. |
| `RECORDING` | Audio recording in progress. **Chip remains loaded.** |

### Recording State Transitions

Recording **requires a chip to be loaded** and **always keeps the chip loaded**:

| From State | After Save | After Short Stop (Cancel) | After Long Stop (Cancel) |
|------------|------------|---------------------------|--------------------------|
| `IDLE_CHIP_LOADED` | → `IDLE_CHIP_LOADED` | → `IDLE_CHIP_LOADED` | → `IDLE_CHIP_LOADED` |
| `PLAYING` | → `PAUSED` | → `PLAYING` (resumes) | → `IDLE_CHIP_LOADED` |
| `PAUSED` | → `PAUSED` | → `PAUSED` | → `IDLE_CHIP_LOADED` |

> **Note:** During RECORDING, both short and long press Stop just cancel the recording. The chip is **never cleared** from the RECORDING state. Long press Stop only clears the chip from other states (IDLE_CHIP_LOADED, PLAYING, PAUSED).

---

## 🔘 Button Controls

Three physical buttons are connected via a **PCF8574 I2C expander**:

| Button | Short Press | Long Press (3s) |
|--------|-------------|-----------------|
| **Play/Pause** | Toggle play/pause | Hold 2s → Play latest recording |
| **Record** | Save recording (when recording) | Hold 3s → Start recording |
| **Stop** | Stop playback / Cancel recording | Clear chip → IDLE_NO_CHIP* |

> *Exception: During RECORDING, long press Stop just cancels the recording (same as short press). Chip stays loaded.

---

## 📂 File-by-File Breakdown

### Entry Point

#### `main.py`
The application entry point that:
1. Prints a startup banner with usage instructions
2. Checks and installs missing dependencies
3. Verifies Mopidy connection
4. Optionally runs hardware health checks (`--health-check` flag)
5. Starts the HTTP server on port 8080 (background thread)
6. Creates and runs the main `Controller` loop

```python
# Key flow:
def main():
    print_banner()                    # Show welcome message
    check_and_install_dependencies()  # Verify/install deps
    check_mopidy_connection()         # Test Mopidy
    start_server(port=8080)           # Start REST API
    controller = Controller()         # Initialize hardware
    controller.run()                  # Main event loop
```

---

### Core Logic

#### `core/controller.py`
The **heart of the application** - implements the main event loop and state machine.

**Key Responsibilities:**
- Initialize all hardware components (NFC, buttons, audio, recorder, UI)
- Run a non-blocking polling loop (50ms interval)
- Handle NFC chip detection (edge detection for arrival/removal)
- Process button presses with timing (short vs long press)
- Delegate to action handlers for state transitions

**Main Loop:**
```python
def run(self):
    while self._running:
        self._buttons.update()     # Poll button states
        self._handle_nfc()         # Check for NFC chips
        self._handle_buttons()     # Process button presses
        time.sleep(LOOP_INTERVAL)  # 50ms
```

**NFC Handling:**
- Uses **edge detection** (only reacts when chip arrives, not continuously)
- Looks up chip data from `ChipStore` (tags.json)
- Blocks NFC during recording
- Stops current playback when new chip is scanned

**Button Handling:**
- Tracks press duration for long-press detection
- Play/Pause: Toggle playback or play latest recording (2s hold)
- Record: Hold 3s to start, press to save
- Stop: Short=stop, Long 3s=clear chip

---

#### `core/state.py`
Defines the data structures for device state:

```python
class State(Enum):
    IDLE_NO_CHIP = auto()
    IDLE_CHIP_LOADED = auto()
    PLAYING = auto()
    PAUSED = auto()
    RECORDING = auto()

@dataclass
class ChipData:
    uid: str          # NFC chip unique ID
    name: str         # Human-readable name
    uri: str          # Music URI (spotify:track:xxx or file://)
    metadata: dict    # Additional data

@dataclass
class DeviceState:
    state: State                      # Current state
    loaded_chip: Optional[ChipData]   # Currently loaded chip
    was_playing_before_recording: bool # For state restoration
    previous_state: Optional[State]    # For cancel recording
```

---

#### `core/actions.py`
**Pure action handlers** that perform state transitions. Each function:
- Takes current state + hardware references
- Performs the action (play, stop, record, etc.)
- Updates and returns the new state
- Triggers UI feedback

| Action | Description |
|--------|-------------|
| `action_load_chip()` | Load NFC chip data, transition to IDLE_CHIP_LOADED |
| `action_play()` | Start playback from loaded chip |
| `action_pause()` | Pause current playback |
| `action_resume()` | Resume paused playback |
| `action_stop()` | Stop playback, return to idle |
| `action_clear_chip()` | Unload chip, return to IDLE_NO_CHIP |
| `action_start_recording()` | Begin audio recording |
| `action_save_recording()` | Stop recording and save file |
| `action_cancel_recording()` | Stop recording without saving |

---

### Hardware Abstraction

#### `hardware/nfc_scanner.py`
Wrapper for the **PN532 NFC reader** via I2C.

- **Non-blocking reads**: Uses short timeout (100ms) to avoid blocking the main loop
- **Error suppression**: Common errors (no chip present) are suppressed to reduce log spam
- **UID format**: Returns UID as `bytearray(b'...')` string for tags.json lookup

```python
def read_uid(self) -> Optional[str]:
    # Returns UID string if chip present, None otherwise
    uid = self._pn532.read_passive_target(timeout=0.1)
    return str(bytearray(uid)) if uid else None
```

---

#### `hardware/buttons.py`
Wrapper for **PCF8574 I2C GPIO expander** (buttons are active-low).

**Features:**
- Polling-based button state detection
- Edge detection (`just_pressed()`, `just_released()`)
- Hold duration tracking for long-press detection

```python
class ButtonID(Enum):
    PLAY_PAUSE = auto()  # Bit 0
    RECORD = auto()      # Bit 1
    STOP = auto()        # Bit 2

# Usage in controller:
if buttons.is_pressed(ButtonID.STOP):
    hold_time = buttons.hold_duration(ButtonID.STOP)
    if hold_time >= 3.0:  # Long press
        # Clear chip
```

---

#### `hardware/audio_player.py`
Wrapper for **Mopidy** music server using JSON-RPC.

**Supported Operations:**
- `play_uri(uri)` - Play from URI (Spotify, local file, etc.)
- `pause()` / `resume()` - Pause/resume playback
- `stop()` - Stop playback and clear tracklist

**URI Formats Supported:**
- `spotify:track:XXXXX` - Spotify tracks (requires Mopidy-Spotify)
- `file:///path/to/file.wav` - Local files
- `local:file:filename.mp3` - Mopidy local library

```python
def _rpc(self, method: str, params: dict = None):
    # Send JSON-RPC to Mopidy at localhost:6680
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    requests.post(f"http://localhost:6680/mopidy/rpc", json=payload)
```

---

#### `hardware/recorder.py`
Audio recording using the system's **arecord** command.

**Features:**
- Starts `arecord` subprocess for recording
- Generates timestamped filenames: `recording_ChipName_20250113_120000.wav`
- Graceful stop (SIGTERM) with timeout handling
- Cancel option deletes the file

```python
def start(self, chip_name: str):
    # Uses CD quality: arecord -f cd output.wav
    arecord_cmd = ["arecord", "-f", "cd", self._current_file]
    self._process = subprocess.Popen(arecord_cmd, ...)
```

---

#### `hardware/chip_store.py`
Provides NFC chip lookup using `server_data.json` (unified with HTTP server).

**Features:**
- Uses same data source as the mobile app
- Auto-registers unknown chips when scanned (so they appear in app)
- Resolves song URIs from library by song_id

**Methods:**
- `lookup(uid)` - Find chip data by UID (auto-registers if new)
- `get_all_uids()` - List all known UIDs

---

#### `hardware/health.py`
Startup diagnostics that verify all hardware components are working:

| Check | What it tests |
|-------|---------------|
| NFC | PN532 firmware version readable |
| Buttons | PCF8574 responds on I2C bus |
| Audio | `arecord` command available |
| Mopidy | JSON-RPC connection succeeds |

Run with: `python main.py --health-check`

---

#### `hardware/leds.py`
**Currently disabled**. Placeholder for APA102 LED strip control.

---

### User Interface Feedback

#### `ui/ui_controller.py`
Combines **sounds** and **lights** for consistent feedback events:

| Event | Sound | Description |
|-------|-------|-------------|
| `on_chip_loaded()` | loaded_success.wav | NFC chip scanned successfully |
| `on_play()` | play.wav | Playback started |
| `on_pause()` | pause.wav | Playback paused |
| `on_stop()` | stop.wav | Playback stopped |
| `on_clear_chip()` | reset.wav | Chip cleared/unloaded |
| `on_record_start()` | countdown.wav | Recording started |
| `on_record_saved()` | saves_success.wav | Recording saved |
| `on_blocked_action()` | blocked.wav | Action not allowed |
| `on_error()` | failed.wav | Error occurred |

---

#### `ui/sounds.py`
Plays WAV files through Mopidy for audio feedback.

- **Cooldown**: 100ms minimum between sounds to prevent overlap
- **Uses Mopidy**: Converts file paths to `file://` URIs
- Sound files located in `assets/sounds/`

---

#### `ui/lights.py`
**Currently disabled**. All methods are no-ops.

---

### Configuration

#### `config/settings.py`
All hardware addresses and timing constants:

```python
# Timing
LOOP_INTERVAL = 0.05          # 50ms main loop
RECORD_HOLD_DURATION = 3.0    # Hold to start recording
CLEAR_CHIP_HOLD_DURATION = 3.0# Hold to clear chip
PLAY_LATEST_HOLD_DURATION = 2.0# Hold to play recording

# I2C Addresses
PCF8574_ADDRESS = 0x27        # Button expander
PN532_I2C_ADDRESS = 0x24      # NFC reader

# Mopidy
MOPIDY_HOST = "localhost"
MOPIDY_PORT = 6680
```

---

#### `config/paths.py`
Central file path definitions:

```python
BASE_DIR = "/path/to/Main/"
TAGS_JSON = BASE_DIR + "config/tags.json"
SOUNDS_DIR = BASE_DIR + "assets/sounds/"
RECORDINGS_DIR = BASE_DIR + "local_files/recordings/"
```

---

### HTTP Server (REST API)

#### `server.py`
HTTP server for the **Flutter mobile app** and **unified data management**.

This is the **single source of truth** for all chip and library data. Both the mobile app and NFC scanner read from the same `server_data.json` file.

**Key Features:**
- Unified data store shared with NFC scanner
- Auto-migration from old `tags.json` format
- Thread-safe data access
- Auto-registers new chips when scanned

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Connection status |
| GET | `/chips` | List all chips (with uid, name, song_id) |
| GET | `/library` | List all songs in library |
| PUT | `/chips/{id}` | Update chip name or song assignment |
| PUT | `/library/{id}` | Update song metadata |
| POST | `/library` | Add new song to library |
| POST | `/files` | Upload audio file |
| DELETE | `/chips/{id}/assignment` | Clear chip's song assignment |
| DELETE | `/library/{id}` | Delete song from library |

**Data Storage:**
- `server_data.json` - Unified storage for chips & library (shared with NFC scanner)
- `local_files/uploads/` - Uploaded audio files
- `local_files/recordings/` - Audio recordings

---

### Utilities

#### `utils/logger.py`
Timestamped logging with emoji-enhanced categories:

```
[2025-01-13 12:00:00.123] [ACTION] Loading chip: MyFirstChip
[2025-01-13 12:00:00.124] [STATE] → IDLE_CHIP_LOADED
[2025-01-13 12:00:00.125] [EVENT] 📀 CHIP LOADED
[2025-01-13 12:00:00.126] [SOUND] 🔊 Playing: CHIP LOADED
```

---

#### `utils/setup_check.py`
Verifies dependencies on startup:
- Checks for `requests`, `adafruit_pn532`, `smbus2`
- Tests Mopidy connection
- Offers to auto-install missing packages

---

## 🔄 Data Flow

### NFC Chip Scan → Play Music

```
1. NFCScanner.read_uid()        → Returns "bytearray(b'...')"
2. ChipStore.lookup(uid)        → Returns {name, uri, ...}
3. actions.action_load_chip()   → Updates DeviceState
4. UIController.on_chip_loaded()→ Plays sound
5. User presses Play/Pause
6. actions.action_play()        → Calls AudioPlayer.play_uri()
7. Mopidy plays the music
```

### Recording Flow

```
1. User holds Record button for 3s (chip must be loaded!)
2. Controller detects hold duration >= 3s
3. actions.action_start_recording()
   - Saves previous state (IDLE_CHIP_LOADED, PLAYING, or PAUSED)
   - Pauses any playing music
   - Starts arecord subprocess
4. State → RECORDING (chip remains loaded)

5a. User presses Record again → SAVE:
    - actions.action_save_recording()
    - Stops arecord, saves file
    - Adds to library
    - State → PAUSED (if was playing/paused) or IDLE_CHIP_LOADED
    - Chip stays loaded!

5b. User presses Stop (short OR long) → CANCEL:
    - actions.action_cancel_recording()
    - Stops arecord, deletes file
    - State → returns to EXACT previous state (PLAYING resumes)
    - Chip stays loaded!

NOTE: Long press Stop does NOT clear the chip during recording!
      Long press Stop only clears chip from other states.
```

---

## 🚀 Running the Application

### Prerequisites

1. **Raspberry Pi** with:
   - PN532 NFC reader (I2C)
   - PCF8574 button expander (I2C)
   - Speaker/audio output

2. **Mopidy** music server running:
   ```bash
   sudo systemctl start mopidy
   ```

3. **Python dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

### Start the Application

```bash
cd Main/
python3 main.py
```

### Command-line Options

| Flag | Description |
|------|-------------|
| `--health-check` | Run hardware diagnostics on startup |
| `--skip-setup` | Skip dependency check |
| `--strict` | Exit if health check fails |

---

## 🔧 Hardware Connections

### I2C Bus

| Device | Address | Purpose |
|--------|---------|---------|
| PN532 | 0x24 | NFC reader |
| PCF8574 | 0x27 | Button GPIO expander |

### Button Wiring (PCF8574)

| Pin | Button |
|-----|--------|
| P0 | Play/Pause |
| P1 | Record |
| P2 | Stop |

*Buttons are active-low (connect to GND when pressed)*

---

## 📱 Mobile App Integration

The Flutter app (`flutter_app/`) connects to the HTTP server to:
- View and manage NFC chip assignments
- Browse and organize the music library
- Upload new audio files
- Rename chips and songs

Connect via:
- Android Emulator: `http://10.0.2.2:8080`
- Physical device: `http://<raspberry-pi-ip>:8080`

---

## 📝 Configuration Files

### `server_data.json` (Unified Data Store)

This is the **single source of truth** for both the NFC scanner and the mobile app.

```json
{
  "chips": [
    {
      "id": "chip001",
      "uid": "bytearray(b'\\xe4\\x1c\\x9d\\xbb')",
      "name": "Kids Songs",
      "song_id": "song001",
      "song_name": "Morning Jazz"
    }
  ],
  "library": [
    {
      "id": "song001", 
      "name": "Morning Jazz",
      "uri": "spotify:track:5hnyJvgoWiQUYZttV4wXy6"
    }
  ]
}
```

### Adding a New Chip

1. **Scan the chip** - it will be auto-registered and appear in the app
2. **Open the mobile app** - find the new chip in the list
3. **Assign a song** - select a song from the library
4. **Scan again** - music will play!

### Migration from `tags.json`

If you have existing chips in `config/tags.json`, they will be automatically migrated to `server_data.json` on first startup.

---

## 🎵 Supported Audio Sources

| Source | URI Format | Requirements |
|--------|------------|--------------|
| Spotify | `spotify:track:XXXXX` | Mopidy-Spotify extension |
| Local files | `file:///absolute/path.mp3` | Mopidy-Local extension |
| Recordings | `file:///path/to/recording.wav` | Automatic |

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| NFC not detected | Check I2C wiring, run `i2cdetect -y 1` |
| Buttons not working | Verify PCF8574 address, check wiring |
| No audio | Ensure Mopidy is running: `systemctl status mopidy` |
| Spotify not playing | Configure Mopidy-Spotify with credentials |
| Recording fails | Install alsa-utils: `apt install alsa-utils` |

---

## 📚 Additional Documentation

- `Docs/MOPIDY_SETUP.md` - Mopidy installation guide
- `Docs/States.txt` - State machine reference
- `Docs/AI_Guidelines.txt` - Development guidelines

