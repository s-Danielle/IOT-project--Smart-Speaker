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
    """Simplified LED control for provisioning - uses Light 1"""
    LIGHT = 1
    
    def __init__(self):
        try:
            from hardware.leds import RGBLeds, Colors
            self.leds = RGBLeds()
            self.Colors = Colors
            self._enabled = True
        except Exception:
            self._enabled = False
        self._pulsing = False
    
    def ap_mode(self):
        """AP mode - blue pulsing"""
        if self._enabled:
            self._pulse(self.Colors.BLUE)
    
    def connecting(self):
        """Waiting for connection - yellow pulsing"""
        if self._enabled:
            self._pulse(self.Colors.YELLOW)
    
    def connected(self):
        """Connected - solid green"""
        if self._enabled:
            self.stop_pulse()
            self.leds.set_light(self.LIGHT, self.Colors.GREEN)
    
    def failed(self):
        """Connection failed - red triple flash"""
        if self._enabled:
            self.stop_pulse()
            for _ in range(3):
                self.leds.set_light(self.LIGHT, self.Colors.RED)
                time.sleep(0.2)
                self.leds.off(self.LIGHT)
                time.sleep(0.2)
    
    def _pulse(self, color):
        """Start pulsing LED with given color"""
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
        """Stop pulsing"""
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
        """Get current connected SSID"""
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
        subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'], check=False, capture_output=True)
        time.sleep(1)
        subprocess.run(['sudo', 'nmcli', 'connection', 'up', AP_SSID], capture_output=True)
        time.sleep(2)
    
    @staticmethod
    def stop_ap():
        """Stop AP mode"""
        subprocess.run(['sudo', 'nmcli', 'connection', 'down', AP_SSID], check=False, capture_output=True)
    
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
        """Suppress default logging"""
        pass
    
    def do_GET(self):
        """Handle GET requests - show network list"""
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
        """Handle POST requests - connect to network"""
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
    """Main WiFi provisioning orchestrator"""
    
    def __init__(self):
        self.led = LEDController()
    
    def run(self):
        """Main provisioning flow - wait for WiFi, fallback to AP mode"""
        print("[WiFi] Waiting for NetworkManager to connect...")
        self.led.connecting()
        
        # Give NetworkManager time to auto-connect to known networks
        for i in range(CONNECT_TIMEOUT):
            if WiFiManager.is_connected():
                ssid = WiFiManager.get_current_ssid()
                print(f"[WiFi] Connected to {ssid}")
                self.led.connected()
                return  # Exit - normal operation can proceed
            time.sleep(1)
            if i % 5 == 0:
                print(f"[WiFi] Waiting... ({CONNECT_TIMEOUT - i}s remaining)")
        
        # No connection after timeout - start AP mode
        print("[WiFi] No connection, starting AP mode...")
        self.led.ap_mode()
        WiFiManager.start_ap()
        
        # Start captive portal
        server = HTTPServer(('0.0.0.0', WEB_PORT), CaptivePortalHandler)
        server.led = self.led
        print(f"[WiFi] Captive portal running at http://192.168.4.1")
        print(f"[WiFi] Connect to '{AP_SSID}' WiFi to configure")
        server.serve_forever()


if __name__ == '__main__':
    WiFiProvisioner().run()
