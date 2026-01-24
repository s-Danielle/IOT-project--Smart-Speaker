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
  ├─ Yes → Start normally
  └─ No → Create hotspot "SmartSpeaker-Setup" 
          → User connects → Configures WiFi via web page
          → Reboot → Connect to configured WiFi
```

**Options:**
- Use `comitup` package (easy WiFi provisioning)
- Custom script with `hostapd`

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

## Priority Order

| # | Item | Time | Value |
|---|------|------|-------|
| 1 | Recording Sync Fix | DONE | Bug fix |
| 2 | Recording Time Limit | 1 hr | ⭐⭐⭐ |
| 3 | Advanced App Settings | DONE | ⭐⭐⭐⭐⭐ |
| 4 | Debug Service | DONE | ⭐⭐⭐⭐ |
| 5 | WiFi Config | TODO | ⭐⭐⭐ |
| 6 | Stale Chip Data Fix | DONE | Bug fix |
