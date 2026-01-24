# Smart Speaker - Fixes & Improvements

## Overview

| # | Fix/Improvement | Status |
|---|-----------------|--------|
| 1 | Recording Countdown Sync | DONE |
| 2 | Recording Time Limit | TODO |
| 3 | Debug Service | DONE |
| 4 | WiFi Config on Boot | DONE |
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

## 4. 📶 WiFi Provisioning System (2-3 hrs)

**What:** Manage WiFi connections via NetworkManager with AP fallback for first-time setup

**Why:** 
- Users shouldn't need SSH/keyboard to configure WiFi on a headless device
- Need to manage saved networks from the Flutter app
- Need a way to test AP mode without losing all connections

**Current Setup:** Using NetworkManager (nmtui/nmcli) - connections already configured

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     NORMAL OPERATION                            │
├─────────────────────────────────────────────────────────────────┤
│  NetworkManager handles auto-connect to known networks          │
│  Priority-based: connects to best available saved network       │
│  Health monitor shows green LED when connected                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AP MODE (Fallback)                          │
├─────────────────────────────────────────────────────────────────┤
│  Triggered when:                                                │
│    1. No known networks available on boot (auto)                │
│    2. User forces AP mode via app (testing)                     │
│                                                                 │
│  Creates "SmartSpeaker-Setup" hotspot                           │
│  Blue pulsing LED                                               │
│  Captive portal for WiFi config                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### API Endpoints for WiFi Management

Add these to `Main/server.py`:

