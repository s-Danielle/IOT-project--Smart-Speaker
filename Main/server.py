"""
HTTP Server for Smart Speaker API
Runs in a separate thread to handle REST API requests

This is the SINGLE SOURCE OF TRUTH for chip and library data.
ChipStore reads from this same data file.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse, unquote
import json
import mimetypes
import uuid
import os
from email.parser import BytesParser
from email.policy import default as email_policy
import threading
import subprocess
import time
from utils.logger import log, log_success
from utils.shared_dirs import ensure_shared_dir
from storage import JsonStore
from hardware.wifi_manager import (
    WiFiManager, AP_SSID, AP_IP, WEB_PORT,
    render_network_list_html, CAPTIVE_PORTAL_HTML
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

# Built Flutter web app bundle (deployed via scripts/deploy_web.sh)
WEB_APP_DIR = os.path.join(SCRIPT_DIR, 'web_app')

# Ensure directories exist
# The server runs as root. These folders must belong to the speaker's user (the owner of this
# program's folder): the controller's arecord writes recordings into them, Mopidy reads them.
ensure_shared_dir(LOCAL_FILES_DIR, SCRIPT_DIR)
ensure_shared_dir(UPLOADS_DIR, SCRIPT_DIR)
ensure_shared_dir(RECORDINGS_DIR, SCRIPT_DIR)
os.makedirs(WEB_APP_DIR, exist_ok=True)

# Some platforms guess these wrong (or not at all); Flutter web needs them
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('application/wasm', '.wasm')
mimetypes.add_type('application/json', '.json')

# Files that must never be cached so deploys take effect immediately
_NO_CACHE_FILES = {'index.html', 'flutter_bootstrap.js'}


def resolve_static_file(url_path: str, web_root: str):
    """Map a request path to a file inside web_root (path-traversal safe).

    Returns the absolute path of the file to serve, or None if nothing
    matches. Paths with no extension that don't exist fall back to
    index.html (SPA routing). Traversal attempts resolve to None.
    """
    rel = unquote(url_path).lstrip('/')
    if not rel:
        rel = 'index.html'

    root = os.path.realpath(web_root)
    candidate = os.path.realpath(os.path.join(root, rel))
    # Reject anything that resolves outside the web root
    if candidate != root and not candidate.startswith(root + os.sep):
        return None

    if os.path.isdir(candidate):
        candidate = os.path.join(candidate, 'index.html')
    if os.path.isfile(candidate):
        return candidate

    # SPA routing: extension-less virtual routes serve the app shell
    if not os.path.splitext(rel)[1]:
        index_path = os.path.join(root, 'index.html')
        if os.path.isfile(index_path):
            return index_path
    return None


# AP-mode check shells out (iwgetid/nmcli), so cache it briefly to avoid
# running it on every static asset request.
_AP_MODE_CACHE_TTL = 5.0
_ap_mode_lock = threading.Lock()
_ap_mode_cache = {"value": False, "checked_at": 0.0}


def is_ap_mode() -> bool:
    """True if the Pi is currently running the setup access point (cached ~5s)."""
    now = time.monotonic()
    with _ap_mode_lock:
        if now - _ap_mode_cache["checked_at"] < _AP_MODE_CACHE_TTL:
            return _ap_mode_cache["value"]
    try:
        value = WiFiManager.get_current_ssid() == AP_SSID
    except Exception:
        value = False
    with _ap_mode_lock:
        _ap_mode_cache["value"] = value
        _ap_mode_cache["checked_at"] = time.monotonic()
    return value

# =============================================================================
# DATA: chips, songs, parental controls, daily usage
# =============================================================================
# One store owns the data file and saves it safely (see storage/json_store.py).
# Everything below that reads or writes the data goes through it.
store = JsonStore(DATA_FILE)


def start_storage():
    """Open the data file when the server starts: create it, or repair it from its backup."""
    status = store.open()
    what_happened = {
        'ok': 'data file opened',
        'new': 'no data file yet, so one was created',
        'recovered': 'the data file was damaged or missing, so the last good copy was put back (a damaged file is kept next to it)',
        'damaged': 'the data file was damaged and there was no good copy, so it started empty (the damaged file was kept)',
    }
    log(f"[STORAGE] {what_happened[status]} ({store.kind}: {DATA_FILE})")
    if status == 'new':
        import_old_tags_file()


def import_old_tags_file():
    """First run only: bring in the chips from the old config/tags.json.

    This used to run at every start, which brought back chips that had been deleted in the app.
    """
    if not os.path.exists(OLD_TAGS_FILE):
        return
    try:
        with open(OLD_TAGS_FILE, 'r') as f:
            old_tags = json.load(f)
    except Exception as e:
        log(f"Could not read old tags.json: {e}")
        return
    added = store.import_legacy_tags(old_tags)
    if added:
        log_success(f"Migrated {added} chips from tags.json")


# =============================================================================
# DEBUG / DEVELOPER TOOL FUNCTIONS
# =============================================================================

LOG_FILE = '/var/log/smart_speaker/controller.log'
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

# Connection-attempt state, shared between the HTML captive portal and the
# JSON debug endpoints. Only one attempt may run at a time. The attempt runs
# in a background thread so HTTP responses return immediately (important:
# tearing down the AP kills the client's network mid-request otherwise).
_wifi_connect_lock = threading.Lock()
_wifi_connect_state = {
    "state": "idle",  # idle | connecting | connected | failed
    "ssid": None,
    "error": None,
    "timestamp": None,
}


def wifi_get_connect_status() -> dict:
    """Snapshot of the current/last connection attempt (thread-safe)."""
    with _wifi_connect_lock:
        return dict(_wifi_connect_state)


def _set_wifi_connect_state(state: str, ssid: str = None, error: str = None):
    with _wifi_connect_lock:
        _wifi_connect_state.update({
            "state": state,
            "ssid": ssid,
            "error": error,
            "timestamp": time.time(),
        })


def _wifi_connect_worker(ssid: str, password: str):
    """Background worker: tear down AP (if active), connect, restore AP on failure."""
    was_ap_active = WiFiManager.get_current_ssid() == AP_SSID
    success = False
    error = None
    try:
        # WiFiManager.connect() brings down the AP profile before connecting
        success = WiFiManager.connect(ssid, password)
        if not success:
            error = "Connection failed (check password and signal)"
    except subprocess.TimeoutExpired:
        error = "Connection timed out"
    except Exception as e:
        error = str(e)
    
    if success:
        _set_wifi_connect_state("connected", ssid)
        log_success(f"WiFi setup: connected to {ssid}")
    else:
        _set_wifi_connect_state("failed", ssid, error)
        log(f"WiFi setup: failed to connect to {ssid}: {error}")
        if was_ap_active:
            # Restore the setup AP so the user can try again
            try:
                WiFiManager.start_ap()
            except Exception as e:
                log(f"WiFi setup: failed to restore AP mode: {e}")


def start_wifi_connect(ssid: str, password: str = None) -> dict:
    """Start a background connection attempt. Returns immediately.
    
    Rejects the request if another attempt is already in progress.
    """
    if not ssid:
        return {"error": "SSID required"}
    
    with _wifi_connect_lock:
        if _wifi_connect_state["state"] == "connecting":
            return {
                "error": "Another connection attempt is in progress",
                "state": "connecting",
                "ssid": _wifi_connect_state["ssid"],
            }
        _wifi_connect_state.update({
            "state": "connecting",
            "ssid": ssid,
            "error": None,
            "timestamp": time.time(),
        })
    
    log(f"WiFi setup: attempting connection to {ssid}")
    threading.Thread(
        target=_wifi_connect_worker, args=(ssid, password), daemon=True
    ).start()
    return {"status": "connecting", "ssid": ssid}


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
    """Start connecting to a WiFi network (new or existing).
    
    Runs asynchronously: returns {"status": "connecting"} immediately.
    Poll GET /debug/wifi/connect-status for the outcome.
    """
    try:
        return start_wifi_connect(ssid, password)
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


def _render_connecting_html(ssid: str) -> str:
    """Render the captive-portal "connecting..." page.
    
    The page polls GET /debug/wifi/connect-status and updates itself with
    the outcome. If the speaker switches networks the AP disappears and
    polling starts failing; after enough failed polls the page assumes
    success and tells the user how to reach the speaker on their LAN.
    """
    # Embed the SSID as a JS string (escape "</" so it can't close the script tag)
    ssid_js = json.dumps(ssid).replace('</', '<\\/')
    content = f'''<div class="status" id="connect-status">
        <h2>⏳ Connecting...</h2>
        <p>Connecting to <strong id="connect-ssid"></strong>&hellip;</p>
        <p style="opacity:0.7">This can take up to a minute. The setup network
        may disappear while the speaker switches networks.</p>
    </div>
    <script>
        (function() {{
            var ssid = {ssid_js};
            document.getElementById('connect-ssid').textContent = ssid;
            var box = document.getElementById('connect-status');
            var missedPolls = 0;
            
            function show(title, lines, extraHtml) {{
                box.innerHTML = '';
                var h = document.createElement('h2');
                h.textContent = title;
                box.appendChild(h);
                lines.forEach(function(t) {{
                    var p = document.createElement('p');
                    p.textContent = t;
                    box.appendChild(p);
                }});
                if (extraHtml) {{
                    var d = document.createElement('div');
                    d.innerHTML = extraHtml;
                    box.appendChild(d);
                }}
            }}
            
            function showSuccess() {{
                box.className = 'status success';
                show('\\u2705 Connected!', [
                    'The speaker joined "' + ssid + '".',
                    'Reconnect this device to your normal WiFi, then reach the ' +
                    'speaker at http://rpi2.local:{WEB_PORT}'
                ]);
            }}
            
            function showFailure(error) {{
                box.className = 'status error';
                show('\\u274C Failed', [
                    'Could not connect to "' + ssid + '".',
                    error || 'Check the password and try again.'
                ], '<button onclick="location.href=\\'/wifi-setup\\'">Try Again</button>');
            }}
            
            function poll() {{
                fetch('/debug/wifi/connect-status')
                    .then(function(r) {{ return r.json(); }})
                    .then(function(s) {{
                        missedPolls = 0;
                        if (s.state === 'connected') {{
                            showSuccess();
                        }} else if (s.state === 'failed') {{
                            showFailure(s.error);
                        }} else {{
                            setTimeout(poll, 2000);
                        }}
                    }})
                    .catch(function() {{
                        // AP likely went down mid-switch; keep trying a while
                        missedPolls++;
                        if (missedPolls >= 15) {{
                            showSuccess();
                        }} else {{
                            setTimeout(poll, 2000);
                        }}
                    }});
            }}
            setTimeout(poll, 2000);
        }})();
    </script>'''
    return CAPTIVE_PORTAL_HTML.format(
        content=content, connect_action="/wifi-setup/connect"
    )


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

    def _parse_multipart_file(self, content_type, field_name='file'):
        """Extract a single uploaded file from a multipart/form-data body.

        Replaces the stdlib `cgi.FieldStorage` (removed in Python 3.13) with
        the `email` package, which parses MIME multipart messages the same
        way. Returns (filename, data) for the given field, or (None, None)
        if it isn't present.
        """
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''

        # email.parser expects headers followed by a blank line, then the body
        header_bytes = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode('utf-8')
        message = BytesParser(policy=email_policy).parsebytes(header_bytes + body)

        if not message.is_multipart():
            return None, None

        for part in message.iter_parts():
            if part.get_param('name', header='Content-Disposition') == field_name:
                return part.get_filename(), part.get_payload(decode=True)

        return None, None

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
            '/hotspot-detect.html', '/library/test/success.html',  # Apple
            '/connecttest.txt', '/redirect',  # Windows
            '/kindle-wifi/wifistub.html',  # Kindle
        ]
        
        # Only hijack these paths while the setup AP is active; on a normal
        # network '/' (and any unmatched path) serves the Flutter web app.
        if (path in captive_portal_paths or path == '') and is_ap_mode():
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
            self._send_json(store.chips())
        elif path == '/library':
            self._send_json(store.songs())
        elif path == '/settings/parental':
            self._send_json(store.parental_controls())
        elif self.path == '/usage/today':
            self._send_json(store.daily_usage())
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
        elif path == '/debug/wifi/connect-status':
            self._send_json(wifi_get_connect_status())
        # Captive portal WiFi setup page
        elif path == '/wifi-setup':
            self._serve_wifi_setup_page()
        else:
            # Anything else: try the deployed Flutter web app bundle
            self._serve_web_app(path)
    
    def _serve_web_app(self, path):
        """Serve a static file from the built Flutter web app (WEB_APP_DIR)."""
        filepath = resolve_static_file(path, WEB_APP_DIR)
        if filepath is None:
            if not os.path.isfile(os.path.join(WEB_APP_DIR, 'index.html')):
                body = (
                    "Web app not deployed.\n"
                    "Run scripts/deploy_web.sh from the development machine "
                    "to build and deploy the Flutter web app.\n"
                )
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body.encode('utf-8'))
            else:
                self.send_error(404)
            return
        
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
        except OSError:
            self.send_error(404)
            return
        
        content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
        if os.path.basename(filepath) in _NO_CACHE_FILES:
            cache_control = 'no-cache'
        else:
            cache_control = 'max-age=3600'
        
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', cache_control)
        self.end_headers()
        self.wfile.write(content)
    
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

    def _send_bad_request(self, problem):
        self._send_json({"error": str(problem)}, 400)

    def do_PUT(self):
        try:
            if self.path == '/settings/parental':
                self._send_json(store.update_parental_controls(self._read_body()))
            elif self.path.startswith('/chips/'):
                chip = store.update_chip(self.path.split('/')[2], self._read_body())
                if chip is None:
                    self.send_error(404)
                else:
                    self._send_json(chip)
            elif self.path.startswith('/library/'):
                song = store.update_song(self.path.split('/')[2], self._read_body())
                if song is None:
                    self.send_error(404)
                else:
                    self._send_json(song)
            else:
                self.send_error(404)
        except ValueError as problem:  # a value of the wrong kind, or a body that isn't JSON
            self._send_bad_request(problem)

    def do_DELETE(self):
        if '/chips/' in self.path and self.path.endswith('/assignment'):
            found = store.clear_chip_assignment(self.path.split('/')[2])
        elif self.path.startswith('/chips/'):
            # Delete a chip: DELETE /chips/{chip_id}
            found = store.delete_chip(self.path.split('/')[2])
        elif self.path.startswith('/library/'):
            # Chips that played this song are left with no song
            found = store.delete_song(self.path.split('/')[2])
        else:
            found = False
        if found:
            self._send_ok(204)
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
            
            try:
                new_chip = store.register_chip(uid, name)
            except ValueError as problem:
                self._send_bad_request(problem)
                return
            self._send_json(new_chip, 201)
            
        elif self.path == '/library':
            try:
                body = self._read_body()
                new_song = store.add_song(body.get('name', ''), body.get('uri', ''))
            except (ValueError, AttributeError) as problem:  # bad JSON, or a body that isn't an object
                self._send_bad_request(problem)
                return
            self._send_json(new_song, 201)
        
        elif self.path == '/usage/add':
            try:
                seconds = self._read_body().get('seconds', 0)
                self._send_json(store.add_daily_usage(seconds))
            except (ValueError, AttributeError) as problem:
                self._send_bad_request(problem)
            
        elif self.path == '/files':
            # Handle multipart file upload
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in content_type:
                upload_filename, file_data = self._parse_multipart_file(content_type)

                if upload_filename:
                    # Generate unique filename
                    file_ext = os.path.splitext(upload_filename)[1] or '.mp3'
                    file_id = uuid.uuid4().hex[:8]
                    filename = f"{file_id}{file_ext}"
                    filepath = os.path.join(UPLOADS_DIR, filename)

                    # Save the file
                    with open(filepath, 'wb') as f:
                        f.write(file_data or b'')

                    uri = f"file://{filepath}"
                    # Extract original filename for display name
                    original_name = os.path.splitext(upload_filename)[0]
                    display_name = f"[UPLOAD] {original_name}"

                    # Add to library automatically
                    store.add_song(display_name, uri)

                    log(f"Uploaded file: {filepath} (added to library as '{display_name}')")
                    self._send_json({"uri": uri, "name": display_name}, 201)
                    return
            
            # Fallback for non-multipart
            file_id = uuid.uuid4().hex[:8]
            uri = f"file://{UPLOADS_DIR}/{file_id}.mp3"
            display_name = f"[UPLOAD] {file_id}"
            store.add_song(display_name, uri)
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
        """Handle WiFi connection from captive portal form.
        
        Responds immediately with a "connecting..." page that polls
        /debug/wifi/connect-status; the actual connection attempt (AP
        teardown + nmcli connect) runs in a background thread.
        """
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = parse_qs(self.rfile.read(length).decode())
            ssid = data.get('ssid', [''])[0]
            password = data.get('password', [''])[0]
            
            result = start_wifi_connect(ssid, password)
            
            if result.get('error') and result.get('state') != 'connecting':
                # Bad request (e.g. missing SSID) - send back to the setup page
                self.send_response(302)
                self.send_header('Location', '/wifi-setup')
                self.end_headers()
                return
            
            # If another attempt is already in progress, the polling page
            # still shows its outcome, so serve it in that case too.
            shown_ssid = result.get('ssid') or ssid
            html = _render_connecting_html(shown_ssid)
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            log(f"WiFi setup error: {e}")
            self.send_error(500, str(e))


def run_server_blocking(port=8080, host='0.0.0.0'):
    """
    Run the HTTP server in the main thread (blocking).
    
    Use this for standalone server service mode where the server
    is the main process and should run until terminated.
    """
    start_storage()
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
