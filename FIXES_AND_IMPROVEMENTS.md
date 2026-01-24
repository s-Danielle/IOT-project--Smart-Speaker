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

## 7. 💡 LED Feedback System (1-2 hrs)

**What:** Visual feedback through 2 RGB LEDs

**Hardware:** PCF8574 I2C expander at 0x21
- **Light 1 (P0-P2):** Device Health - controlled by **health_monitor.py** (separate service)
- **Light 2 (P3-P5):** Player State - controlled by **Main** (already wired up!)

---

### Light 2: Player State (Main) - ZERO controller.py changes needed!

`ui_controller.py` **already calls** `self._lights.show_*()` methods. Just implement them in `lights.py`:

| Existing Method | Called When | Color | Pattern |
|-----------------|-------------|-------|---------|
| `show_idle()` | Chip cleared | Off | - |
| `show_chip_loaded()` | Chip scanned, stop, cancel recording | Blue | Flash (200ms) |
| `show_playing()` | Play/resume | Green | Solid |
| `show_paused()` | Pause | Yellow | Solid |
| `show_recording()` | Recording starts | Red | Solid |
| `show_success()` | Recording saved | Green | Flash (500ms) |
| `show_error()` | Error or blocked action | Red | Triple flash |
| `show_volume(v)` | Volume change | White | Brief flash |

**That's it!** The hooks are already in place. Just fill in the method bodies.

---

### Light 1: Device Health (Separate Service)

**Main ignores this LED** - run as separate `health_monitor.py` service.

| Condition | Color | Pattern |
|-----------|-------|---------|
| Internet ✓ Server ✓ Hardware ✓ | Green | Solid |
| Server + Hardware, no internet | Yellow | Blink |
| Hardware only | Cyan | Solid |
| Server only | Magenta | Solid |
| All down | Red | Solid |
| Booting | White | Blink |

---

### Implementation

**File 1: `Main/hardware/leds.py`** - Low-level PCF8574 control

```python
from smbus2 import SMBus

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
    def __init__(self):
        self.bus = SMBus(1)
        try:
            self._state = self.bus.read_byte(I2C_ADDRESS)
        except:
            self._state = 0x00
    
    def set_light(self, light_num: int, color: tuple):
        pins = LIGHT1_PINS if light_num == 1 else LIGHT2_PINS
        for pin, on in zip(pins, color):
            if on:
                self._state |= (1 << pin)
            else:
                self._state &= ~(1 << pin)
        self.bus.write_byte(I2C_ADDRESS, self._state)
    
    def off(self, light_num: int):
        self.set_light(light_num, Colors.OFF)
```

---

**File 2: `Main/ui/lights.py`** - Replace no-op methods with real implementation

```python
"""
Player LED feedback (Light 2) - implements existing show_* interface
"""
import threading
import time
from hardware.leds import RGBLeds, Colors

class Lights:
    """LED feedback - implements interface already called by UIController"""
    
    LIGHT = 2  # Player uses Light 2
    
    def __init__(self, leds=None):
        try:
            self.leds = leds or RGBLeds()
            self._enabled = True
        except:
            self._enabled = False
    
    def show_idle(self):
        """Chip cleared - LED off"""
        if self._enabled:
            self.leds.off(self.LIGHT)
    
    def show_chip_loaded(self):
        """Chip scanned - blue flash"""
        if self._enabled:
            self._flash(Colors.BLUE, 0.2)
    
    def show_playing(self):
        """Playing - green solid"""
        if self._enabled:
            self.leds.set_light(self.LIGHT, Colors.GREEN)
    
    def show_paused(self):
        """Paused - yellow solid"""
        if self._enabled:
            self.leds.set_light(self.LIGHT, Colors.YELLOW)
    
    def show_recording(self):
        """Recording - red solid"""
        if self._enabled:
            self.leds.set_light(self.LIGHT, Colors.RED)
    
    def show_error(self):
        """Error/blocked - red triple flash"""
        if self._enabled:
            self._flash(Colors.RED, 0.1, times=3)
    
    def show_success(self):
        """Success - green flash"""
        if self._enabled:
            self._flash(Colors.GREEN, 0.5)
    
    def show_volume(self, volume: int):
        """Volume change - white brief flash"""
        if self._enabled:
            self._flash(Colors.WHITE, 0.1)
    
    def off(self):
        if self._enabled:
            self.leds.off(self.LIGHT)
    
    def _flash(self, color, duration, times=1):
        def do_flash():
            for i in range(times):
                self.leds.set_light(self.LIGHT, color)
                time.sleep(duration)
                self.leds.off(self.LIGHT)
                if i < times - 1:
                    time.sleep(0.1)
        threading.Thread(target=do_flash, daemon=True).start()
```

---

**File 3: `Main/health_monitor.py`** - Separate service for Light 1

```python
#!/usr/bin/env python3
"""Health monitor service - controls Light 1"""
import time
import subprocess
import threading
import requests
from hardware.leds import RGBLeds, Colors

class HealthMonitor:
    LIGHT = 1
    
    def __init__(self):
        self.leds = RGBLeds()
        self._stop = threading.Event()
    
    def check_internet(self):
        try:
            r = subprocess.run(['ping', '-c', '1', '-W', '2', '8.8.8.8'],
                             capture_output=True, timeout=3)
            return r.returncode == 0
        except:
            return False
    
    def check_server(self):
        try:
            r = requests.get('http://localhost:5000/health', timeout=2)
            return r.status_code == 200
        except:
            return False
    
    def check_hardware(self):
        try:
            r = requests.get('http://localhost:5000/debug/speaker/status', timeout=2)
            return r.json().get('status') == 'running'
        except:
            return False
    
    def update(self):
        inet = self.check_internet()
        srv = self.check_server()
        hw = self.check_hardware()
        
        if inet and srv and hw:
            self.leds.set_light(self.LIGHT, Colors.GREEN)
        elif srv and hw:
            self.leds.set_light(self.LIGHT, Colors.YELLOW)  # No internet
        elif hw:
            self.leds.set_light(self.LIGHT, Colors.CYAN)    # HW only
        elif srv:
            self.leds.set_light(self.LIGHT, Colors.MAGENTA) # Server only
        else:
            self.leds.set_light(self.LIGHT, Colors.RED)     # All down
    
    def run(self):
        # Boot: white blink
        for _ in range(3):
            self.leds.set_light(self.LIGHT, Colors.WHITE)
            time.sleep(0.3)
            self.leds.off(self.LIGHT)
            time.sleep(0.3)
        
        while not self._stop.is_set():
            self.update()
            time.sleep(5)

if __name__ == '__main__':
    HealthMonitor().run()
```

---

**File 4: `services/smart_speaker_health.service`**

```ini
[Unit]
Description=Smart Speaker Health Monitor
After=network.target smart_speaker_server.service

[Service]
Type=simple
User=iot-proj
WorkingDirectory=/home/iot-proj/IOT-project--Smart-Speaker/Main
ExecStart=/usr/bin/python3 health_monitor.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

### Summary

| Task | Effort |
|------|--------|
| Implement `hardware/leds.py` | 15 min |
| Replace `ui/lights.py` | 15 min |
| Create `health_monitor.py` | 30 min |
| Create systemd service | 5 min |
| **Total** | **~1 hour** |

**No changes to controller.py needed** - UIController already calls the light methods!

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