```python
# ============== WiFi Management Endpoints ==============

@app.route('/debug/wifi/status', methods=['GET'])
def wifi_status():
    """Get current WiFi connection status"""
    # Get active connection
    active = subprocess.run(
        ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'],
        capture_output=True, text=True
    )
    
    # Get current SSID
    ssid_result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
    ssid = ssid_result.stdout.strip()
    
    # Get IP address
    ip_result = subprocess.run(
        ['nmcli', '-t', '-f', 'IP4.ADDRESS', 'device', 'show', 'wlan0'],
        capture_output=True, text=True
    )
    ip = None
    for line in ip_result.stdout.split('\n'):
        if 'IP4.ADDRESS' in line:
            ip = line.split(':')[1].split('/')[0] if ':' in line else None
            break
    
    # Get signal strength
    signal_result = subprocess.run(
        ['nmcli', '-t', '-f', 'IN-USE,SIGNAL,SSID', 'device', 'wifi', 'list'],
        capture_output=True, text=True
    )
    signal = None
    for line in signal_result.stdout.split('\n'):
        if line.startswith('*:'):
            parts = line.split(':')
            signal = int(parts[1]) if len(parts) > 1 else None
            break
    
    return jsonify({
        "connected": bool(ssid),
        "ssid": ssid or None,
        "ip": ip,
        "signal": signal,
        "mode": "ap" if ssid == "SmartSpeaker-Setup" else "client"
    })


@app.route('/debug/wifi/connections', methods=['GET'])
def wifi_connections():
    """List all saved WiFi connections"""
    result = subprocess.run(
        ['nmcli', '-t', '-f', 'NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY', 'connection', 'show'],
        capture_output=True, text=True
    )
    
    connections = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split(':')
        if len(parts) >= 2 and parts[1] == '802-11-wireless':
            connections.append({
                "name": parts[0],
                "autoconnect": parts[2] == 'yes' if len(parts) > 2 else True,
                "priority": int(parts[3]) if len(parts) > 3 and parts[3] else 0
            })
    
    return jsonify({"connections": connections})


@app.route('/debug/wifi/scan', methods=['GET'])
def wifi_scan():
    """Scan for available WiFi networks"""
    # Trigger a fresh scan
    subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], capture_output=True)
    time.sleep(2)
    
    result = subprocess.run(
        ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE', 'device', 'wifi', 'list'],
        capture_output=True, text=True
    )
    
    networks = []
    seen = set()
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split(':')
        ssid = parts[0] if parts else ''
        if ssid and ssid not in seen:
            seen.add(ssid)
            networks.append({
                "ssid": ssid,
                "signal": int(parts[1]) if len(parts) > 1 and parts[1] else 0,
                "security": parts[2] if len(parts) > 2 else "Open",
                "connected": parts[3] == '*' if len(parts) > 3 else False
            })
    
    # Sort by signal strength
    networks.sort(key=lambda x: x['signal'], reverse=True)
    return jsonify({"networks": networks})


@app.route('/debug/wifi/connect', methods=['POST'])
def wifi_connect():
    """Connect to a WiFi network (new or existing)"""
    data = request.get_json()
    ssid = data.get('ssid')
    password = data.get('password')  # Optional for saved networks
    
    if not ssid:
        return jsonify({"error": "SSID required"}), 400
    
    # Check if connection already exists
    existing = subprocess.run(
        ['nmcli', 'connection', 'show', ssid],
        capture_output=True, text=True
    )
    
    if existing.returncode == 0:
        # Existing connection - just activate it
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'up', ssid],
            capture_output=True, text=True, timeout=30
        )
    else:
        # New connection - need password
        if not password:
            return jsonify({"error": "Password required for new network"}), 400
        
        result = subprocess.run(
            ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True, timeout=30
        )
    
    if result.returncode == 0:
        return jsonify({"status": "connected", "ssid": ssid})
    else:
        return jsonify({"error": result.stderr or "Connection failed"}), 500


@app.route('/debug/wifi/disconnect', methods=['POST'])
def wifi_disconnect():
    """Disconnect from current WiFi (but keep saved)"""
    result = subprocess.run(
        ['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'],
        capture_output=True, text=True
    )
    return jsonify({"status": "disconnected"})


@app.route('/debug/wifi/forget', methods=['POST'])
def wifi_forget():
    """Delete a saved WiFi connection"""
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({"error": "Connection name required"}), 400
    
    result = subprocess.run(
        ['sudo', 'nmcli', 'connection', 'delete', name],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        return jsonify({"status": "deleted", "name": name})
    else:
        return jsonify({"error": result.stderr or "Delete failed"}), 500


@app.route('/debug/wifi/priority', methods=['POST'])
def wifi_set_priority():
    """Set connection priority (higher = preferred)"""
    data = request.get_json()
    name = data.get('name')
    priority = data.get('priority', 0)
    
    if not name:
        return jsonify({"error": "Connection name required"}), 400
    
    result = subprocess.run(
        ['sudo', 'nmcli', 'connection', 'modify', name, 
         'connection.autoconnect-priority', str(priority)],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        return jsonify({"status": "updated", "name": name, "priority": priority})
    else:
        return jsonify({"error": result.stderr}), 500


@app.route('/debug/wifi/ap-mode', methods=['POST'])
def wifi_ap_mode():
    """Force AP mode for testing (creates hotspot)"""
    data = request.get_json() or {}
    enable = data.get('enable', True)
    
    if enable:
        # Stop current connection
        subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'], check=False)
        
        # Create/start hotspot
        # Check if hotspot connection exists
        existing = subprocess.run(
            ['nmcli', 'connection', 'show', 'SmartSpeaker-Setup'],
            capture_output=True
        )
        
        if existing.returncode != 0:
            # Create hotspot connection
            subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'con-name', 'SmartSpeaker-Setup',
                'autoconnect', 'no',
                'wifi.mode', 'ap',
                'wifi.ssid', 'SmartSpeaker-Setup',
                'ipv4.method', 'shared',
                'ipv4.addresses', '192.168.4.1/24'
            ])
        
        # Activate hotspot
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'up', 'SmartSpeaker-Setup'],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            return jsonify({
                "status": "ap_mode_enabled",
                "ssid": "SmartSpeaker-Setup",
                "ip": "192.168.4.1",
                "message": "Connect to SmartSpeaker-Setup WiFi to configure"
            })
        else:
            return jsonify({"error": result.stderr}), 500
    else:
        # Disable AP mode, reconnect to normal WiFi
        subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'SmartSpeaker-Setup'], check=False)
        
        # Let NetworkManager auto-connect to best available
        subprocess.run(['sudo', 'nmcli', 'device', 'connect', 'wlan0'], check=False)
        
        return jsonify({"status": "ap_mode_disabled", "message": "Reconnecting to WiFi..."})
```

---

### Sudoers Configuration

```bash
# /etc/sudoers.d/smart_speaker - add these lines:
iot-proj ALL=(ALL) NOPASSWD: /usr/bin/nmcli
```

---

### WiFi Provisioner Service (Auto AP on Boot)

