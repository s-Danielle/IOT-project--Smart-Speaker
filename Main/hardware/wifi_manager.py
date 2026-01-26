"""
Shared WiFi Management Module

This module provides a unified WiFiManager class for WiFi operations
used by both the main server and the wifi_provisioner service.
"""

import subprocess
import time


# Shared constant for AP mode SSID
AP_SSID = "SmartSpeaker-Setup"
AP_IP = "192.168.4.1"
WEB_PORT = 8080


class WiFiManager:
    """NetworkManager-based WiFi management"""
    
    @staticmethod
    def is_connected() -> bool:
        """Check if connected to WiFi (not AP mode)"""
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        ssid = result.stdout.strip()
        return bool(ssid) and ssid != AP_SSID
    
    @staticmethod
    def get_current_ssid() -> str:
        """Get current connected SSID"""
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        return result.stdout.strip()
    
    @staticmethod
    def get_ip_address() -> str | None:
        """Get current IP address on wlan0"""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'IP4.ADDRESS', 'device', 'show', 'wlan0'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'IP4.ADDRESS' in line:
                    return line.split(':')[1].split('/')[0] if ':' in line else None
        except Exception:
            pass
        return None
    
    @staticmethod
    def get_signal_strength() -> int | None:
        """Get current signal strength (0-100)"""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'IN-USE,SIGNAL,SSID', 'device', 'wifi', 'list'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if line.startswith('*:'):
                    parts = line.split(':')
                    return int(parts[1]) if len(parts) > 1 and parts[1] else None
        except Exception:
            pass
        return None
    
    @staticmethod
    def get_status() -> dict:
        """Get full WiFi connection status"""
        ssid = WiFiManager.get_current_ssid()
        return {
            "connected": WiFiManager.is_connected(),
            "ssid": ssid or None,
            "ip": WiFiManager.get_ip_address(),
            "signal": WiFiManager.get_signal_strength(),
            "mode": "ap" if ssid == AP_SSID else "client"
        }
    
    @staticmethod
    def scan_networks() -> list[dict]:
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
    def scan_networks_extended() -> list[dict]:
        """Scan for networks with extended info (including connected status)"""
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
        
        networks.sort(key=lambda x: x['signal'], reverse=True)
        return networks
    
    @staticmethod
    def get_saved_connections() -> list[dict]:
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
        
        return connections
    
    # Path to dnsmasq captive portal config (for DNS wildcard redirect)
    DNSMASQ_CAPTIVE_CONF = '/etc/NetworkManager/dnsmasq-shared.d/captive-portal.conf'
    
    @staticmethod
    def _enable_captive_dns():
        """Enable DNS hijacking for captive portal detection.
        
        Creates a dnsmasq config that responds to ALL DNS queries with
        the AP's IP address, making phones detect a captive portal.
        """
        conf_content = f"address=/#/{AP_IP}\n"
        conf_dir = '/etc/NetworkManager/dnsmasq-shared.d'
        
        try:
            subprocess.run(['sudo', 'mkdir', '-p', conf_dir], check=False, capture_output=True)
            subprocess.run(
                ['sudo', 'tee', WiFiManager.DNSMASQ_CAPTIVE_CONF],
                input=conf_content.encode(),
                capture_output=True
            )
        except Exception:
            pass
    
    @staticmethod
    def _disable_captive_dns():
        """Disable DNS hijacking (restore normal DNS)."""
        try:
            subprocess.run(['sudo', 'rm', '-f', WiFiManager.DNSMASQ_CAPTIVE_CONF],
                          check=False, capture_output=True)
        except Exception:
            pass
    
    @staticmethod
    def start_ap() -> bool:
        """Start AP mode using NetworkManager. Returns True on success."""
        # Enable DNS hijacking BEFORE starting AP so dnsmasq picks it up
        WiFiManager._enable_captive_dns()
        
        # Delete existing hotspot connection to force fresh start with new DNS config
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', AP_SSID],
                      check=False, capture_output=True)
        
        # Create hotspot
        subprocess.run([
            'sudo', 'nmcli', 'connection', 'add',
            'type', 'wifi',
            'con-name', AP_SSID,
            'autoconnect', 'no',
            'wifi.mode', 'ap',
            'wifi.ssid', AP_SSID,
            'ipv4.method', 'shared',
            'ipv4.addresses', f'{AP_IP}/24'
        ])
        
        # Disconnect current WiFi and start AP
        subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'], 
                      check=False, capture_output=True)
        time.sleep(1)
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', AP_SSID], 
                               capture_output=True)
        time.sleep(2)
        
        return result.returncode == 0
    
    @staticmethod
    def stop_ap() -> bool:
        """Stop AP mode. Returns True on success."""
        # Disable DNS hijacking first
        WiFiManager._disable_captive_dns()
        
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'down', AP_SSID], 
                               check=False, capture_output=True)
        return result.returncode == 0
    
    @staticmethod
    def connect(ssid: str, password: str = None) -> bool:
        """Connect to a WiFi network. Returns True on success."""
        if not ssid:
            return False
        
        # Stop AP mode if active
        WiFiManager.stop_ap()
        time.sleep(1)
        
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
                return False
            
            result = subprocess.run(
                ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                capture_output=True, text=True, timeout=30
            )
        
        if result.returncode == 0:
            # Wait for connection to stabilize
            for _ in range(10):
                time.sleep(1)
                if WiFiManager.is_connected():
                    return True
        return False
    
    @staticmethod
    def disconnect() -> bool:
        """Disconnect from current WiFi (but keep saved). Returns True on success."""
        result = subprocess.run(
            ['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    
    @staticmethod
    def forget(name: str) -> bool:
        """Delete a saved WiFi connection. Returns True on success."""
        if not name:
            return False
        
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'delete', name],
            capture_output=True, text=True
        )
        return result.returncode == 0
    
    @staticmethod
    def set_priority(name: str, priority: int) -> bool:
        """Set connection priority (higher = preferred). Returns True on success."""
        if not name:
            return False
        
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'modify', name, 
             'connection.autoconnect-priority', str(priority)],
            capture_output=True, text=True
        )
        return result.returncode == 0
    
    @staticmethod
    def reconnect() -> bool:
        """Let NetworkManager auto-connect to best available network."""
        result = subprocess.run(
            ['sudo', 'nmcli', 'device', 'connect', 'wlan0'],
            capture_output=True, check=False
        )
        return result.returncode == 0


