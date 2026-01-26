"""
HTTP Server for Smart Speaker API
Runs in a separate thread to handle REST API requests

This is the SINGLE SOURCE OF TRUTH for chip and library data.
ChipStore reads from this same data file.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse
import json
import uuid
import os
import cgi
import threading
import subprocess
import time
from utils.logger import log, log_success
from hardware.wifi_manager import (
    WiFiManager, AP_SSID, AP_IP, WEB_PORT,
    render_network_list_html, render_status_html
)


# Thread-pool HTTP server limited to 2 workers (suitable for single-core RPi)
class ThreadPoolHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles requests in a thread pool."""
    
    def __init__(self, server_address, RequestHandlerClass, max_workers=2):
        super().__init__(server_address, RequestHandlerClass)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        log(f"Server configured with {max_workers} worker threads")
    
    def process_request(self, request, client_address):
        """Submit request to thread pool instead of creating unlimited threads."""
        self.executor.submit(self.process_request_thread, request, client_address)
    
    def server_close(self):
        """Shutdown thread pool when server closes."""
        super().server_close()
        self.executor.shutdown(wait=True)

# File paths - use Main directory for data storage
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, 'server_data.json')
OLD_TAGS_FILE = os.path.join(SCRIPT_DIR, 'config', 'tags.json')

# Unified local_files directory structure
LOCAL_FILES_DIR = os.path.join(SCRIPT_DIR, 'local_files')
UPLOADS_DIR = os.path.join(LOCAL_FILES_DIR, 'uploads')
RECORDINGS_DIR = os.path.join(LOCAL_FILES_DIR, 'recordings')

# Ensure directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Default data - chips now have uid field for NFC matching
DEFAULT_DATA = {
    "chips": [
        # uid will be set when chip is first scanned
        # song_id links to library, uri is resolved from library
    ],
    "library": [
        {"id": "song001", "name": "Surprise", "uri": "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"},
        {"id": "song002", "name": "Lights", "uri": "file:///home/iot-proj/lights.mp3"},
    ],
    "parental_controls": {
        "enabled": False,
        "volume_limit": 100,
        "quiet_hours": {
            "enabled": False,
            "start": "21:00",
            "end": "07:00"
        },
        "daily_limit_minutes": 0,
        "chip_blacklist": [],
        "chip_whitelist_mode": False,
        "chip_whitelist": []
    },
    "daily_usage": {
        # Tracks daily playback usage, resets each day
        # "date": "YYYY-MM-DD",
        # "seconds": 0
    }
}

# Thread-safe data access
_data_lock = threading.Lock()
_migration_done = False

def migrate_from_tags_json():
    """
    Migrate chips from old tags.json format to server_data.json.
    This preserves existing chips that were set up before the unification.
    """
    global _migration_done
    if _migration_done:
        return
    _migration_done = True
    
    if not os.path.exists(OLD_TAGS_FILE):
        return
    
    try:
        with open(OLD_TAGS_FILE, 'r') as f:
            old_tags = json.load(f)
    except Exception as e:
        log(f"Could not read old tags.json: {e}")
        return
    
    if not old_tags:
        return
    
    # Load or create server_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {'chips': [], 'library': []}
    
    if 'chips' not in data:
        data['chips'] = []
    if 'library' not in data:
        data['library'] = []
    
    # Get existing UIDs to avoid duplicates
    existing_uids = {chip.get('uid') for chip in data['chips'] if chip.get('uid')}
    
    migrated_count = 0
    for uid, tag_data in old_tags.items():
        if uid in existing_uids:
            continue  # Already migrated
        
        # Add song to library if it has a URI
        song_id = None
        uri = tag_data.get('uri', '')
        if uri:
            # Check if this URI already exists in library
            for song in data['library']:
                if song.get('uri') == uri:
                    song_id = song['id']
                    break
            
            # If not found, add to library
            if song_id is None:
                song_id = f"song{uuid.uuid4().hex[:6]}"
                data['library'].append({
                    'id': song_id,
                    'name': tag_data.get('name', 'Migrated Song'),
                    'uri': uri,
                })
        
        # Add chip
        chip_name = tag_data.get('name', f'Chip {len(data["chips"]) + 1}')
        data['chips'].append({
            'id': f'chip{uuid.uuid4().hex[:6]}',
            'uid': uid,
            'name': chip_name,
            'song_id': song_id,
            'song_name': chip_name if song_id else None,
        })
        migrated_count += 1
    
    if migrated_count > 0:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        log_success(f"Migrated {migrated_count} chips from tags.json to server_data.json")

