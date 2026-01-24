# Smart Speaker - Fixes & Improvements

## Overview

| # | Fix/Improvement | Status |
|---|-----------------|--------|
| 1 | Recording Countdown Sync | DONE |
| 2 | Recording Time Limit | TODO |
| 3 | Debug Service | DONE |
| 4 | WiFi Config on Boot | TODO |
| 5 | Advanced App Settings | DONE |
| 6 | Stale Chip Data Fix | DONE |
| 7 | LED Feedback System | TODO |

---

## 1. 🔧 Recording Countdown Sync Fix (5 min)

**Problem:** `countdown.wav` is 3.8s but `RECORD_HOLD_DURATION` is 3.0s  
**Solution:** Change `RECORD_HOLD_DURATION` to 4.0s to match audio

**File:** `Main/config/settings.py`
```python
RECORD_HOLD_DURATION = 3.8  # Was 3.0, now matches countdown.wav length exactly
```

---

## 2. ⏱️ Recording Time Limit (1 hr)

**Problem:** Recordings can go on forever, fill up storage  
**Solution:** Auto-stop recording after configurable duration

**Implementation:**
- Add `MAX_RECORDING_SECONDS` to settings (default: 60s)
- Timer in recorder that auto-stops
- Warning sound at 10s remaining
- Show remaining time in app (via WebSocket)

---

## 3. 🐛 Debug Service - DONE ✅

**What:** Systemd service that logs to file for debugging

**Implemented:**
- Both services log to `/var/log/smart_speaker*.log`
- Server: `/var/log/smart_speaker_server.log`
- Hardware: `/var/log/smart_speaker.log`

**Service files:**
```ini
# services/smart_speaker_server.service
StandardOutput=append:/var/log/smart_speaker_server.log
StandardError=append:/var/log/smart_speaker_server.log

# services/smart_speaker.service
StandardOutput=append:/var/log/smart_speaker.log
StandardError=append:/var/log/smart_speaker.log
```

---

## 4. 📶 WiFi Configuration on Boot (2-3 hrs)

**What:** If no WiFi, create hotspot for configuration

**Flow:**
```
Boot → Check WiFi → Connected? 
  ├─ Yes → Start normally (green LED pulse)
  └─ No → Create hotspot "SmartSpeaker-Setup" (blue pulsing LED)
          → User connects → Configures WiFi via captive portal
          → Reboot → Connect to configured WiFi
```

**Recommended Approach: `comitup`**
- Raspberry Pi WiFi provisioning package
- Creates AP with captive portal when no WiFi
- Web UI for network selection
- Automatically connects after config

**Installation:**
```bash
sudo apt install comitup comitup-web
sudo systemctl enable comitup
```

**Configuration (`/etc/comitup.conf`):**
```ini
ap_name: SmartSpeaker-Setup
web_ui_port: 80
```

**LED Integration:**
- Blue pulsing = AP mode (waiting for config)
- Yellow breathing = Connecting to WiFi
- Green pulse = Connected successfully
- Red flash = Connection failed

---

## 5. 📱 Advanced App Settings - DONE ✅

### Implemented Endpoints

| Feature | Endpoint | Description |
|---------|----------|-------------|
| View I2C Devices | `GET /debug/i2c` | List all I2C devices |
| Speaker Status | `GET /debug/speaker/status` | Hardware controller status |
| Start Speaker | `POST /debug/speaker/start` | Start hardware controller |
| Stop Speaker | `POST /debug/speaker/stop` | Stop hardware controller |
| Restart Speaker | `POST /debug/speaker/restart` | Restart hardware controller |
| View Error Log | `GET /debug/logs` | Last 100 lines of log |
| View System Info | `GET /debug/system` | CPU temp, memory, disk, uptime |
| Git Pull | `POST /debug/git-pull` | Pull latest code from repo |
| Git Status | `GET /debug/git-status` | Current branch, changes |
| Daemon Reload | `POST /debug/service/daemon-reload` | Reload systemd daemon |
| Reboot Pi | `POST /debug/reboot` | Reboot the Raspberry Pi |

