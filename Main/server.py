"""
HTTP Server for Smart Speaker API
Runs in a separate thread to handle REST API requests
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import uuid
import os
import cgi
import threading
from utils.logger import log, log_success

# File paths - use Main directory for data storage
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, 'server_data.json')

# Unified local_files directory structure
LOCAL_FILES_DIR = os.path.join(SCRIPT_DIR, 'local_files')
UPLOADS_DIR = os.path.join(LOCAL_FILES_DIR, 'uploads')
RECORDINGS_DIR = os.path.join(LOCAL_FILES_DIR, 'recordings')

# Ensure directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Default data
DEFAULT_DATA = {
    "chips": [
        {"id": "chip001", "name": "Blue Tag", "song_id": "song001", "song_name": "Morning Jazz"},
        {"id": "chip002", "name": "Red Tag", "song_id": None, "song_name": None},
        {"id": "chip003", "name": "Green Tag", "song_id": "song002", "song_name": "Lullaby"},
    ],
    "library": [
        {"id": "song001", "name": "Morning Jazz", "uri": "spotify:track:abc123"},
        {"id": "song002", "name": "Lullaby", "uri": "file:///music/lullaby.mp3"},
    ]
}

# Thread-safe data access
_data_lock = threading.Lock()

def load_data():
    """Load data from JSON file, or create with defaults if not exists."""
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        else:
            save_data(DEFAULT_DATA)
            return DEFAULT_DATA.copy()

def save_data(data):
    """Save data to JSON file."""
    with _data_lock:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)

def add_to_library(uri: str, name: str):
    """
    Add a file to the library (thread-safe).
    Used for both recordings and uploads.
    """
    global data
    with _data_lock:
        data = load_data()
        new_song = {
            "id": f"song{uuid.uuid4().hex[:6]}",
            "name": name,
            "uri": uri,
        }
        data['library'].append(new_song)
        save_data(data)
        log(f"Added to library: {name} ({uri})")

def add_recording_to_library(filepath: str, display_name: str = None):
    """
    Add a recording to the library with [RECORDING] prefix.
    If display_name is not provided, extracts it from filename.
    """
    if not os.path.exists(filepath):
        log(f"Warning: Recording file not found: {filepath}")
        return
    
    # Generate display name if not provided
    if display_name is None:
        # Extract name from filename (remove extension and recording_ prefix)
        basename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(basename)[0]
        # Remove "recording_" prefix if present
        if name_without_ext.startswith("recording_"):
            name_without_ext = name_without_ext[10:]  # Remove "recording_" (10 chars)
        display_name = f"[RECORDING] {name_without_ext}"
    
    uri = f"file://{filepath}"
    add_to_library(uri, display_name)
    log(f"Recording added to library: {display_name}")

# Load initial data
data = load_data()

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
        global data
        if self.path == '/status':
            self._send_json({"connected": True, "chip_id": "chip001"})
        elif self.path == '/chips':
            data = load_data()
            self._send_json(data['chips'])
        elif self.path == '/library':
            data = load_data()
            self._send_json(data['library'])
        else:
            self.send_error(404)

    def do_PUT(self):
        global data
        data = load_data()
        if self.path.startswith('/chips/'):
            chip_id = self.path.split('/')[2]
            body = self._read_body()
            for chip in data['chips']:
                if chip['id'] == chip_id:
                    if 'name' in body:
                        chip['name'] = body['name']
                    if 'song_id' in body:
                        chip['song_id'] = body['song_id']
                        # Find song name
                        for song in data['library']:
                            if song['id'] == body['song_id']:
                                chip['song_name'] = song['name']
                                break
                    save_data(data)
                    log(f"Updated chip {chip_id}: {chip}")
                    self._send_json(chip)
                    return
            self.send_error(404)
        elif self.path.startswith('/library/'):
            song_id = self.path.split('/')[2]
            body = self._read_body()
            for song in data['library']:
                if song['id'] == song_id:
                    song['name'] = body.get('name', song['name'])
                    song['uri'] = body.get('uri', song['uri'])
                    save_data(data)
                    log(f"Updated song {song_id}: {song}")
                    self._send_json(song)
                    return
            self.send_error(404)
        else:
            self.send_error(404)

    def do_DELETE(self):
        global data
        data = load_data()
        if '/chips/' in self.path and self.path.endswith('/assignment'):
            chip_id = self.path.split('/')[2]
            for chip in data['chips']:
                if chip['id'] == chip_id:
                    chip['song_id'] = None
                    chip['song_name'] = None
                    save_data(data)
                    log(f"Reset assignment for chip {chip_id}")
                    self._send_ok(204)
                    return
            self.send_error(404)
        elif self.path.startswith('/library/'):
            song_id = self.path.split('/')[2]
            for i, song in enumerate(data['library']):
                if song['id'] == song_id:
                    data['library'].pop(i)
                    save_data(data)
                    log(f"Deleted song {song_id}")
                    self._send_ok(204)
                    return
            self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        global data
        data = load_data()
        if self.path == '/library':
            body = self._read_body()
            new_song = {
                "id": f"song{uuid.uuid4().hex[:6]}",
                "name": body.get('name', ''),
                "uri": body.get('uri', ''),
            }
            data['library'].append(new_song)
            save_data(data)
            log(f"Added song: {new_song}")
            self._send_json(new_song, 201)
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
        else:
            self.send_error(404)


class ServerThread(threading.Thread):
    """Thread wrapper for the HTTP server"""
    
    def __init__(self, port=8080, host='0.0.0.0'):
        super().__init__(daemon=True)  # Daemon thread so it exits when main exits
        self.port = port
        self.host = host
        self.server = None
        
    def run(self):
        """Start the HTTP server in this thread"""
        try:
            self.server = HTTPServer((self.host, self.port), SpeakerHandler)
            log_success(f"HTTP Server started on http://{self.host}:{self.port}")
            log(f"  - Data file: {DATA_FILE}")
            log(f"  - Local files directory: {LOCAL_FILES_DIR}")
            log(f"  - Uploads: {UPLOADS_DIR}")
            log(f"  - Recordings: {RECORDINGS_DIR}")
            log(f"  - iOS Simulator: http://localhost:{self.port}")
            log(f"  - Android Emulator: http://10.0.2.2:{self.port}")
            log(f"  - Physical device (same WiFi): http://<your-ip>:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            log(f"Server error: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """Stop the server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def start_server(port=8080, host='0.0.0.0'):
    """
    Start the HTTP server in a background thread.
    Returns the ServerThread instance.
    """
    server_thread = ServerThread(port=port, host=host)
    server_thread.start()
    return server_thread