def load_data():
    """Load data from JSON file, or create with defaults if not exists."""
    # Run migration on first load
    migrate_from_tags_json()
    
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                # Ensure chips and library keys exist
                if 'chips' not in data:
                    data['chips'] = []
                if 'library' not in data:
                    data['library'] = []
                # Ensure parental_controls key exists
                if 'parental_controls' not in data:
                    data['parental_controls'] = DEFAULT_DATA['parental_controls'].copy()
                return data
        else:
            save_data_unlocked(DEFAULT_DATA)
            return DEFAULT_DATA.copy()


def get_parental_controls() -> dict:
    """Get parental control settings."""
    data = load_data()
    return data.get('parental_controls', DEFAULT_DATA['parental_controls'].copy())


def update_parental_controls(settings: dict) -> dict:
    """Update parental control settings."""
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = DEFAULT_DATA.copy()
        
        if 'parental_controls' not in data:
            data['parental_controls'] = DEFAULT_DATA['parental_controls'].copy()
        
        # Update only provided fields
        pc = data['parental_controls']
        if 'enabled' in settings:
            pc['enabled'] = settings['enabled']
        if 'volume_limit' in settings:
            pc['volume_limit'] = max(0, min(100, settings['volume_limit']))
        if 'quiet_hours' in settings:
            qh = settings['quiet_hours']
            if 'enabled' in qh:
                pc['quiet_hours']['enabled'] = qh['enabled']
            if 'start' in qh:
                pc['quiet_hours']['start'] = qh['start']
            if 'end' in qh:
                pc['quiet_hours']['end'] = qh['end']
        if 'daily_limit_minutes' in settings:
            pc['daily_limit_minutes'] = max(0, settings['daily_limit_minutes'])
        if 'chip_blacklist' in settings:
            pc['chip_blacklist'] = settings['chip_blacklist']
        if 'chip_whitelist_mode' in settings:
            pc['chip_whitelist_mode'] = settings['chip_whitelist_mode']
        if 'chip_whitelist' in settings:
            pc['chip_whitelist'] = settings['chip_whitelist']
        
        save_data_unlocked(data)
        log(f"Updated parental controls: {pc}")
        return pc

def save_data_unlocked(data):
    """Save data to JSON file (must be called with lock held)."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def save_data(data):
    """Save data to JSON file (thread-safe)."""
    with _data_lock:
        save_data_unlocked(data)


# =============================================================================
# DAILY USAGE TRACKING
# =============================================================================

def _get_today_str() -> str:
    """Get today's date as YYYY-MM-DD string."""
    from datetime import date
    return date.today().isoformat()


def get_daily_usage() -> dict:
    """Get today's usage data. Resets if date changed."""
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = DEFAULT_DATA.copy()
        
        usage = data.get('daily_usage', {})
        today = _get_today_str()
        
        # Reset if new day
        if usage.get('date') != today:
            usage = {'date': today, 'seconds': 0}
            data['daily_usage'] = usage
            save_data_unlocked(data)
        
        return usage


def add_daily_usage(seconds: int) -> dict:
    """Add seconds to today's usage. Returns updated usage."""
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = DEFAULT_DATA.copy()
        
        today = _get_today_str()
        usage = data.get('daily_usage', {})
        
        # Reset if new day
        if usage.get('date') != today:
            usage = {'date': today, 'seconds': 0}
        
        # Add usage
        usage['seconds'] = usage.get('seconds', 0) + max(0, int(seconds))
        data['daily_usage'] = usage
        save_data_unlocked(data)
        
        log(f"Daily usage updated: {usage['seconds']} seconds")
        return usage