### API Implementation

```python
# Main/server.py - Add debug endpoints

def get_i2c_devices():
    result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
    return {"output": result.stdout}

def get_logs():
    result = subprocess.run(['tail', '-100', '/var/log/smart_speaker.log'], 
                          capture_output=True, text=True)
    return {"logs": result.stdout.split('\n')}

def restart_service():
    subprocess.run(['sudo', 'systemctl', 'restart', 'smart_speaker'])
    return {"status": "restarting"}

def git_pull():
    result = subprocess.run(['git', 'pull'], 
                          cwd='/home/iot-proj/IOT-project--Smart-Speaker',
                          capture_output=True, text=True)
    return {"stdout": result.stdout, "stderr": result.stderr}

def git_status():
    branch = subprocess.run(['git', 'branch', '--show-current'],
                          cwd='/home/iot-proj/IOT-project--Smart-Speaker',
                          capture_output=True, text=True)
    status = subprocess.run(['git', 'status', '--short'],
                          cwd='/home/iot-proj/IOT-project--Smart-Speaker',
                          capture_output=True, text=True)
    return {"branch": branch.stdout.strip(), "status": status.stdout}

def system_info():
    temp = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True)
    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
    return {"temperature": temp.stdout.strip(), "uptime": uptime.stdout.strip()}

def reboot_pi():
    subprocess.Popen(['sudo', 'reboot'])
    return {"status": "rebooting"}
```

### Flutter Screen Layout

```
┌─────────────────────────────────────────┐
│        ⚙️ Advanced Settings             │
├─────────────────────────────────────────┤
│  📡 Hardware: I2C @ 0x24, 0x27          │
│  🌡️ CPU: 45°C  |  ⏱️ Up: 3 days        │
├─────────────────────────────────────────┤
│  [Restart Service]    [Reboot Pi]       │
├─────────────────────────────────────────┤
│  📋 [View Logs]                         │
├─────────────────────────────────────────┤
│  🔀 Branch: main ✓                      │
│  [Git Pull]    [View Changes]           │
└─────────────────────────────────────────┘
```

### Sudoers Config (Required)

```bash
# /etc/sudoers.d/smart_speaker
iot-proj ALL=(ALL) NOPASSWD: /bin/systemctl restart smart_speaker
iot-proj ALL=(ALL) NOPASSWD: /sbin/reboot
```

---

## 6. 🔄 Stale Chip Data Fix - DONE ✅

**Problem:** When you update a chip's song in the app, pressing play used cached data instead of fetching fresh data from the server.

**Solution:** `action_play()` now always fetches fresh chip data from the server before playing.

**Files Modified:**
- `Main/core/actions.py` - Added `chip_store` parameter to `action_play`, fetches fresh data
- `Main/core/controller.py` - Passes `chip_store` to `action_play` calls

---

## 7. 💡 LED Feedback System (2-3 hrs)

**What:** Visual feedback through 2 dedicated RGB LEDs

**Hardware:** PCF8574 I2C expander at 0x21
- Light 1 (P0-P2): **Device Health**
- Light 2 (P3-P5): **Player State**
- Future: Light 3 for PTT mode (separate expander or additional pins)

---

### Light 1: Device Health LED

| State | Color | Pattern |
|-------|-------|---------|
| Healthy / Connected | Green | Solid |
| WiFi AP Mode (setup) | Blue | Slow blink |
| WiFi Connecting | Yellow | Fast blink |
| Service Error | Red | Solid |
| Hardware Error | Red | Fast blink |
| Booting | Cyan | Pulse |

---

### Light 2: Player State LED

