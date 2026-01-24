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

**What:** Visual feedback through 2 dedicated RGB LEDs with separate concerns

**Hardware:** PCF8574 I2C expander at 0x21
- **Light 1 (P0-P2):** Device Health - controlled by **health service** (Main ignores)
- **Light 2 (P3-P5):** Player State - controlled by **Main**
- Future: Light 3 for PTT mode

**Available Colors:**
| Color | R | G | B | Use |
|-------|---|---|---|-----|
| Red | ✓ | | | Errors, recording |
| Green | | ✓ | | OK, playing |
| Blue | | | ✓ | WiFi setup, NFC scan |
| Yellow | ✓ | ✓ | | Partial/warning, paused |
| Cyan | | ✓ | ✓ | Loading, hardware-only |
| Magenta | ✓ | | ✓ | Blocked, server-only |
| White | ✓ | ✓ | ✓ | Booting, volume |

---

### Light 1: Device Health LED (Separate Health Service)

**Main does NOT control this LED** - managed by `health_monitor.py` service

| State | Color | Pattern | Meaning |
|-------|-------|---------|---------|
| All Systems Go | Green | Solid | Internet ✓ Server ✓ Hardware ✓ |
| WiFi Provisioning | Blue | Slow pulse | AP mode, waiting for config |
| Connecting to WiFi | Blue | Fast blink | Trying to connect |
| Partially Up | Yellow | Solid | Some services running, not all |
| Hardware Only | Cyan | Solid | Hardware OK, no internet/server |
| Server Only | Magenta | Solid | Server OK, hardware not responding |
| No Internet | Yellow | Slow blink | WiFi connected but no internet |
| Service Crashed | Red | Solid | Critical service down |
| Hardware Error | Red | Fast blink | I2C/NFC/audio failure |
| Booting | White | Pulse | System starting up |

**Health Check Logic:**
```
┌─────────────────────────────────────────────────┐
│           Health Monitor (every 5s)             │
├─────────────────────────────────────────────────┤
│  1. Check internet    → ping 8.8.8.8            │
│  2. Check server      → GET localhost:5000/health│
│  3. Check hardware    → GET /debug/speaker/status│
├─────────────────────────────────────────────────┤
│  All 3 OK     → GREEN solid                     │
│  2 of 3       → YELLOW solid                    │
│  HW only      → CYAN solid                      │
│  Server only  → MAGENTA solid                   │
│  None         → RED solid                       │
│  No internet  → YELLOW blink                    │
└─────────────────────────────────────────────────┘
```

---

### Light 2: Player State LED (Main Controller)

**Controlled by Main** via `ui/lights.py`

| State | Color | Pattern | Trigger |
|-------|-------|---------|---------|
| Idle / Standby | Off | - | No activity |
| Chip Scanned | Blue | Quick flash (200ms) | NFC read success |
| Chip Unknown | Yellow | Double flash | NFC read but chip not in DB |
| Loading Track | Cyan | Pulse | Fetching from Mopidy |
| Playing | Green | Solid | Playback active |
| Paused | Yellow | Solid | Playback paused |
| Stopped | Off | - | Playback stopped |
| Recording Countdown | Red | Blink (sync with beeps) | 3-2-1 countdown |
| Recording Active | Red | Solid | Recording in progress |
| Recording Saved | Green | Flash (500ms) | Recording saved successfully |
| Volume Change | White | Brief flash (100ms) | Volume adjusted |
| Blocked (Parental) | Magenta | Double flash | Quiet hours / blocked chip |
| Blocked (Volume Cap) | Magenta | Single flash | Volume limit hit |
| Playback Error | Red | Triple flash | Mopidy error |
| Chip Error | Red | Quick flash | Failed to read/write chip |

---

### Future: Light 3 - PTT Voice Mode

| State | Color | Pattern |
|-------|-------|---------|
| PTT Idle | Off | - |
| Listening | Blue | Pulse |
| Processing | Cyan | Fast pulse |
| Command Recognized | Green | Flash |
| Command Failed | Red | Flash |
| No Match | Yellow | Flash |

