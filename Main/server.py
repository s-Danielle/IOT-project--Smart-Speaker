"""
HTTP Server for Smart Speaker API
Runs in a separate thread to handle REST API requests

This is the SINGLE SOURCE OF TRUTH for chip and library data.
ChipStore reads from this same data file.
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
        {"id": "song001", "name": "Morning Jazz", "uri": "spotify:track:abc123"},
        {"id": "song002", "name": "Lullaby", "uri": "file:///music/lullaby.mp3"},
    ]
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
                return data
        else:
            save_data_unlocked(DEFAULT_DATA)
            return DEFAULT_DATA.copy()

def save_data_unlocked(data):
    """Save data to JSON file (must be called with lock held)."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def save_data(data):
    """Save data to JSON file (thread-safe)."""
    with _data_lock:
        save_data_unlocked(data)

def get_song_uri_by_id(song_id: str) -> str:
    """Get song URI from library by song_id."""
    data = load_data()
    for song in data.get('library', []):
        if song['id'] == song_id:
            return song.get('uri', '')
    return ''

def lookup_chip_by_uid(uid: str) -> dict:
    """
    Look up chip data by NFC UID.
    Returns dict with uid, name, uri (resolved from library) or None if not found.
    This is called by ChipStore.
    """
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            return None
        
        for chip in data.get('chips', []):
            if chip.get('uid') == uid:
                # Found chip - resolve URI from library
                song_id = chip.get('song_id')
                uri = ''
                if song_id:
                    for song in data.get('library', []):
                        if song['id'] == song_id:
                            uri = song.get('uri', '')
                            break
                
                return {
                    'uid': uid,
                    'name': chip.get('name', 'Unknown'),
                    'uri': uri,
                    'song_id': song_id,
                    'song_name': chip.get('song_name', ''),
                }
        
        return None

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

def get_all_chip_uids() -> list:
    """Get all known chip UIDs."""
    data = load_data()
    return [chip.get('uid') for chip in data.get('chips', []) if chip.get('uid')]

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
        if self.path == '/status':
            self._send_json({"connected": True})
        elif self.path == '/chips':
            data = load_data()
            self._send_json(data.get('chips', []))
        elif self.path == '/library':
            data = load_data()
            self._send_json(data.get('library', []))
        else:
            self.send_error(404)

    def do_PUT(self):
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
                        save_data_unlocked(data)
                        log(f"Deleted song {song_id}")
                        self._send_ok(204)
                        return
                
            self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/library':
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