Only starts AP mode if no known networks connect after boot.

**File: `Main/wifi_provisioner.py`**

```python
#!/usr/bin/env python3
"""
WiFi Provisioning Service (NetworkManager-based)
- Waits for NetworkManager to connect on boot
- If no connection after timeout, starts AP mode
- LED feedback via Light 1
"""
import os
import sys
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

AP_SSID = "SmartSpeaker-Setup"
WEB_PORT = 80
CONNECT_TIMEOUT = 30  # Seconds to wait for auto-connect

class LEDController:
    """Simplified LED control for provisioning"""
    LIGHT = 1
    
    def __init__(self):
        try:
            from hardware.leds import RGBLeds, Colors
            self.leds = RGBLeds()
            self.Colors = Colors
            self._enabled = True
        except:
            self._enabled = False
        self._pulsing = False
    
    def ap_mode(self):
        if self._enabled:
            self._pulse(self.Colors.BLUE)
    
    def connecting(self):
        if self._enabled:
            self._pulse(self.Colors.YELLOW)
    
    def connected(self):
        if self._enabled:
            self.stop_pulse()
            self.leds.set_light(self.LIGHT, self.Colors.GREEN)
    
    def failed(self):
        if self._enabled:
            self.stop_pulse()
            for _ in range(3):
                self.leds.set_light(self.LIGHT, self.Colors.RED)
                time.sleep(0.2)
                self.leds.off(self.LIGHT)
                time.sleep(0.2)
    
    def _pulse(self, color):
        self.stop_pulse()
        self._pulsing = True
        def do_pulse():
            while self._pulsing:
                self.leds.set_light(self.LIGHT, color)
                time.sleep(0.5)
                self.leds.off(self.LIGHT)
                time.sleep(0.5)
        threading.Thread(target=do_pulse, daemon=True).start()
    
    def stop_pulse(self):
        self._pulsing = False
        time.sleep(0.1)


class WiFiManager:
    """NetworkManager-based WiFi management"""
    
    @staticmethod
    def is_connected():
        """Check if connected to WiFi (not AP mode)"""
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        ssid = result.stdout.strip()
        return bool(ssid) and ssid != AP_SSID
    
    @staticmethod
    def get_current_ssid():
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        return result.stdout.strip()
    
    @staticmethod
    def scan_networks():
        """Scan for available networks using nmcli"""
        subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], capture_output=True)
        time.sleep(2)
        
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list'],
            capture_output=True, text=True
        )
        
        networks = []
        seen = set()
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(':')
            ssid = parts[0]
            if ssid and ssid not in seen and ssid != AP_SSID:
                seen.add(ssid)
                networks.append({
                    "ssid": ssid,
                    "signal": int(parts[1]) if len(parts) > 1 and parts[1] else 0,
                    "security": parts[2] if len(parts) > 2 else ""
                })
        
        networks.sort(key=lambda x: x['signal'], reverse=True)
        return networks
    
    @staticmethod
    def start_ap():
        """Start AP mode using NetworkManager"""
        # Check if hotspot exists
        existing = subprocess.run(
            ['nmcli', 'connection', 'show', AP_SSID],
            capture_output=True
        )
        
        if existing.returncode != 0:
            # Create hotspot
            subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'con-name', AP_SSID,
                'autoconnect', 'no',
                'wifi.mode', 'ap',
                'wifi.ssid', AP_SSID,
                'ipv4.method', 'shared',
                'ipv4.addresses', '192.168.4.1/24'
            ])
        
        # Disconnect current and start AP
        subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'], check=False)
        time.sleep(1)
        subprocess.run(['sudo', 'nmcli', 'connection', 'up', AP_SSID])
        time.sleep(2)
    
    @staticmethod
    def stop_ap():
        """Stop AP mode"""
        subprocess.run(['sudo', 'nmcli', 'connection', 'down', AP_SSID], check=False)
    
    @staticmethod
    def connect(ssid, password):
        """Connect to a network"""
        WiFiManager.stop_ap()
        time.sleep(1)
        
        # Try connecting
        result = subprocess.run(
            ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            # Wait for connection
            for _ in range(10):
                time.sleep(1)
                if WiFiManager.is_connected():
                    return True
        return False


class CaptivePortalHandler(BaseHTTPRequestHandler):
    """HTTP handler for captive portal"""
    
    HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>SmartSpeaker WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; font-family: -apple-system, sans-serif; }}
        body {{ margin: 0; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e); 
               min-height: 100vh; color: white; }}
        .container {{ max-width: 400px; margin: 0 auto; }}
        h1 {{ text-align: center; }}
        h1 span {{ font-size: 48px; display: block; }}
        .card {{ background: rgba(255,255,255,0.1); border-radius: 16px; padding: 24px; }}
        .network {{ display: flex; justify-content: space-between; align-items: center;
                   padding: 12px; margin: 8px 0; background: rgba(255,255,255,0.1); 
                   border-radius: 8px; cursor: pointer; }}
        .network:hover {{ background: rgba(255,255,255,0.2); }}
        .signal {{ font-size: 12px; opacity: 0.7; }}
        input {{ width: 100%; padding: 14px; border: none; border-radius: 8px; 
                font-size: 16px; margin: 16px 0; }}
        button {{ width: 100%; padding: 16px; background: #4CAF50; color: white; 
                border: none; border-radius: 8px; font-size: 18px; cursor: pointer; }}
        button:hover {{ background: #45a049; }}
        .hidden {{ display: none; }}
        .status {{ text-align: center; padding: 20px; }}
        .error {{ color: #ff6b6b; }}
        .success {{ color: #69db7c; }}
        .back {{ background: transparent; border: 1px solid rgba(255,255,255,0.3); 
                color: white; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1><span>🔊</span>SmartSpeaker Setup</h1>
        <div class="card">
            <div id="networks">{content}</div>
            <div id="password-form" class="hidden">
                <h3 id="selected-ssid"></h3>
                <form method="POST" action="/connect">
                    <input type="hidden" name="ssid" id="ssid-input">
                    <input type="password" name="password" placeholder="WiFi Password" required>
                    <button type="submit">Connect</button>
                </form>
                <button class="back" onclick="showNetworks()">← Back</button>
            </div>
        </div>
    </div>
    <script>
        function selectNetwork(ssid) {{
            document.getElementById('networks').classList.add('hidden');
            document.getElementById('password-form').classList.remove('hidden');
            document.getElementById('selected-ssid').textContent = ssid;
            document.getElementById('ssid-input').value = ssid;
        }}
        function showNetworks() {{
            document.getElementById('networks').classList.remove('hidden');
            document.getElementById('password-form').classList.add('hidden');
        }}
    </script>
</body>
</html>'''
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        networks = WiFiManager.scan_networks()
        content = '<h3>Select Network</h3>'
        for n in networks:
            bars = '▂▄▆█'[:max(1, n['signal']//25)]
            lock = '🔒' if n['security'] else ''
            content += f'''<div class="network" onclick="selectNetwork('{n["ssid"]}')">
                <span>{n["ssid"]} {lock}</span>
                <span class="signal">{bars} {n["signal"]}%</span>
            </div>'''
        
        if not networks:
            content += '<p>No networks found. <a href="/" style="color:white">Refresh</a></p>'
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(self.HTML.format(content=content).encode())
    
    def do_POST(self):
        length = int(self.headers['Content-Length'])
        data = parse_qs(self.rfile.read(length).decode())
        ssid = data.get('ssid', [''])[0]
        password = data.get('password', [''])[0]
        
        if self.server.led:
            self.server.led.connecting()
        
        success = WiFiManager.connect(ssid, password)
        
        if success:
            if self.server.led:
                self.server.led.connected()
            content = f'''<div class="status success">
                <h2>✅ Connected!</h2>
                <p>Connected to <strong>{ssid}</strong></p>
                <p>Restarting in 5 seconds...</p>
            </div>'''
            threading.Timer(5, lambda: subprocess.run(['sudo', 'reboot'])).start()
        else:
            if self.server.led:
                self.server.led.failed()
                time.sleep(1)
                self.server.led.ap_mode()
            WiFiManager.start_ap()
            content = f'''<div class="status error">
                <h2>❌ Failed</h2>
                <p>Could not connect to <strong>{ssid}</strong></p>
                <p>Check password and try again.</p>
                <button onclick="location.href='/'">Try Again</button>
            </div>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(self.HTML.format(content=content).encode())


class WiFiProvisioner:
    def __init__(self):
        self.led = LEDController()
    
    def run(self):
        print("[WiFi] Waiting for NetworkManager to connect...")
        self.led.connecting()
        
        # Give NetworkManager time to auto-connect
        for i in range(CONNECT_TIMEOUT):
            if WiFiManager.is_connected():
                ssid = WiFiManager.get_current_ssid()
                print(f"[WiFi] Connected to {ssid}")
                self.led.connected()
                return  # Exit - normal operation
            time.sleep(1)
            if i % 5 == 0:
                print(f"[WiFi] Waiting... ({CONNECT_TIMEOUT - i}s remaining)")
        
        print("[WiFi] No connection, starting AP mode...")
        self.led.ap_mode()
        WiFiManager.start_ap()
        
        server = HTTPServer(('0.0.0.0', WEB_PORT), CaptivePortalHandler)
        server.led = self.led
        print(f"[WiFi] Captive portal at http://192.168.4.1")
        server.serve_forever()


if __name__ == '__main__':
    WiFiProvisioner().run()
```