---

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PCF8574 @ 0x21                       │
├─────────────────────────┬───────────────────────────────┤
│   Light 1 (P0-P2)       │   Light 2 (P3-P5)             │
│   DEVICE HEALTH         │   PLAYER STATE                │
├─────────────────────────┼───────────────────────────────┤
│   health_monitor.py     │   Main (controller.py)        │
│   (separate service)    │   via ui/lights.py            │
└─────────────────────────┴───────────────────────────────┘
```

**3 Services:**
1. `smart_speaker_server.service` - API server (always running)
2. `smart_speaker.service` - Hardware controller (Main) → controls Light 2
3. `smart_speaker_health.service` - Health monitor → controls Light 1 (NEW)

---

### Implementation Files

**New files:**
- `Main/health_monitor.py` - Health service controlling Light 1
- `services/smart_speaker_health.service` - Systemd unit for health monitor

**Modified files:**
- `Main/hardware/leds.py` - Low-level PCF8574 control (shared library)
- `Main/ui/lights.py` - Player state LED methods (Light 2 only)
- `Main/core/controller.py` - Hook LED calls into state transitions

---

### Code: Shared LED Hardware Layer

```python
# Main/hardware/leds.py - Shared low-level control
from smbus2 import SMBus
import threading
import time

I2C_ADDRESS = 0x21
LIGHT1_PINS = (0, 1, 2)  # Health (R, G, B)
LIGHT2_PINS = (3, 4, 5)  # Player (R, G, B)

class Colors:
    OFF =     (False, False, False)
    RED =     (True,  False, False)
    GREEN =   (False, True,  False)
    BLUE =    (False, False, True)
    YELLOW =  (True,  True,  False)
    CYAN =    (False, True,  True)
    MAGENTA = (True,  False, True)
    WHITE =   (True,  True,  True)

class RGBLeds:
    """Control RGB LEDs via PCF8574 - each service controls its own LED"""
    
    def __init__(self):
        self.bus = SMBus(1)
        # Read current state to preserve other LED
        try:
            self._state = self.bus.read_byte(I2C_ADDRESS)
        except:
            self._state = 0x00
    
    def set_light(self, light_num: int, color: tuple):
        """Set LED 1 or 2 to a color tuple (r, g, b)"""
        pins = LIGHT1_PINS if light_num == 1 else LIGHT2_PINS
        for pin, on in zip(pins, color):
            if on:
                self._state |= (1 << pin)
            else:
                self._state &= ~(1 << pin)
        self.bus.write_byte(I2C_ADDRESS, self._state)
    
    def off(self, light_num: int):
        """Turn off specific LED"""
        self.set_light(light_num, Colors.OFF)
```

---

### Code: Player State LED (Main)

```python
# Main/ui/lights.py - Player LED only (Light 2)
import threading
import time
from hardware.leds import RGBLeds, Colors

class PlayerLights:
    """Player state LED (Light 2) - used by Main controller"""
    
    LIGHT_NUM = 2  # Player uses Light 2
    
    def __init__(self):
        self.leds = RGBLeds()
        self._pattern_thread = None
        self._stop_pattern = threading.Event()
    
    def _stop_current_pattern(self):
        """Stop any running pattern"""
        self._stop_pattern.set()
        if self._pattern_thread and self._pattern_thread.is_alive():
            self._pattern_thread.join(timeout=0.5)
        self._stop_pattern.clear()
    
    # === Solid states ===
    def idle(self):
        self._stop_current_pattern()
        self.leds.off(self.LIGHT_NUM)
    
    def playing(self):
        self._stop_current_pattern()
        self.leds.set_light(self.LIGHT_NUM, Colors.GREEN)
    
    def paused(self):
        self._stop_current_pattern()
        self.leds.set_light(self.LIGHT_NUM, Colors.YELLOW)
    
    def recording(self):
        self._stop_current_pattern()
        self.leds.set_light(self.LIGHT_NUM, Colors.RED)
    
    # === Flash patterns ===
    def chip_scanned(self):
        """Blue flash on NFC scan"""
        self._flash(Colors.BLUE, duration=0.2)
    
    def chip_unknown(self):
        """Yellow double flash for unknown chip"""
        self._double_flash(Colors.YELLOW)
    
    def blocked(self):
        """Magenta double flash for parental block"""
        self._double_flash(Colors.MAGENTA)
    
    def volume_changed(self):
        """Brief white flash on volume change"""
        self._flash(Colors.WHITE, duration=0.1)
    
    def success(self):
        """Green flash for success"""
        self._flash(Colors.GREEN, duration=0.5)
    
    def error(self):
        """Red triple flash for error"""
        self._triple_flash(Colors.RED)
    
    # === Pattern helpers ===
    def _flash(self, color, duration=0.2):
        def do_flash():
            self.leds.set_light(self.LIGHT_NUM, color)
            time.sleep(duration)
            self.leds.off(self.LIGHT_NUM)
        threading.Thread(target=do_flash, daemon=True).start()
    
    def _double_flash(self, color):
        def do_double():
            for _ in range(2):
                self.leds.set_light(self.LIGHT_NUM, color)
                time.sleep(0.15)
                self.leds.off(self.LIGHT_NUM)
                time.sleep(0.1)
        threading.Thread(target=do_double, daemon=True).start()
    
    def _triple_flash(self, color):
        def do_triple():
            for _ in range(3):
                self.leds.set_light(self.LIGHT_NUM, color)
                time.sleep(0.1)
                self.leds.off(self.LIGHT_NUM)
                time.sleep(0.1)
        threading.Thread(target=do_triple, daemon=True).start()
    
    def loading(self):
        """Cyan pulsing while loading"""
        self._stop_current_pattern()
        def do_pulse():
            while not self._stop_pattern.is_set():
                self.leds.set_light(self.LIGHT_NUM, Colors.CYAN)
                time.sleep(0.3)
                self.leds.off(self.LIGHT_NUM)
                time.sleep(0.3)
        self._pattern_thread = threading.Thread(target=do_pulse, daemon=True)
        self._pattern_thread.start()