# Captive portal HTML template - shared between server and provisioner
CAPTIVE_PORTAL_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
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
                <form method="POST" action="{connect_action}">
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


def render_network_list_html(networks: list[dict], connect_action: str = "/connect") -> str:
    """Render the network list HTML content"""
    content = '<h3>Select Network</h3>'
    for n in networks:
        bars = '▂▄▆█'[:max(1, n['signal']//25)]
        lock = '🔒' if n.get('security') else ''
        content += f'''<div class="network" onclick="selectNetwork('{n["ssid"]}')">
            <span>{n["ssid"]} {lock}</span>
            <span class="signal">{bars} {n["signal"]}%</span>
        </div>'''
    
    if not networks:
        content += '<p>No networks found. <a href="/" style="color:white">Refresh</a></p>'
    
    return CAPTIVE_PORTAL_HTML.format(content=content, connect_action=connect_action)


def render_status_html(success: bool, ssid: str, connect_action: str = "/connect") -> str:
    """Render the connection status HTML content"""
    if success:
        content = f'''<div class="status success">
            <h2>✅ Connected!</h2>
            <p>Connected to <strong>{ssid}</strong></p>
            <p>Restarting in 5 seconds...</p>
        </div>'''
    else:
        content = f'''<div class="status error">
            <h2>❌ Failed</h2>
            <p>Could not connect to <strong>{ssid}</strong></p>
            <p>Check password and try again.</p>
            <button onclick="location.href='/'">Try Again</button>
        </div>'''
    
    return CAPTIVE_PORTAL_HTML.format(content=content, connect_action=connect_action)
