# Mopidy Setup for Local File Playback

To play recordings through Mopidy, you need to configure Mopidy to support local file playback.

## Option 1: File Backend (Simplest)

Enable Mopidy's file backend to play `file://` URIs directly:

1. Edit Mopidy config:
   ```bash
   sudo nano /etc/mopidy/mopidy.conf
   ```

2. Add or enable the file backend:
   ```
   [file]
   enabled = true
   media_dirs = 
       /path/to/recordings = Recordings
   ```

3. Restart Mopidy:
   ```bash
   sudo systemctl restart mopidy
   ```

## Option 2: Local Backend (Recommended for Library)

Use Mopidy-Local extension for indexed local files:

1. Install Mopidy-Local:
   ```bash
   sudo python3 -m pip install Mopidy-Local
   ```

2. Edit Mopidy config:
   ```bash
   sudo nano /etc/mopidy/mopidy.conf
   ```

3. Configure local backend:
   ```
   [local]
   media_dir = /path/to/recordings
   scan_timeout = 1000
   ```

4. Scan for files:
   ```bash
   sudo mopidyctl local scan
   ```

5. Restart Mopidy:
   ```bash
   sudo systemctl restart mopidy
   ```

6. Use `local:file:` URIs instead of `file://` URIs in the code.

## Option 3: HTTP Server (Alternative)

Serve recordings via HTTP and use stream backend:

1. Serve recordings directory via HTTP (e.g., using Python's http.server)
2. Use `http://localhost:8000/recording.wav` URIs
3. Mopidy's stream backend will handle these automatically

## Verify Setup

Test if Mopidy can play a local file:

```bash
curl -X POST http://localhost:6680/mopidy/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "core.tracklist.add",
    "params": {"uris": ["file:///path/to/test.wav"]}
  }'
```

If this works, Mopidy is configured correctly for local file playback.

