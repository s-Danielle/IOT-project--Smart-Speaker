from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import uuid
import os
import cgi

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, 'data.json')
UPLOADS_DIR = os.path.join(SCRIPT_DIR, 'uploads')

# Ensure uploads directory exists
os.makedirs(UPLOADS_DIR, exist_ok=True)

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

def load_data():
    """Load data from JSON file, or create with defaults if not exists."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    else:
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA.copy()

def save_data(data):
    """Save data to JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Load initial data
data = load_data()

class SpeakerHandler(BaseHTTPRequestHandler):
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
            self._send_json({"connected": True, "chip_id": "chip001"})
        elif self.path == '/chips':
            self._send_json(data['chips'])
        elif self.path == '/library':
            self._send_json(data['library'])
        else:
            self.send_error(404)

    def do_PUT(self):
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
                    print(f"Updated chip {chip_id}: {chip}")
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
                    print(f"Updated song {song_id}: {song}")
                    self._send_json(song)
                    return
            self.send_error(404)
        else:
            self.send_error(404)

    def do_DELETE(self):
        if '/chips/' in self.path and self.path.endswith('/assignment'):
            chip_id = self.path.split('/')[2]
            for chip in data['chips']:
                if chip['id'] == chip_id:
                    chip['song_id'] = None
                    chip['song_name'] = None
                    save_data(data)
                    print(f"Reset assignment for chip {chip_id}")
                    self._send_ok(204)
                    return
            self.send_error(404)
        elif self.path.startswith('/library/'):
            song_id = self.path.split('/')[2]
            for i, song in enumerate(data['library']):
                if song['id'] == song_id:
                    data['library'].pop(i)
                    save_data(data)
                    print(f"Deleted song {song_id}")
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
            data['library'].append(new_song)
            save_data(data)
            print(f"Added song: {new_song}")
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
                        print(f"Uploaded file: {filepath}")
                        self._send_json({"uri": uri}, 201)
                        return
            
            # Fallback for non-multipart
            file_id = uuid.uuid4().hex[:8]
            uri = f"file://{UPLOADS_DIR}/{file_id}.mp3"
            self._send_json({"uri": uri}, 201)
        else:
            self.send_error(404)

if __name__ == '__main__':
    port = 8080
    server = HTTPServer(('0.0.0.0', port), SpeakerHandler)
    print(f"Mock speaker server running on http://0.0.0.0:{port}")
    print(f"Data file: {DATA_FILE}")
    print(f"Uploads directory: {UPLOADS_DIR}")
    print(f"\nUse this URL in the app Settings:")
    print(f"  - iOS Simulator: http://localhost:{port}")
    print(f"  - Android Emulator: http://10.0.2.2:{port}")
    print(f"  - Physical device (same WiFi): http://<your-mac-ip>:{port}")
    server.serve_forever()