| State | Color | Pattern |
|-------|-------|---------|
| Idle | Off | - |
| NFC Chip Scanned | Blue | Quick flash |
| Playing | Green | Solid |
| Paused | Yellow | Solid |
| Recording | Red | Pulse |
| Recording Countdown | Red | Blink (sync with countdown) |
| Blocked (Parental) | Magenta | Double flash |
| Error (playback) | Red | Quick flash |

---

### Future: Light 3 - PTT Voice Mode

| State | Color | Pattern |
|-------|-------|---------|
| PTT Idle | Off | - |
| Listening | Blue | Pulse |
| Processing | Cyan | Fast pulse |
| Command OK | Green | Flash |
| Command Failed | Red | Flash |

---

### Implementation

**Files to modify/create:**
- `Main/hardware/leds.py` - Low-level PCF8574 control
- `Main/ui/lights.py` - High-level state → LED mapping

**Code Structure:**
```python
# Main/hardware/leds.py
from smbus2 import SMBus

I2C_ADDRESS = 0x21
LIGHT1_PINS = (0, 1, 2)  # Device Health (R, G, B)
LIGHT2_PINS = (3, 4, 5)  # Player State (R, G, B)

class RGBLeds:
    """Control 2 RGB LEDs via PCF8574"""
    
    def __init__(self):
        self.bus = SMBus(1)
        self._state = 0x00
    
    def set_health(self, r: bool, g: bool, b: bool):
        """Set device health LED (Light 1)"""
        self._set_light(LIGHT1_PINS, r, g, b)
    
    def set_player(self, r: bool, g: bool, b: bool):
        """Set player state LED (Light 2)"""
        self._set_light(LIGHT2_PINS, r, g, b)
    
    def _set_light(self, pins, r, g, b):
        for pin, on in zip(pins, (r, g, b)):
            if on:
                self._state |= (1 << pin)
            else:
                self._state &= ~(1 << pin)
        self.bus.write_byte(I2C_ADDRESS, self._state)
```

```python
# Main/ui/lights.py
import threading
import time

class Colors:
    OFF =     (False, False, False)
    RED =     (True,  False, False)
    GREEN =   (False, True,  False)
    BLUE =    (False, False, True)
    YELLOW =  (True,  True,  False)
    CYAN =    (False, True,  True)
    MAGENTA = (True,  False, True)

class Lights:
    """High-level LED state management"""
    
    def __init__(self, leds: RGBLeds):
        self.leds = leds
        self._blink_thread = None
        self._stop_blink = threading.Event()
    
    # Device Health
    def health_ok(self):
        self.leds.set_health(*Colors.GREEN)
    
    def health_wifi_setup(self):
        self._blink_health(Colors.BLUE, interval=1.0)
    
    def health_error(self):
        self.leds.set_health(*Colors.RED)
    
    # Player State
    def player_idle(self):
        self.leds.set_player(*Colors.OFF)
    
    def player_playing(self):
        self.leds.set_player(*Colors.GREEN)
    
    def player_paused(self):
        self.leds.set_player(*Colors.YELLOW)
    
    def player_recording(self):
        self._pulse_player(Colors.RED, interval=0.5)
    
    def player_blocked(self):
        self._double_flash(Colors.MAGENTA)
```

**Integration points:**
- `core/controller.py` - Call `lights.player_*()` on state changes
- `server.py` - Call `lights.health_*()` on startup/errors
- WiFi provisioning script - Call `lights.health_wifi_setup()`

---

## Priority Order

| # | Item | Time | Value |
|---|------|------|-------|
| 1 | Recording Sync Fix | DONE | Bug fix |
| 2 | Recording Time Limit | 1 hr | ⭐⭐⭐ |
| 3 | Advanced App Settings | DONE | ⭐⭐⭐⭐⭐ |
| 4 | Debug Service | DONE | ⭐⭐⭐⭐ |
| 5 | WiFi Config | TODO | ⭐⭐⭐⭐ |
| 6 | Stale Chip Data Fix | DONE | Bug fix |
| 7 | LED Feedback | TODO | ⭐⭐⭐⭐⭐ |
