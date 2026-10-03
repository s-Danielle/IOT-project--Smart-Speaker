"""
Mopidy wrapper: play_uri, pause, stop
Uses python-mpd2 library for MPD protocol communication
"""

import time
from config.settings import MOPIDY_HOST, MPD_PORT, STATUS_POLL_INTERVAL
from utils.logger import log_audio, log_error
from utils.hardware_health import HardwareHealthManager

# MPD client library
try:
    from mpd import MPDClient
    from mpd.base import CommandError as MPDCommandError
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
        self.last_error = None  # why Mopidy last refused a command, for the caller to log
        
        # Local state cache to minimize Mopidy requests
        self._cached_state = "stop"      # "play", "pause", "stop"
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
    
    def _execute(self, func, *args, _none_is_success=False, **kwargs):
        """Execute MPD command with automatic reconnection on failure"""
        self._ensure_connected()
        if not self._connected:
            return None
        
        try:
            result = func(*args, **kwargs)
            self._health.report_success()
            return True if _none_is_success and result is None else result
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
                    return True if _none_is_success and result is None else result
                except MPDCommandError as e:
                    self.last_error = str(e)
                    log_error(f"Mopidy refused the command after reconnect: {e}")
                    return None
                except Exception as e:
                    if self._health.report_error(e):
                        log_error(f"MPD command error after reconnect: {e}")
                    self._connected = False  # Reset for next attempt
                    return None
            else:
                # Connection failed error already logged in _ensure_connected
                return None
        except MPDCommandError as e:
            # Mopidy answered, but refused this command (for example "add" for a link it
            # cannot find). The connection is fine, so keep it, and remember why.
            self.last_error = str(e)
            log_error(f"Mopidy refused the command: {e}")
            return None
        except Exception as e:
            # Other errors (e.g., timeout) - also reset connection state
            if self._health.report_error(e):
                log_error(f"MPD command error: {e}")
            self._connected = False  # Reset so next call attempts reconnection
            return None
    
    def play_uri(self, uri: str) -> bool:
        """Play audio from URI (Spotify, local file, etc.).

        Returns True if Mopidy accepted the link, False if it could not be started
        (Mopidy refused the link, or could not be reached). The reason is in
        `last_error`. True does not mean sound yet: a Spotify song takes a few
        seconds to start, and the controller waits for that.
        """
        log_audio(f"Playing URI: {uri}")
        self._current_uri = uri
        self.last_error = None

        # Clear current tracklist and add new track
        for command, args in ((self._client.clear, ()), (self._client.add, (uri,)), (self._client.play, ())):
            if self._execute(command, *args, _none_is_success=True) is None:
                reason = self.last_error or "Mopidy could not be reached"
                self.last_error = reason
                log_error(f"Could not start {uri}: {reason}")
                self._current_uri = None
                self._cached_state = "stop"
                return False
        self._cached_state = "play"  # Update cache
        return True
    
    def pause(self):
        """Pause current playback"""
        log_audio("Pausing playback")
        self._execute(self._client.pause, 1)  # 1 = pause
        self._cached_state = "pause"  # Update cache
    
    def resume(self) -> bool:
        """Resume paused playback. Returns False if Mopidy could not be reached."""
        log_audio("Resuming playback")
        if self._execute(self._client.pause, 0, _none_is_success=True) is None:  # 0 = resume
            return False
        self._cached_state = "play"  # Update cache
        return True
    
    def stop(self):
        """Stop playback"""
        log_audio("Stopping playback")
        self._execute(self._client.stop)
        self._current_uri = None
        self._cached_state = "stop"  # Update cache
    
    def is_playing(self, force_refresh: bool = False) -> bool:
        """Check if audio is currently playing.
        
        Args:
            force_refresh: If True, bypass cache and query Mopidy directly.
                          Use this when you need guaranteed fresh data, e.g.,
                          when confirming playback has actually started.
        """
        now = time.monotonic()
        
        # Use cache if recent enough (unless force_refresh requested)
        if not force_refresh and now - self._last_status_check < STATUS_POLL_INTERVAL:
            return self._cached_state == "play"
        
        # Poll Mopidy and update cache
        self._last_status_check = now
        status = self._execute(self._client.status)
        if status is not None:
            self._cached_state = status.get("state", "stop")
        
        return self._cached_state == "play"
    
    def get_current_uri(self) -> str:
        """Get currently loaded URI"""
        # Try to get URI from MPD current song
        song = self._execute(self._client.currentsong)
        if song and "file" in song:
            return song["file"]
        # Fall back to cached URI
        return self._current_uri
    
    def refresh_status(self) -> dict:
        """Force refresh status from Mopidy, bypassing cache.
        
        Use this when you need guaranteed fresh data, e.g., after
        external changes or at application startup.
        
        Returns the raw status dict from Mopidy, or None on error.
        """
        self._last_status_check = time.monotonic()
        status = self._execute(self._client.status)
        if status is not None:
            self._cached_state = status.get("state", "stop")
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
