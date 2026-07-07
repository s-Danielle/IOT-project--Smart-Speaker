"""
Shared WiFi Management Module

This module provides a unified WiFiManager class for WiFi operations
used by both the main server and the wifi_provisioner service.
"""

import html
import os
import subprocess
import time

from hardware import captive_responder
from utils.logger import log


# Shared constant for AP mode SSID
AP_SSID = "SmartSpeaker-Setup"
AP_IP = "192.168.4.1"
WEB_PORT = 8080

# Repo-root SECRETS file (shell-style KEY="value" lines, see SECRETS.template)
_SECRETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'SECRETS'
)


def _get_secret(key: str) -> str:
    """Read a single value from the SECRETS file. Returns '' if missing."""
    try:
        with open(_SECRETS_PATH, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                if k.strip() == key:
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                        v = v[1:-1]
                    return v
    except OSError:
        pass
    return ''


def split_terse_line(line: str) -> list[str]:
    """Split one line of `nmcli -t` output on unescaped colons.

    nmcli terse mode escapes literal ':' as '\\:' and '\\' as '\\\\';
    this unescapes both while splitting.
    """
    fields = []
    current = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and i + 1 < len(line):
            current.append(line[i + 1])
            i += 2
        elif ch == ':':
            fields.append(''.join(current))
            current = []
            i += 1
        else:
            current.append(ch)
            i += 1
    fields.append(''.join(current))
    return fields


_wifi_interface = None


def get_wifi_interface() -> str:
    """Detect the WiFi interface name via nmcli (cached, falls back to wlan0)."""
    global _wifi_interface
    if _wifi_interface is None:
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'DEVICE,TYPE', 'device'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    parts = split_terse_line(line)
                    if len(parts) >= 2 and parts[1] == 'wifi' and parts[0]:
                        _wifi_interface = parts[0]
                        break
        except Exception:
            pass
        if not _wifi_interface:
            _wifi_interface = 'wlan0'
    return _wifi_interface


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
        """Get current IP address on the WiFi interface"""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'IP4.ADDRESS', 'device', 'show', get_wifi_interface()],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'IP4.ADDRESS' in line:
                    parts = split_terse_line(line)
                    return parts[1].split('/')[0] if len(parts) > 1 and parts[1] else None
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
                parts = split_terse_line(line)
                if parts and parts[0] == '*':
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
        # --rescan yes triggers a fresh scan and blocks until results are ready
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY',
             'device', 'wifi', 'list', '--rescan', 'yes'],
            capture_output=True, text=True
        )
        
        networks = []
        seen = set()
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = split_terse_line(line)
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
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE',
             'device', 'wifi', 'list', '--rescan', 'yes'],
            capture_output=True, text=True
        )
        
        networks = []
        seen = set()
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = split_terse_line(line)
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
            parts = split_terse_line(line)
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                connections.append({
                    "name": parts[0],
                    "autoconnect": parts[2] == 'yes' if len(parts) > 2 else True,
                    "priority": int(parts[3]) if len(parts) > 3 and parts[3] else 0
                })
        
        return connections
    
    @staticmethod
    def get_setup_url() -> str:
        """Get the WiFi setup URL for QR code generation."""
        return f"http://{AP_IP}:{WEB_PORT}/wifi-setup"
    
    @staticmethod
    def start_ap() -> bool:
        """Start AP mode using NetworkManager. Returns True on success."""
        # Check if hotspot exists
        existing = subprocess.run(
            ['nmcli', 'connection', 'show', AP_SSID],
            capture_output=True
        )
        
        if existing.returncode != 0:
            # Create hotspot
            cmd = [
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'con-name', AP_SSID,
                'autoconnect', 'no',
                'wifi.mode', 'ap',
                'wifi.ssid', AP_SSID,
                'ipv4.method', 'shared',
                'ipv4.addresses', f'{AP_IP}/24'
            ]
            ap_password = _get_secret('AP_PASSWORD')
            if ap_password:
                if len(ap_password) >= 8:
                    cmd += ['wifi-sec.key-mgmt', 'wpa-psk',
                            'wifi-sec.psk', ap_password]
                else:
                    log("AP_PASSWORD is shorter than 8 chars (WPA2 minimum); "
                        "starting open AP instead", "WARN")
            subprocess.run(cmd)
        
        # Disconnect current WiFi and start AP
        subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', get_wifi_interface()], 
                      check=False, capture_output=True)
        time.sleep(1)
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', AP_SSID], 
                               capture_output=True)
        time.sleep(2)
        
        if result.returncode == 0:
            # Answer OS captive-portal probes on port 80 so devices show
            # the "sign in to network" sheet. Never fatal for AP mode.
            try:
                captive_responder.start(WiFiManager.get_setup_url())
            except Exception as e:
                log(f"Captive responder failed to start: {e}", "WARN")
        
        return result.returncode == 0
    
    @staticmethod
    def stop_ap() -> bool:
        """Stop AP mode. Returns True on success."""
        try:
            captive_responder.stop()
        except Exception as e:
            log(f"Captive responder failed to stop: {e}", "WARN")
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
            if result.returncode == 0:
                return WiFiManager._wait_for_connection()
            return False
        
        # New connection - password optional (open networks)
        cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid]
        if password:
            cmd += ['password', password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and WiFiManager._wait_for_connection():
            return True
        
        # A failed `nmcli device wifi connect` can leave a broken profile
        # behind; clean it up since it wasn't previously saved.
        subprocess.run(
            ['sudo', 'nmcli', 'connection', 'delete', ssid],
            check=False, capture_output=True
        )
        return False
    
    @staticmethod
    def _wait_for_connection(timeout: int = 10) -> bool:
        """Poll until connected to a real network, up to `timeout` seconds."""
        for _ in range(timeout):
            time.sleep(1)
            if WiFiManager.is_connected():
                return True
        return False
    
    @staticmethod
    def disconnect() -> bool:
        """Disconnect from current WiFi (but keep saved). Returns True on success."""
        result = subprocess.run(
            ['sudo', 'nmcli', 'device', 'disconnect', get_wifi_interface()],
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
            ['sudo', 'nmcli', 'device', 'connect', get_wifi_interface()],
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
                    <input type="password" name="password" id="password-input"
                           placeholder="WiFi Password" required>
                    <button type="submit">Connect</button>
                </form>
                <button class="back" onclick="showNetworks()">← Back</button>
            </div>
        </div>
    </div>
    <script>
        function selectNetwork(ssid, isOpen) {{
            document.getElementById('networks').classList.add('hidden');
            document.getElementById('password-form').classList.remove('hidden');
            document.getElementById('selected-ssid').textContent = ssid;
            document.getElementById('ssid-input').value = ssid;
            var pw = document.getElementById('password-input');
            pw.value = '';
            pw.required = !isOpen;
            pw.placeholder = isOpen ? 'No password (open network)' : 'WiFi Password';
        }}
        function showNetworks() {{
            document.getElementById('networks').classList.remove('hidden');
            document.getElementById('password-form').classList.add('hidden');
        }}
        document.getElementById('networks').addEventListener('click', function(e) {{
            var el = e.target.closest('.network');
            if (el && el.dataset.ssid !== undefined) {{
                selectNetwork(el.dataset.ssid, el.dataset.open === '1');
            }}
        }});
    </script>
</body>
</html>'''


def _is_open_network(network: dict) -> bool:
    """True if a scan result represents an open (passwordless) network."""
    security = (network.get('security') or '').strip()
    return security in ('', '--', 'Open')


def render_network_list_html(networks: list[dict], connect_action: str = "/connect") -> str:
    """Render the network list HTML content.
    
    SSIDs are attacker-controlled (anyone can broadcast any SSID), so they
    are HTML-escaped and passed to JS via data attributes rather than
    inline handlers.
    """
    content = '<h3>Select Network</h3>'
    for n in networks:
        bars = '▂▄▆█'[:max(1, n['signal']//25)]
        is_open = _is_open_network(n)
        lock = '' if is_open else '🔒'
        ssid_escaped = html.escape(n["ssid"], quote=True)
        content += f'''<div class="network" data-ssid="{ssid_escaped}" data-open="{1 if is_open else 0}">
            <span>{ssid_escaped} {lock}</span>
            <span class="signal">{bars} {n["signal"]}%</span>
        </div>'''
    
    if not networks:
        content += '<p>No networks found. <a href="/" style="color:white">Refresh</a></p>'
    
    return CAPTIVE_PORTAL_HTML.format(content=content, connect_action=connect_action)
