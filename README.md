# Smart Speaker - Raspberry Pi IoT Project

A smart speaker system that uses NFC chips to trigger music playback. Scan an NFC tag to instantly play your favorite songs from Spotify or local files, record voice memos, and control everything through physical buttons or a companion mobile app.

## Features

- **NFC-Triggered Playback**: Scan NFC tags to instantly play associated music
- **Multiple Audio Sources**: Supports Spotify tracks and local audio files via Mopidy
- **Voice Recording**: Record audio clips and save them to chips
- **Physical Controls**: Three buttons for Play/Pause, Record, and Stop
- **Mobile App**: Flutter companion app for managing chips and music library
- **Audio Feedback**: Sound effects for all interactions

## Hardware Components

| Component | Purpose |
|-----------|---------|
| Raspberry Pi | Main controller |
| PN532 NFC Reader | Read NFC chip UIDs (I2C) |
| PCF8574 GPIO Expander | Button input handling (I2C) |
| 3 Physical Buttons | Play/Pause, Record, Stop |
| Speaker/Audio Output | Music playback & feedback sounds |
| Microphone | Audio recording |

## Controls

| Button | Short Press | Long Press (3s) |
|--------|-------------|-----------------|
| **Play/Pause** | Toggle playback | Play latest recording (2s) |
| **Record** | Save recording | Start recording |
| **Stop** | Stop / Cancel | Clear chip |

## Project Structure

```
├── Main/                    # Python application
│   ├── main.py              # Entry point
│   ├── server.py            # REST API for mobile app
│   ├── core/                # State machine & actions
│   ├── hardware/            # Hardware abstraction (NFC, buttons, audio)
│   ├── ui/                  # Sound & light feedback
│   ├── config/              # Settings & NFC tag mappings
│   └── ARCHITECTURE.md      # Detailed documentation
│
├── flutter_app/             # Mobile companion app
├── Unit-tests/              # Hardware component tests
└── include/                 # WiFi module headers
```

## Quick Start

### Prerequisites

1. **Raspberry Pi** with I2C enabled
2. **Mopidy** music server installed and running
3. **Python 3.7+**

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd IOT-project--Smart-Speaker/Main

# Install dependencies
pip3 install -r requirements.txt

# Start Mopidy (if not running)
sudo systemctl start mopidy

# Run the application
python3 main.py
```

### Configuration

1. **Add NFC Tags**: Edit `Main/config/tags.json` to map chip UIDs to songs:
   ```json
   {
     "bytearray(b'\\xe4\\x1c\\x9d\\xbb')": {
       "name": "My Favorite Song",
       "uri": "spotify:track:XXXXX"
     }
   }
   ```

2. **I2C Addresses** (in `Main/config/settings.py`):
   - PN532 NFC: `0x24`
   - PCF8574 Buttons: `0x27`

## Mobile App

The Flutter app connects to the speaker's REST API (port 8080) to:
- View and rename NFC chips
- Assign songs to chips
- Manage the music library
- Upload audio files

## Documentation

- [`Main/ARCHITECTURE.md`](Main/ARCHITECTURE.md) - Complete architecture documentation
- [`Main/Docs/States.txt`](Main/Docs/States.txt) - State machine reference
- [`Main/Docs/MOPIDY_SETUP.md`](Main/Docs/MOPIDY_SETUP.md) - Mopidy installation guide

## Dependencies

### Python Libraries
- `requests` - Mopidy JSON-RPC communication
- `adafruit-circuitpython-pn532` - NFC reader driver
- `smbus2` - I2C communication for buttons

### System Requirements
- Mopidy music server
- ALSA utils (`arecord` for recording)
- I2C enabled on Raspberry Pi

---

This project is part of ICST - The Interdisciplinary Center for Smart Technologies, Taub Faculty of Computer Science, Technion  
https://icst.cs.technion.ac.il/