```

---

### Code: Health Monitor Service

```python
# Main/health_monitor.py - Separate service for Light 1
import time
import subprocess
import requests
from hardware.leds import RGBLeds, Colors

class HealthMonitor:
    """Monitor system health and control Light 1"""
    
    LIGHT_NUM = 1
    CHECK_INTERVAL = 5  # seconds
    
    def __init__(self):
        self.leds = RGBLeds()
        self.server_url = "http://localhost:5000"
        self._blink_thread = None
        self._stop_blink = threading.Event()
    
    def check_internet(self) -> bool:
        """Ping Google DNS"""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', '8.8.8.8'],
                capture_output=True, timeout=3
            )
            return result.returncode == 0
        except:
            return False
    
    def check_server(self) -> bool:
        """Check if API server is responding"""
        try:
            r = requests.get(f"{self.server_url}/health", timeout=2)
            return r.status_code == 200
        except:
            return False
    
    def check_hardware(self) -> bool:
        """Check if hardware controller is running"""
        try:
            r = requests.get(f"{self.server_url}/debug/speaker/status", timeout=2)
            data = r.json()
            return data.get("status") == "running"
        except:
            return False
    
    def _set_solid(self, color):
        self._stop_blink.set()
        self.leds.set_light(self.LIGHT_NUM, color)
    
    def _set_blink(self, color, interval=0.5):
        self._stop_blink.set()
        time.sleep(0.1)
        self._stop_blink.clear()
        
        def do_blink():
            while not self._stop_blink.is_set():
                self.leds.set_light(self.LIGHT_NUM, color)
                time.sleep(interval)
                self.leds.off(self.LIGHT_NUM)
                time.sleep(interval)
        
        self._blink_thread = threading.Thread(target=do_blink, daemon=True)
        self._blink_thread.start()
    
    def update_led(self):
        internet = self.check_internet()
        server = self.check_server()
        hardware = self.check_hardware()
        
        if internet and server and hardware:
            self._set_solid(Colors.GREEN)       # All systems go
        elif server and hardware and not internet:
            self._set_blink(Colors.YELLOW)      # No internet
        elif hardware and not server:
            self._set_solid(Colors.CYAN)        # Hardware only
        elif server and not hardware:
            self._set_solid(Colors.MAGENTA)     # Server only
        elif not internet and not server and not hardware:
            self._set_solid(Colors.RED)         # Critical - all down
        else:
            self._set_solid(Colors.YELLOW)      # Partial
    
    def run(self):
        """Main loop"""
        # Boot animation
        self._set_blink(Colors.WHITE, interval=0.3)
        time.sleep(3)
        
        while True:
            try:
                self.update_led()
            except Exception as e:
                self._set_solid(Colors.RED)
            time.sleep(self.CHECK_INTERVAL)

if __name__ == "__main__":
    monitor = HealthMonitor()
    monitor.run()
```

---

### Integration in Controller

```python
# Main/core/controller.py - Add LED hooks
from ui.lights import PlayerLights

class Controller:
    def __init__(self, ...):
        # ... existing init ...
        self.lights = PlayerLights()
    
    def _on_state_change(self, new_state):
        # Update LED based on state
        if new_state == State.IDLE:
            self.lights.idle()
        elif new_state == State.PLAYING:
            self.lights.playing()
        elif new_state == State.PAUSED:
            self.lights.paused()
        elif new_state == State.RECORDING:
            self.lights.recording()
    
    def _on_chip_scanned(self, chip_id):
        self.lights.chip_scanned()
    
    def _on_blocked(self, reason):
        self.lights.blocked()
```

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
