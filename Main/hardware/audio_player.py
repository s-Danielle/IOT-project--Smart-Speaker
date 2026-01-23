"""
Mopidy wrapper: play_uri, pause, stop
"""

from config.settings import MOPIDY_HOST, MOPIDY_PORT, VOLUME_STEP, VOLUME_DEFAULT
from utils.logger import log_audio, log_error, log_success

# Mopidy RPC client
try:
    import requests
except ImportError:
    raise ImportError("requests library is required. Install with: pip install requests")


class AudioPlayer:
    """Mopidy audio player wrapper using JSON-RPC"""
    
    def __init__(self):
        """Initialize Mopidy connection"""
        self._url = f"http://{MOPIDY_HOST}:{MOPIDY_PORT}/mopidy/rpc"
        self._playing = False
        self._current_uri = None
        self._request_id = 0
        log_audio(f"Audio player initialized (Mopidy at {self._url})")
    
    def _rpc(self, method: str, params: dict = None) -> dict:
        """Send JSON-RPC request to Mopidy"""
        
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            payload["params"] = params
        
        try:
            response = requests.post(self._url, json=payload, timeout=5)
            result = response.json()
            if "error" in result:
                log_error(f"Mopidy error: {result['error']}")
            return result.get("result", {})
        except requests.exceptions.ConnectionError:
            log_error(f"Cannot connect to Mopidy at {self._url}")
            return {}
        except Exception as e:
            log_error(f"Mopidy RPC error: {e}")
            return {}
    
    def play_uri(self, uri: str):
        """Play audio from URI (Spotify, local file, etc.)"""
        log_audio(f"▶️  Playing URI: {uri}")
        self._current_uri = uri
        
        # Clear current tracklist and add new track
        self._rpc("core.tracklist.clear")
        self._rpc("core.tracklist.add", {"uris": [uri]})
        self._rpc("core.playback.play")
        self._playing = True
        log_success(f"Playback started: {uri}")
    
    def pause(self):
        """Pause current playback"""
        log_audio("⏸️  Pausing playback")
        self._rpc("core.playback.pause")
        self._playing = False
        log_success("Playback paused")
    
    def resume(self):
        """Resume paused playback"""
        log_audio("▶️  Resuming playback")
        self._rpc("core.playback.resume")
        self._playing = True
        log_success("Playback resumed")
    
    def stop(self):
        """Stop playback"""
        log_audio("⏹️  Stopping playback")
        self._rpc("core.playback.stop")
        self._playing = False
        self._current_uri = None
        log_success("Playback stopped")
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        return self._playing
    
    def get_current_uri(self) -> str:
        """Get currently loaded URI"""
        return self._current_uri
    
    # =========================================================================
    # VOLUME CONTROL (works while playing, paused, or stopped)
    # Uses Mopidy's mixer API: core.mixer.get_volume / core.mixer.set_volume
    # =========================================================================
    
    def get_volume(self) -> int:
        """Get current volume level (0-100)"""
        result = self._rpc("core.mixer.get_volume")
        if result is None:
            log_error("Failed to get volume, returning default")
            return VOLUME_DEFAULT
        return result
    
    def set_volume(self, volume: int) -> bool:
        """Set volume level (0-100). Returns True if successful."""
        # Clamp volume to valid range
        volume = max(0, min(100, volume))
        log_audio(f"🔊 Setting volume to {volume}")
        result = self._rpc("core.mixer.set_volume", {"volume": volume})
        # set_volume returns True on success
        if result:
            log_success(f"Volume set to {volume}")
        return result is True
    
    def volume_up(self) -> int:
        """Increase volume by VOLUME_STEP. Returns new volume level."""
        current = self.get_volume()
        new_volume = min(100, current + VOLUME_STEP)
        self.set_volume(new_volume)
        log_audio(f"🔊 Volume UP: {current} → {new_volume}")
        return new_volume
    
    def volume_down(self) -> int:
        """Decrease volume by VOLUME_STEP. Returns new volume level."""
        current = self.get_volume()
        new_volume = max(0, current - VOLUME_STEP)
        self.set_volume(new_volume)
        log_audio(f"🔉 Volume DOWN: {current} → {new_volume}")
        return new_volume
    
    def close(self):
        """Clean up audio player resources"""
        self.stop()
        log_audio("Audio player closed")
