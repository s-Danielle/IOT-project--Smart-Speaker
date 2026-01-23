"""
Mopidy wrapper: play_uri, pause, stop
Uses python-mpd2 library for MPD protocol communication
"""

import time
from config.settings import MOPIDY_HOST, MPD_PORT, VOLUME_STEP, VOLUME_DEFAULT, STATUS_POLL_INTERVAL
from utils.logger import log_audio, log_error, log_success
from utils.hardware_health import HardwareHealthManager

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
        
        # Local state cache to minimize Mopidy requests
        self._cached_state = "stop"      # "play", "pause", "stop"
        self._cached_volume = VOLUME_DEFAULT
        self._last_status_check = 0.0    # Timestamp of last status poll
        
        # Register with health manager for connection error tracking
        self._health = HardwareHealthManager.get_instance().register(
            "audio",
            expected_errors=[],  # Log all audio errors (not as frequent as button polling)
            log_interval=10.0,   # Rate-limit to every 10 seconds
            failure_threshold=5  # Mark failed after 5 consecutive connection failures
        )
        
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
                self._health.report_success()
            except MPDConnectionError as e:
                if self._health.report_error(e):
                    log_error(f"Cannot connect to Mopidy MPD at {self._host}:{self._port}: {e}")
                self._connected = False
            except Exception as e:
                if self._health.report_error(e):
                    log_error(f"MPD connection error: {e}")
                self._connected = False
    
    def _execute(self, func, *args, **kwargs):
        """Execute MPD command with automatic reconnection on failure"""
        self._ensure_connected()
        if not self._connected:
            return None
        
        try:
            result = func(*args, **kwargs)
            self._health.report_success()
            return result
        except (MPDConnectionError, OSError, IOError) as e:
            # Connection-related errors - try to reconnect once
            if self._health.report_error(e):
                log_error(f"MPD connection lost: {e}")
            self._connected = False
            self._ensure_connected()
            if self._connected:
                try:
                    result = func(*args, **kwargs)
                    self._health.report_success()
                    return result
                except Exception as e:
                    if self._health.report_error(e):
                        log_error(f"MPD command error after reconnect: {e}")
                    self._connected = False  # Reset for next attempt
                    return None
            else:
                # Connection failed error already logged in _ensure_connected
                return None
        except Exception as e:
            # Other errors (e.g., timeout) - also reset connection state
            if self._health.report_error(e):
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
        self._cached_state = "play"  # Update cache
        log_success(f"Playback started: {uri}")
    
    def pause(self):
        """Pause current playback"""
        log_audio("⏸️  Pausing playback")
        self._execute(self._client.pause, 1)  # 1 = pause
        self._cached_state = "pause"  # Update cache
        log_success("Playback paused")
    
    def resume(self):
        """Resume paused playback"""
        log_audio("▶️  Resuming playback")
        self._execute(self._client.pause, 0)  # 0 = resume
        self._cached_state = "play"  # Update cache
        log_success("Playback resumed")
    
    def stop(self):
        """Stop playback"""
        log_audio("⏹️  Stopping playback")
        self._execute(self._client.stop)
        self._current_uri = None
        self._cached_state = "stop"  # Update cache
        log_success("Playback stopped")
    
    def is_playing(self, force_refresh: bool = False) -> bool:
        """Check if audio is currently playing.
        
        Args:
            force_refresh: If True, bypass cache and query Mopidy directly.
                          Use this when you need guaranteed fresh data, e.g.,
                          when confirming playback has actually started.
        """
        now = time.time()
        
        # Use cache if recent enough (unless force_refresh requested)
        if not force_refresh and now - self._last_status_check < STATUS_POLL_INTERVAL:
            return self._cached_state == "play"
        
        # Poll Mopidy and update cache
        self._last_status_check = now
        status = self._execute(self._client.status)
        if status is not None:
            self._cached_state = status.get("state", "stop")
            # Also update cached volume while we're at it
            vol = status.get("volume")
            if vol is not None:
                try:
                    self._cached_volume = int(vol)
                except (ValueError, TypeError):
                    pass
        
        return self._cached_state == "play"
    
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
        """Get current volume level from Mopidy (0-100)
        
        Always fetches fresh data to ensure accuracy for volume operations.
        """
        status = self._execute(self._client.status)
        if status is None:
            log_error("Failed to get volume, returning cached value")
            return self._cached_volume
        
        volume_str = status.get("volume", None)
        if volume_str is None:
            log_error("Volume not available in status, returning cached value")
            return self._cached_volume
        
        try:
            volume = int(volume_str)
            self._cached_volume = volume  # Update cache
            return volume
        except (ValueError, TypeError):
            log_error(f"Invalid volume value: {volume_str}, returning cached value")
            return self._cached_volume
    
    def set_volume(self, volume: int) -> bool:
        """Set volume level (0-100). Returns True if successful."""
        # Clamp volume to valid range
        volume = max(0, min(100, volume))
        log_audio(f"🔊 Setting volume to {volume}")
        
        # Update cache immediately (optimistic update)
        self._cached_volume = volume
        
        result = self._execute(self._client.setvol, volume)
        if result is None:
            log_error(f"Failed to set volume to {volume}")
            return False
        log_success(f"Volume set to {volume}")
        return True
    
    def volume_up(self) -> int:
        """Increase volume by VOLUME_STEP. Returns new volume level.
        
        Fetches current volume from Mopidy to ensure accuracy with rapid presses.
        """
        current = self.get_volume()
        new_volume = min(100, current + VOLUME_STEP)
        self.set_volume(new_volume)
        log_audio(f"🔊 Volume UP: {current} → {new_volume}")
        return new_volume
    
    def volume_down(self) -> int:
        """Decrease volume by VOLUME_STEP. Returns new volume level.
        
        Fetches current volume from Mopidy to ensure accuracy with rapid presses.
        """
        current = self.get_volume()
        new_volume = max(0, current - VOLUME_STEP)
        self.set_volume(new_volume)
        log_audio(f"🔉 Volume DOWN: {current} → {new_volume}")
        return new_volume
    
    def refresh_status(self) -> dict:
        """Force refresh status from Mopidy, bypassing cache.
        
        Use this when you need guaranteed fresh data, e.g., after
        external changes or at application startup.
        
        Returns the raw status dict from Mopidy, or None on error.
        """
        self._last_status_check = time.time()
        status = self._execute(self._client.status)
        if status is not None:
            self._cached_state = status.get("state", "stop")
            vol = status.get("volume")
            if vol is not None:
                try:
                    self._cached_volume = int(vol)
                except (ValueError, TypeError):
                    pass
        return status
    
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
