"""
Mopidy wrapper: play_uri, pause, stop
Uses python-mpd2 library for MPD protocol communication
"""

from config.settings import MOPIDY_HOST, MPD_PORT, VOLUME_STEP, VOLUME_DEFAULT
from utils.logger import log_audio, log_error, log_success

# MPD client library
try:
    from mpd import MPDClient
    from mpd.base import ConnectionError as MPDConnectionError
except ImportError:
    raise ImportError("python-mpd2 library is required. Install with: pip install python-mpd2")


class AudioPlayer:
    """Mopidy audio player wrapper using MPD protocol via python-mpd2"""
    
    def __init__(self):
        """Initialize MPD connection to Mopidy"""
        self._client = MPDClient()
        self._client.timeout = 5  # Network timeout in seconds
        self._host = MOPIDY_HOST
        self._port = MPD_PORT
        self._connected = False
        self._current_uri = None
        
        # Connect to Mopidy MPD server
        self._ensure_connected()
        log_audio(f"Audio player initialized (Mopidy MPD at {self._host}:{self._port})")
    
    def _ensure_connected(self):
        """Ensure MPD connection is established"""
        if not self._connected:
            try:
                # Ensure clean state before connecting
                try:
                    self._client.disconnect()
                except:
                    pass
                self._client.connect(self._host, self._port)
                self._connected = True
            except MPDConnectionError as e:
                log_error(f"Cannot connect to Mopidy MPD at {self._host}:{self._port}: {e}")
                self._connected = False
            except Exception as e:
                log_error(f"MPD connection error: {e}")
                self._connected = False
    
    def _execute(self, func, *args, **kwargs):
        """Execute MPD command with automatic reconnection on failure"""
        self._ensure_connected()
        if not self._connected:
            return None
        
        try:
            return func(*args, **kwargs)
        except (MPDConnectionError, OSError, IOError) as e:
            # Connection-related errors - try to reconnect once
            log_error(f"MPD connection lost: {e}")
            self._connected = False
            self._ensure_connected()
            if self._connected:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    log_error(f"MPD command error after reconnect: {e}")
                    self._connected = False  # Reset for next attempt
                    return None
            else:
                log_error("Failed to reconnect to Mopidy MPD")
                return None
        except Exception as e:
            # Other errors (e.g., timeout) - also reset connection state
            log_error(f"MPD command error: {e}")
            self._connected = False  # Reset so next call attempts reconnection
            return None
    
    def play_uri(self, uri: str):
        """Play audio from URI (Spotify, local file, etc.)"""
        log_audio(f"▶️  Playing URI: {uri}")
        self._current_uri = uri
        
        # Clear current tracklist and add new track
        self._execute(self._client.clear)
        self._execute(self._client.add, uri)
        self._execute(self._client.play)
        log_success(f"Playback started: {uri}")
    
    def pause(self):
        """Pause current playback"""
        log_audio("⏸️  Pausing playback")
        self._execute(self._client.pause, 1)  # 1 = pause
        log_success("Playback paused")
    
    def resume(self):
        """Resume paused playback"""
        log_audio("▶️  Resuming playback")
        self._execute(self._client.pause, 0)  # 0 = resume
        log_success("Playback resumed")
    
    def stop(self):
        """Stop playback"""
        log_audio("⏹️  Stopping playback")
        self._execute(self._client.stop)
        self._current_uri = None
        log_success("Playback stopped")
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        status = self._execute(self._client.status)
        if status is None:
            return False
        state = status.get("state", "stop")
        return state == "play"
    
    def get_current_uri(self) -> str:
        """Get currently loaded URI"""
        # Try to get URI from MPD current song
        song = self._execute(self._client.currentsong)
        if song and "file" in song:
            return song["file"]
        # Fall back to cached URI
        return self._current_uri
    
    # =========================================================================
    # VOLUME CONTROL (works while playing, paused, or stopped)
    # Uses MPD's volume commands: status() for get, setvol() for set
    # =========================================================================
    
    def get_volume(self) -> int:
        """Get current volume level (0-100)"""
        status = self._execute(self._client.status)
        if status is None:
            log_error("Failed to get volume, returning default")
            return VOLUME_DEFAULT
        
        volume_str = status.get("volume", None)
        if volume_str is None:
            log_error("Volume not available in status, returning default")
            return VOLUME_DEFAULT
        
        try:
            volume = int(volume_str)
            return volume
        except (ValueError, TypeError):
            log_error(f"Invalid volume value: {volume_str}, returning default")
            return VOLUME_DEFAULT
    
    def set_volume(self, volume: int) -> bool:
        """Set volume level (0-100). Returns True if successful."""
        # Clamp volume to valid range
        volume = max(0, min(100, volume))
        log_audio(f"🔊 Setting volume to {volume}")
        
        try:
            self._execute(self._client.setvol, volume)
            log_success(f"Volume set to {volume}")
            return True
        except Exception as e:
            log_error(f"Failed to set volume: {e}")
            return False
    
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
        if self._connected:
            try:
                self._client.disconnect()
                self._connected = False
            except Exception as e:
                log_error(f"Error disconnecting from MPD: {e}")
        log_audio("Audio player closed")
