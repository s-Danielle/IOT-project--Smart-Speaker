# Smart Speaker - Raspberry Pi IoT Project

A smart speaker system that uses NFC chips to trigger music playback. Scan an NFC tag to instantly play songs from Spotify or local files, record voice memos, and control playback through physical buttons, voice commands, or a companion mobile app.

## Features

| Feature | Description | Status |
|---------|-------------|--------|
| NFC Playback | Scan NFC tags to instantly play associated music | Done |
| Multiple Audio Sources | Spotify tracks and local files via Mopidy | Done |
| Voice Recording | Record audio clips and save to chips | Done |
| Physical Buttons | Play/Pause, Record, Stop controls | Done |
| Mobile App | Flutter app for chip and library management | Done |
| Audio Feedback | Sound effects for all interactions | Done |
| Parental Controls | Volume limits, quiet hours, chip whitelist | Done |
| PTT Voice Commands | Press-to-talk voice control (play, pause, stop) | Done |
| Developer Tools | Remote logs, service management, git operations | Done |
| Service Architecture | Separate server and hardware services | Done |
| WiFi Provisioning | AP mode fallback + app-based WiFi management | Done |
| Health Monitor | LED status indicators + health API | Done |

## Hardware

| Component | Purpose | I2C Address |
|-----------|---------|-------------|
| Raspberry Pi | Main controller | - |
| PN532 NFC Reader | Read NFC chip UIDs | 0x24 |
| PCF8574 (Buttons) | Button input handling | 0x20 |
| PCF8574 (LEDs) | RGB LED control | 0x21 |
| Speaker | Audio output | - |
| Microphone | Voice recording & commands | - |

## Button Controls

| Button | Short Press | Long Press (3s) |
|--------|-------------|-----------------|
| Play/Pause | Toggle playback | Play latest recording (2s hold) |
| Record | Save recording | Start recording |
| Stop | Stop / Cancel | Clear chip |
| PTT | - | Voice command (hold to speak) |

## Project Structure

```
├── Main/                    # Python backend
│   ├── main.py              # Hardware controller entry
│   ├── server.py            # REST API server
│   ├── server_main.py       # Server standalone entry
│   ├── health_monitor.py    # Health LED service
│   ├── wifi_provisioner.py  # WiFi AP fallback
│   ├── core/                # State machine & actions
│   ├── hardware/            # NFC, buttons, audio, LEDs
│   ├── ui/                  # Sound & light feedback
│   └── config/              # Settings & chip mappings
│
├── flutter_app/             # Mobile companion app
│   └── lib/
│       ├── screens/         # UI screens
│       └── services/        # API client
│
├── services/                # Systemd service files
│   ├── smart_speaker.service
│   ├── smart_speaker_server.service
│   ├── smart_speaker_health.service
│   └── smart_speaker_wifi.service
│
└── Unit-tests/              # Hardware component tests
```

## Installation

### Prerequisites

- Raspberry Pi with I2C enabled
- Mopidy music server
- Python 3.7+
- NetworkManager (for WiFi provisioning)

### Quick Start

```bash
# Clone repository
git clone <repo-url>
cd IOT-project--Smart-Speaker

# Install Python dependencies
pip3 install -r requirements.txt

# Install PTT voice command dependencies
cd scripts && ./install-ptt-deps.sh && cd ..

# Start Mopidy
sudo systemctl start mopidy

# Run manually (for testing)
cd Main && python3 main.py
```

### Service Installation

```bash
# Install all services
cd services
sudo ./copy-and-enable-service.sh

# Or install individually:
sudo cp smart_speaker*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smart_speaker_server smart_speaker smart_speaker_health
sudo systemctl start smart_speaker_server smart_speaker smart_speaker_health
```

### Sudoers Configuration