def register_new_chip(uid: str, name: str = None) -> dict:
    """
    Register a new NFC chip that was scanned for the first time.
    Returns the new chip data.
    """
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = DEFAULT_DATA.copy()
        
        # Check if chip already exists
        for chip in data.get('chips', []):
            if chip.get('uid') == uid:
                return chip
        
        # Create new chip
        chip_num = len(data.get('chips', [])) + 1
        new_chip = {
            'id': f'chip{uuid.uuid4().hex[:6]}',
            'uid': uid,
            'name': name or f'Chip {chip_num}',
            'song_id': None,
            'song_name': None,
        }
        
        if 'chips' not in data:
            data['chips'] = []
        data['chips'].append(new_chip)
        save_data_unlocked(data)
        
        log(f"Registered new chip: {new_chip['name']} (UID: {uid[:20]}...)")
        return new_chip

def add_to_library(uri: str, name: str):
    """
    Add a file to the library (thread-safe).
    Used for both recordings and uploads.
    """
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = DEFAULT_DATA.copy()
        
        new_song = {
            "id": f"song{uuid.uuid4().hex[:6]}",
            "name": name,
            "uri": uri,
        }
        if 'library' not in data:
            data['library'] = []
        data['library'].append(new_song)
        save_data_unlocked(data)
        log(f"Added to library: {name} ({uri})")


# =============================================================================
# DEBUG / DEVELOPER TOOL FUNCTIONS
# =============================================================================

LOG_FILE = '/var/log/smart_speaker.log'
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # Parent of Main/


def debug_get_i2c_devices() -> dict:
    """Get list of I2C devices using i2cdetect."""
    try:
        result = subprocess.run(
            ['sudo', 'i2cdetect', '-y', '1'],
            capture_output=True, text=True, timeout=10
        )
        return {"output": result.stdout, "error": result.stderr if result.returncode != 0 else None}
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "Command timed out"}
    except Exception as e:
        return {"output": "", "error": str(e)}


def debug_get_system_info() -> dict:
    """Get system information: CPU temp, memory, disk, uptime."""
    info = {}
    
    # CPU Temperature
    try:
        result = subprocess.run(
            ['sudo', 'vcgencmd', 'measure_temp'],
            capture_output=True, text=True, timeout=5
        )
        info['temperature'] = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        info['temperature'] = "N/A"
    
    # Uptime
    try:
        result = subprocess.run(
            ['uptime', '-p'],
            capture_output=True, text=True, timeout=5
        )
        info['uptime'] = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        info['uptime'] = "N/A"
    
    # Memory usage
    try:
        result = subprocess.run(
            ['free', '-h'],
            capture_output=True, text=True, timeout=5
        )
        info['memory'] = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        info['memory'] = "N/A"
    
    # Disk usage
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True, text=True, timeout=5
        )
        info['disk'] = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        info['disk'] = "N/A"
    
    return info


def debug_get_logs(lines: int = 100) -> dict:
    """Get last N lines from log file."""
    try:
        if os.path.exists(LOG_FILE):
            result = subprocess.run(
                ['tail', f'-{lines}', LOG_FILE],
                capture_output=True, text=True, timeout=10
            )
            return {"logs": result.stdout.split('\n'), "error": None}
        else:
            return {"logs": [], "error": f"Log file not found: {LOG_FILE}"}
    except Exception as e:
        return {"logs": [], "error": str(e)}


def debug_get_git_status() -> dict:
    """Get git branch and status."""
    try:
        # Get current branch
        branch_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        
        # Get status
        status_result = subprocess.run(
            ['git', 'status', '--short'],
            cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=10
        )
        status = status_result.stdout.strip() if status_result.returncode == 0 else ""
        
        return {"branch": branch, "status": status, "error": None}
    except Exception as e:
        return {"branch": "unknown", "status": "", "error": str(e)}


def debug_git_pull() -> dict:
    """Pull latest code from git."""
    try:
        result = subprocess.run(
            ['git', 'pull'],
            cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=60
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "success": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "success": False}