---

### Service File

**File: `services/smart_speaker_wifi.service`**

```ini
[Unit]
Description=Smart Speaker WiFi Provisioner
After=NetworkManager.service
Before=smart_speaker_server.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/iot-proj/IOT-project--Smart-Speaker/Main
ExecStart=/usr/bin/python3 wifi_provisioner.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

### Installation

**Quick Install (recommended):**
```bash
cd services
sudo ./install-wifi-provisioner.sh
```

**Manual Installation:**
```bash
# 1. Ensure NetworkManager is installed (usually is on Pi OS)
sudo apt install network-manager

# 2. Add sudoers permission
echo "iot-proj ALL=(ALL) NOPASSWD: /usr/bin/nmcli" | sudo tee /etc/sudoers.d/smart_speaker_wifi

# 3. Install service
sudo cp services/smart_speaker_wifi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smart_speaker_wifi

# 4. Test AP mode manually
sudo nmcli device wifi hotspot ssid SmartSpeaker-Setup password ""
```

**Files Created:**
- `Main/wifi_provisioner.py` - Main provisioning service
- `services/smart_speaker_wifi.service` - Systemd unit file
- `services/install-wifi-provisioner.sh` - Installation script
- Server endpoints added to `Main/server.py`
- Flutter UI added to Developer Tools screen

---

### LED Feedback Summary

| State | Light 1 Color | Pattern |
|-------|---------------|---------|
| Waiting for auto-connect | Yellow | Pulsing |
| AP Mode (setup) | Blue | Pulsing |
| Connected | Green | Solid |
| Connection failed | Red | Triple flash |

---

### Testing Checklist

- [ ] Auto-connects to known networks on boot
- [ ] Falls back to AP mode if no networks available
- [ ] `GET /debug/wifi/status` returns current connection
- [ ] `GET /debug/wifi/connections` lists saved networks
- [ ] `GET /debug/wifi/scan` shows available networks
- [ ] `POST /debug/wifi/connect` connects to network
- [ ] `POST /debug/wifi/forget` removes saved network
- [ ] `POST /debug/wifi/ap-mode` forces AP mode for testing
- [ ] `POST /debug/wifi/ap-mode {"enable": false}` exits AP mode
- [ ] Captive portal shows on phone when connecting to AP
- [ ] LED states match connection status

---

### Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/wifi/status` | GET | Current connection info |
| `/debug/wifi/connections` | GET | List saved networks |
| `/debug/wifi/scan` | GET | Scan available networks |
| `/debug/wifi/connect` | POST | Connect to network |
| `/debug/wifi/disconnect` | POST | Disconnect (keep saved) |
| `/debug/wifi/forget` | POST | Delete saved network |
| `/debug/wifi/priority` | POST | Set network priority |
| `/debug/wifi/ap-mode` | POST | Force/exit AP mode |

| Task | Time |
|------|------|
| Add server endpoints | 30 min |
| Create wifi_provisioner.py | 45 min |
| Create systemd service | 10 min |
| Test & debug | 30 min |
| **Total** | **~2 hrs**

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
| 5 | WiFi Config | DONE | ⭐⭐⭐⭐ |
| 6 | Stale Chip Data Fix | DONE | Bug fix |
| 7 | LED Feedback | TODO | ⭐⭐⭐⭐⭐ |