Add to `/etc/sudoers.d/smart_speaker`:
```
iot-proj ALL=(ALL) NOPASSWD: /bin/systemctl restart smart_speaker
iot-proj ALL=(ALL) NOPASSWD: /bin/systemctl restart smart_speaker_server
iot-proj ALL=(ALL) NOPASSWD: /bin/systemctl stop smart_speaker
iot-proj ALL=(ALL) NOPASSWD: /bin/systemctl start smart_speaker
iot-proj ALL=(ALL) NOPASSWD: /sbin/reboot
iot-proj ALL=(ALL) NOPASSWD: /usr/bin/nmcli
```

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Connection status |
| GET | `/health` | Health check |
| GET | `/chips` | List all chips |
| GET | `/library` | List all songs |
| PUT | `/chips/{id}` | Update chip |
| POST | `/library` | Add song |
| POST | `/files` | Upload audio file |

### Debug Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/debug/speaker/status` | Hardware controller status |
| POST | `/debug/speaker/restart` | Restart hardware service |
| GET | `/debug/logs` | View recent logs |
| GET | `/debug/system` | CPU temp, memory, uptime |
| POST | `/debug/git-pull` | Pull latest code |
| POST | `/debug/reboot` | Reboot device |

### WiFi Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/debug/wifi/status` | Current connection |
| GET | `/debug/wifi/scan` | Available networks |
| POST | `/debug/wifi/connect` | Connect to network |
| POST | `/debug/wifi/forget` | Remove saved network |
| POST | `/debug/wifi/ap-mode` | Force AP mode |

### Parental Control Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/parental/settings` | Get parental settings |
| PUT | `/parental/settings` | Update settings |

## Mobile App

The Flutter app connects to the speaker's REST API (port 5000) to:
- View and rename NFC chips
- Assign songs to chips
- Manage the music library
- Configure parental controls
- Access developer tools (logs, services, WiFi)

Connect via: `http://<raspberry-pi-ip>:5000`

## LED Indicators

| LED | Color | Meaning |
|-----|-------|---------|
| Health (Light 1) | Green | All systems OK |
| Health (Light 1) | Yellow | No internet |
| Health (Light 1) | Red | System error |
| Health (Light 1) | Blue (pulsing) | AP mode / WiFi setup |
| Player (Light 2) | Green | Playing |
| Player (Light 2) | Yellow | Paused |
| Player (Light 2) | Red | Recording |

## Voice Commands

Hold the PTT button and speak:
- "hi speaker play" - Play/resume
- "hi speaker pause" - Pause
- "hi speaker stop" - Stop
- "hi speaker clear" - Clear chip

## WiFi Setup

### First-Time Setup (No WiFi Configured)

1. Power on the Smart Speaker
2. Wait 30 seconds - if no known WiFi is found, it creates a hotspot
3. LED 1 will pulse blue when in AP mode
4. Connect your phone to **"SmartSpeaker-Setup"** WiFi network
5. Open browser - captive portal appears automatically (or go to `192.168.4.1`)
6. Select your WiFi network and enter password
7. Device reboots and connects to your network

### Managing WiFi from the App

Once connected, use the mobile app's Developer Tools to:
- View current connection status
- Scan for available networks
- Connect to new networks
- Forget saved networks
- Force AP mode for testing

### Install WiFi Provisioner Service

```bash
cd services
sudo ./install-wifi-provisioner.sh
```

### Manual AP Mode Testing

```bash
# Start hotspot manually
sudo nmcli device wifi hotspot ssid SmartSpeaker-Setup

# Check WiFi status
nmcli device wifi list

# Connect to a network
sudo nmcli device wifi connect "NetworkName" password "password"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| NFC not detected | Check I2C: `i2cdetect -y 1`, verify 0x24 |
| Buttons not working | Check PCF8574 at 0x20 |
| No audio | `systemctl status mopidy` |
| Service won't start | Check logs: `tail -f /var/log/smart_speaker.log` |
| WiFi issues | Force AP mode from app, connect to "SmartSpeaker-Setup" |

## Log Files

- Server: `/var/log/smart_speaker_server.log`
- Hardware: `/var/log/smart_speaker.log`

---

ICST - The Interdisciplinary Center for Smart Technologies  
Taub Faculty of Computer Science, Technion  
https://icst.cs.technion.ac.il/