def debug_speaker_status() -> dict:
    """Get the status of the smart_speaker hardware service."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'smart_speaker'],
            capture_output=True, text=True, timeout=10
        )
        status = result.stdout.strip()
        return {"status": status, "running": status == "active"}
    except Exception as e:
        return {"status": "error", "running": False, "error": str(e)}


def debug_speaker_start() -> dict:
    """Start the smart_speaker hardware service."""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'start', 'smart_speaker'],
            capture_output=True, text=True, timeout=30
        )
        return {"status": "started" if result.returncode == 0 else "error", "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def debug_speaker_stop() -> dict:
    """Stop the smart_speaker hardware service."""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'stop', 'smart_speaker'],
            capture_output=True, text=True, timeout=30
        )
        return {"status": "stopped" if result.returncode == 0 else "error", "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def debug_speaker_restart() -> dict:
    """Restart the smart_speaker hardware service."""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'smart_speaker'],
            capture_output=True, text=True, timeout=30
        )
        return {"status": "restarting" if result.returncode == 0 else "error", "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def debug_daemon_reload() -> dict:
    """Reload systemd daemon."""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'daemon-reload'],
            capture_output=True, text=True, timeout=30
        )
        return {"status": "reloaded" if result.returncode == 0 else "error", "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def debug_run_main() -> dict:
    """Run main.py with venv activated (in background)."""
    try:
        # Run in background using bash to source venv and run python
        venv_path = os.path.join(PROJECT_DIR, 'venv', 'bin', 'activate')
        main_path = os.path.join(SCRIPT_DIR, 'main.py')
        
        cmd = f'source {venv_path} && python {main_path}'
        subprocess.Popen(
            ['bash', '-c', cmd],
            cwd=PROJECT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return {"status": "started", "error": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def debug_reboot() -> dict:
    """Reboot the Raspberry Pi."""
    try:
        subprocess.Popen(['sudo', 'reboot'])
        return {"status": "rebooting"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============== WiFi Management Functions ==============
# These functions wrap the shared WiFiManager class for API responses

def wifi_get_status() -> dict:
    """Get current WiFi connection status."""
    try:
        return WiFiManager.get_status()
    except Exception as e:
        return {"error": str(e)}


def wifi_get_connections() -> dict:
    """List all saved WiFi connections."""
    try:
        return {"connections": WiFiManager.get_saved_connections()}
    except Exception as e:
        return {"error": str(e)}


def wifi_scan() -> dict:
    """Scan for available WiFi networks."""
    try:
        return {"networks": WiFiManager.scan_networks_extended()}
    except Exception as e:
        return {"error": str(e)}


def wifi_connect(ssid: str, password: str = None) -> dict:
    """Connect to a WiFi network (new or existing)."""
    try:
        if not ssid:
            return {"error": "SSID required"}
        
        if WiFiManager.connect(ssid, password):
            return {"status": "connected", "ssid": ssid}
        else:
            return {"error": "Connection failed"}
    except subprocess.TimeoutExpired:
        return {"error": "Connection timeout"}
    except Exception as e:
        return {"error": str(e)}


def wifi_disconnect() -> dict:
    """Disconnect from current WiFi (but keep saved)."""
    try:
        WiFiManager.disconnect()
        return {"status": "disconnected"}
    except Exception as e:
        return {"error": str(e)}


def wifi_forget(name: str) -> dict:
    """Delete a saved WiFi connection."""
    try:
        if not name:
            return {"error": "Connection name required"}
        
        if WiFiManager.forget(name):
            return {"status": "deleted", "name": name}
        else:
            return {"error": "Delete failed"}
    except Exception as e:
        return {"error": str(e)}


def wifi_set_priority(name: str, priority: int) -> dict:
    """Set connection priority (higher = preferred)."""
    try:
        if not name:
            return {"error": "Connection name required"}
        
        if WiFiManager.set_priority(name, priority):
            return {"status": "updated", "name": name, "priority": priority}
        else:
            return {"error": "Failed to update priority"}
    except Exception as e:
        return {"error": str(e)}


def wifi_ap_mode(enable: bool = True) -> dict:
    """Force AP mode for testing (creates hotspot)."""
    try:
        if enable:
            if WiFiManager.start_ap():
                return {
                    "status": "ap_mode_enabled",
                    "ssid": AP_SSID,
                    "ip": AP_IP,
                    "setup_url": f"http://{AP_IP}:{WEB_PORT}/wifi-setup",
                    "message": f"Connect to {AP_SSID} WiFi, then visit http://{AP_IP}:{WEB_PORT}/wifi-setup to configure"
                }
            else:
                return {"error": "Failed to start AP mode"}
        else:
            WiFiManager.stop_ap()
            WiFiManager.reconnect()
            return {"status": "ap_mode_disabled", "message": "Reconnecting to WiFi..."}
    except Exception as e:
        return {"error": str(e)}


class SpeakerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to use our logger instead of default logging"""
        log(f"HTTP {format % args}")
    
    def _send_json(self, response_data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())

    def _send_ok(self, status=200):
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        # Parse path to handle query strings
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')  # Normalize trailing slashes
        
        # Captive portal detection URLs - redirect to WiFi setup
        # Android, iOS, Windows, etc. use these to detect captive portals
        captive_portal_paths = [
            '/generate_204', '/gen_204', '/ncsi.txt',  # Android/Chrome
            '/canonical.html', '/success.txt',  # Various
        ]
        
        if path in captive_portal_paths or path == '':
            # Redirect to WiFi setup page
            self.send_response(302)
            self.send_header('Location', '/wifi-setup')
            self.end_headers()
            return
        
        if path == '/status':
            self._send_json({"connected": True})
        elif path == '/health':
            # Return hardware health status for all components
            from utils.hardware_health import HardwareHealthManager
            manager = HardwareHealthManager.get_instance()
            health_data = {
                name: {
                    "status": h.status.value,
                    "last_error": h.last_error,
                    "error_count": h.error_count
                }
                for name, h in manager.get_all_status().items()
            }
            self._send_json(health_data)
        elif path == '/chips':
            data = load_data()
            self._send_json(data.get('chips', []))
        elif path == '/library':
            data = load_data()
            self._send_json(data.get('library', []))
        elif path == '/settings/parental':
            self._send_json(get_parental_controls())
        elif self.path == '/usage/today':
            self._send_json(get_daily_usage())
        # Debug endpoints
        elif path == '/debug/i2c':
            self._send_json(debug_get_i2c_devices())
        elif path == '/debug/system':
            self._send_json(debug_get_system_info())
        elif path == '/debug/logs':
            self._send_json(debug_get_logs())
        elif path == '/debug/git-status':
            self._send_json(debug_get_git_status())
        elif path == '/debug/speaker/status':
            self._send_json(debug_speaker_status())
        # WiFi endpoints
        elif path == '/debug/wifi/status':
            self._send_json(wifi_get_status())
        elif path == '/debug/wifi/connections':
            self._send_json(wifi_get_connections())
        elif path == '/debug/wifi/scan':
            self._send_json(wifi_scan())
        # Captive portal WiFi setup page
        elif path == '/wifi-setup':
            self._serve_wifi_setup_page()
        else:
            self.send_error(404)
    
    def _serve_wifi_setup_page(self):
        """Serve the WiFi setup captive portal page"""
        try:
            networks = WiFiManager.scan_networks()
            html = render_network_list_html(networks, connect_action="/wifi-setup/connect")
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def do_PUT(self):
        if self.path == '/settings/parental':
            body = self._read_body()
            updated = update_parental_controls(body)
            self._send_json(updated)
            return
        
        if self.path.startswith('/chips/'):
            chip_id = self.path.split('/')[2]
            body = self._read_body()
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    self.send_error(404)
                    return
                
                for chip in data.get('chips', []):
                    if chip['id'] == chip_id:
                        if 'name' in body:
                            chip['name'] = body['name']
                        if 'song_id' in body:
                            chip['song_id'] = body['song_id']
                            # Find song name and URI from library
                            chip['song_name'] = None
                            for song in data.get('library', []):
                                if song['id'] == body['song_id']:
                                    chip['song_name'] = song['name']
                                    break
                        save_data_unlocked(data)
                        log(f"Updated chip {chip_id}: {chip}")
                        self._send_json(chip)
                        return
                
            self.send_error(404)
            
        elif self.path.startswith('/library/'):
            song_id = self.path.split('/')[2]
            body = self._read_body()
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    self.send_error(404)
                    return
                
                for song in data.get('library', []):
                    if song['id'] == song_id:
                        song['name'] = body.get('name', song['name'])
                        song['uri'] = body.get('uri', song['uri'])
                        save_data_unlocked(data)
                        log(f"Updated song {song_id}: {song}")
                        self._send_json(song)
                        return
                
            self.send_error(404)
        else:
            self.send_error(404)

    def do_DELETE(self):
        if '/chips/' in self.path and self.path.endswith('/assignment'):
            chip_id = self.path.split('/')[2]
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    self.send_error(404)
                    return
                
                for chip in data.get('chips', []):
                    if chip['id'] == chip_id:
                        chip['song_id'] = None
                        chip['song_name'] = None
                        save_data_unlocked(data)
                        log(f"Reset assignment for chip {chip_id}")
                        self._send_ok(204)
                        return
                
            self.send_error(404)
        
        elif self.path.startswith('/chips/'):
            # Delete a chip: DELETE /chips/{chip_id}
            chip_id = self.path.split('/')[2]
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    self.send_error(404)
                    return
                
                for i, chip in enumerate(data.get('chips', [])):
                    if chip['id'] == chip_id:
                        data['chips'].pop(i)
                        save_data_unlocked(data)
                        log(f"Deleted chip {chip_id}")
                        self._send_ok(204)
                        return
                
            self.send_error(404)
            
        elif self.path.startswith('/library/'):
            song_id = self.path.split('/')[2]
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    self.send_error(404)
                    return
                
                for i, song in enumerate(data.get('library', [])):
                    if song['id'] == song_id:
                        data['library'].pop(i)
                        # Cascade: clear song from any chips that reference it
                        for chip in data.get('chips', []):
                            if chip.get('song_id') == song_id:
                                chip['song_id'] = None
                                chip['song_name'] = None
                                log(f"Cleared song {song_id} from chip {chip['id']}")
                        save_data_unlocked(data)
                        log(f"Deleted song {song_id}")
                        self._send_ok(204)
                        return
                
            self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/chips':
            # Register a new chip: POST /chips {uid: "...", name: "..."}
            body = self._read_body()
            uid = body.get('uid')
            name = body.get('name')
            
            if not uid:
                self._send_json({"error": "uid is required"}, 400)
                return
            
            new_chip = register_new_chip(uid, name)
            self._send_json(new_chip, 201)
            
        elif self.path == '/library':
            body = self._read_body()
            new_song = {
                "id": f"song{uuid.uuid4().hex[:6]}",
                "name": body.get('name', ''),
                "uri": body.get('uri', ''),
            }
            
            with _data_lock:
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                else:
                    data = {'chips': [], 'library': []}
                
                data['library'].append(new_song)
                save_data_unlocked(data)
            
            log(f"Added song: {new_song}")
            self._send_json(new_song, 201)
        
        elif self.path == '/usage/add':
            body = self._read_body()
            seconds = body.get('seconds', 0)
            updated = add_daily_usage(seconds)
            self._send_json(updated)
            
        elif self.path == '/files':
            # Handle multipart file upload
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in content_type:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST',
                             'CONTENT_TYPE': content_type}
                )
                
                if 'file' in form:
                    file_item = form['file']
                    if file_item.filename:
                        # Generate unique filename
                        file_ext = os.path.splitext(file_item.filename)[1] or '.mp3'
                        file_id = uuid.uuid4().hex[:8]
                        filename = f"{file_id}{file_ext}"
                        filepath = os.path.join(UPLOADS_DIR, filename)
                        
                        # Save the file
                        with open(filepath, 'wb') as f:
                            f.write(file_item.file.read())
                        
                        uri = f"file://{filepath}"
                        # Extract original filename for display name
                        original_name = os.path.splitext(file_item.filename)[0]
                        display_name = f"[UPLOAD] {original_name}"
                        
                        # Add to library automatically
                        add_to_library(uri, display_name)
                        
                        log(f"Uploaded file: {filepath} (added to library as '{display_name}')")
                        self._send_json({"uri": uri, "name": display_name}, 201)
                        return
            
            # Fallback for non-multipart
            file_id = uuid.uuid4().hex[:8]
            uri = f"file://{UPLOADS_DIR}/{file_id}.mp3"
            display_name = f"[UPLOAD] {file_id}"
            add_to_library(uri, display_name)
            self._send_json({"uri": uri, "name": display_name}, 201)
        
        # Debug POST endpoints
        elif self.path == '/debug/git-pull':
            self._send_json(debug_git_pull())
        # Speaker service control (hardware controller)
        elif self.path == '/debug/speaker/start':
            self._send_json(debug_speaker_start())
        elif self.path == '/debug/speaker/stop':
            self._send_json(debug_speaker_stop())
        elif self.path == '/debug/speaker/restart':
            self._send_json(debug_speaker_restart())
        elif self.path == '/debug/daemon-reload':
            self._send_json(debug_daemon_reload())
        elif self.path == '/debug/run-main':
            self._send_json(debug_run_main())
        elif self.path == '/debug/reboot':
            self._send_json(debug_reboot())
        # WiFi POST endpoints
        elif self.path == '/debug/wifi/connect':
            body = self._read_body()
            self._send_json(wifi_connect(body.get('ssid'), body.get('password')))
        elif self.path == '/debug/wifi/disconnect':
            self._send_json(wifi_disconnect())
        elif self.path == '/debug/wifi/forget':
            body = self._read_body()
            self._send_json(wifi_forget(body.get('name')))
        elif self.path == '/debug/wifi/priority':
            body = self._read_body()
            self._send_json(wifi_set_priority(body.get('name'), body.get('priority', 0)))
        elif self.path == '/debug/wifi/ap-mode':
            body = self._read_body() or {}
            self._send_json(wifi_ap_mode(body.get('enable', True)))
        # Captive portal WiFi connect handler
        elif self.path == '/wifi-setup/connect' or self.path.startswith('/wifi-setup/connect?'):
            self._handle_wifi_setup_connect()
        else:
            self.send_error(404)
    
    def _handle_wifi_setup_connect(self):
        """Handle WiFi connection from captive portal form"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = parse_qs(self.rfile.read(length).decode())
            ssid = data.get('ssid', [''])[0]
            password = data.get('password', [''])[0]
            
            log(f"WiFi setup: attempting connection to {ssid}")
            success = WiFiManager.connect(ssid, password)
            
            html = render_status_html(success, ssid, connect_action="/wifi-setup/connect")
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
            if success:
                log_success(f"WiFi setup: connected to {ssid}")
                # Schedule a reboot after successful connection (like the provisioner does)
                threading.Timer(5, lambda: subprocess.run(['sudo', 'reboot'])).start()
            else:
                log(f"WiFi setup: failed to connect to {ssid}")
                # Re-enable AP mode so user can try again
                WiFiManager.start_ap()
        except Exception as e:
            log(f"WiFi setup error: {e}")
            self.send_error(500, str(e))


def run_server_blocking(port=8080, host='0.0.0.0'):
    """
    Run the HTTP server in the main thread (blocking).
    
    Use this for standalone server service mode where the server
    is the main process and should run until terminated.
    """
    server = ThreadPoolHTTPServer((host, port), SpeakerHandler, max_workers=2)
    log_success(f"HTTP Server started on http://{host}:{port}")
    log(f"  - Data file: {DATA_FILE}")
    log(f"  - Local files directory: {LOCAL_FILES_DIR}")
    log("Server running in standalone mode (blocking)...")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Server shutdown requested...")
    finally:
        server.server_close()
        log("Server stopped.")
