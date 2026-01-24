"""
Main loop: polls inputs, updates state
Implements the full state machine from States.txt
"""

import time
import os
from datetime import datetime


from core.state import DeviceState, State
from core import actions
from hardware.nfc_scanner import NFCScanner
from hardware.chip_store import ChipStore
from hardware.buttons import Buttons, ButtonID
from hardware.audio_player import AudioPlayer
from hardware.recorder import Recorder
from ui.ui_controller import UIController
from config.settings import (
    LOOP_INTERVAL, 
    RECORD_HOLD_DURATION, 
    CLEAR_CHIP_HOLD_DURATION,
    PLAY_LATEST_HOLD_DURATION,
    MAX_WAIT_FOR_PLAYBACK,
    MIN_PLAYBACK_DURATION,
    PTT_ENABLED,
    BUTTON_PTT_BIT,
)
from utils.logger import log, log_state, log_event, log_error, log_button
from typing import Optional
from utils.server_client import get_parental_controls
from hardware.leds import RGBLeds, Colors


class Controller:
    """Main controller that handles the event loop and state machine"""
    
    def __init__(self):
        log("=" * 60)
        log("SMART SPEAKER CONTROLLER STARTING")
        log("=" * 60)
        
        self.device_state = DeviceState()
        self._running = False
        
        # Initialize hardware components
        log("Initializing components...")
        self._nfc = NFCScanner()
        self._chip_store = ChipStore()
        self._buttons = Buttons()
        self._audio = AudioPlayer()
        self._recorder = Recorder()
        self._ui = UIController()
        
        # Track record button arming (need to hold 3s then release)
        self._record_armed = False
        self._countdown_played = False  # Track if countdown sound was played
        
        # Track stop button long-press to prevent repeated execution
        self._stop_long_press_triggered = False
        
        # Track Play/Pause button long-press to prevent repeated execution
        self._play_pause_long_press_triggered = False
        
        # Track NFC chip presence for edge detection
        self._last_nfc_uid: Optional[str] = None
        self._nfc_chip_present = False
        
        # PTT (Push-to-Talk) voice command support
        self._voice_command = None
        self._ptt_leds = None
        if PTT_ENABLED:
            try:
                from hardware.voice_command import VoiceCommand
                self._voice_command = VoiceCommand()
                self._ptt_leds = RGBLeds()  # Separate instance to control Light 1
                log("[PTT] Voice command support enabled")
            except Exception as e:
                log_error(f"[PTT] Failed to initialize voice commands: {e}")
                self._voice_command = None
        
        # Track when play was initiated to allow grace period for Mopidy startup
        self._play_initiated_time: Optional[float] = None
        
        # Track when Mopidy actually confirmed playback (reported "play" state)
        # This handles variable Spotify loading times (can take up to 10s)
        self._playback_confirmed = False
        self._playback_confirmed_time: Optional[float] = None
        
        log_state(f"Initial state: {self.device_state.state}")
        log("=" * 60)
        log("READY - Waiting for input...")
        log("=" * 60)
    
    def run(self):
        """Run the main non-blocking loop"""
        self._running = True
        
        try:
            while self._running:
                # Update button states
                self._buttons.update()
                
                # Process inputs based on current state
                self._handle_nfc()
                self._handle_buttons()
                
                # Check if playback finished naturally
                self._check_playback_finished()
                
                # Sleep for loop interval
                time.sleep(LOOP_INTERVAL)
                
        except KeyboardInterrupt:
            log("\nShutdown requested...")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown"""
        log("=" * 60)
        log("SHUTTING DOWN")
        log("=" * 60)
        self._running = False
        self._nfc.close()
        self._buttons.close()
        self._audio.close()
        self._recorder.close()
        log("Goodbye!")
    
    def stop(self):
        """Stop the main loop"""
        self._running = False
    
    def _play_latest_recording(self):
        """Play the most recent recording file"""
        from config.paths import RECORDINGS_DIR
        
        # Check parental controls - quiet hours
        if self._check_quiet_hours():
            self._ui.on_blocked_action()
            return
        
        log_event(f"[DEBUG] Looking for recordings in: {RECORDINGS_DIR}")
        
        # Find all recording files
        if not os.path.exists(RECORDINGS_DIR):
            log_event(f"[DEBUG] Recordings directory does not exist: {RECORDINGS_DIR}")
            log_event("No recordings directory found")
            self._ui.on_error()
            return
        
        log_event(f"[DEBUG] Scanning directory: {RECORDINGS_DIR}")
        all_files = os.listdir(RECORDINGS_DIR)
        log_event(f"[DEBUG] Found {len(all_files)} files in directory")
        
        recording_files = []
        for filename in all_files:
            log_event(f"[DEBUG] Checking file: {filename}")
            if filename.endswith('.wav') and filename.startswith('recording_'):
                filepath = os.path.join(RECORDINGS_DIR, filename)
                if os.path.isfile(filepath):
                    mtime = os.path.getmtime(filepath)
                    size = os.path.getsize(filepath)
                    recording_files.append((filepath, mtime))
                    log_event(f"[DEBUG] Found recording: {filename} (size: {size} bytes, mtime: {mtime})")
        
        log_event(f"[DEBUG] Total recording files found: {len(recording_files)}")
        
        if not recording_files:
            log_event("No recordings found")
            log_event("[DEBUG] To create a recording:")
            log_event("[DEBUG]   1. Load a chip")
            log_event("[DEBUG]   2. Hold Record button for 3 seconds")
            log_event("[DEBUG]   3. Release to start recording")
            log_event("[DEBUG]   4. Press Record again to save")
            self._ui.on_error()
            return
        
        # Sort by modification time (newest first)
        recording_files.sort(key=lambda x: x[1], reverse=True)
        latest_recording = recording_files[0][0]
        
        # Get absolute path for Mopidy
        abs_path = os.path.abspath(latest_recording)
        
        log_event(f"[DEBUG] Selected latest recording: {os.path.basename(latest_recording)}")
        log_event(f"[DEBUG] Absolute path: {abs_path}")
        log_event(f"Playing latest recording: {os.path.basename(latest_recording)}")
        
        # Convert to URI for Mopidy
        # Mopidy supports multiple URI formats:
        # 1. file:// URIs (if file backend is enabled)
        # 2. local:file: URIs (if local backend is configured)
        # 3. We'll try file:// first, then fall back to local:file: if needed
        
        # Try file:// URI format first (works if file backend is enabled)
        if os.name == 'nt':  # Windows
            # Windows: file:///C:/path/to/file
            file_uri = f"file:///{abs_path.replace(os.sep, '/')}"
        else:
            # Unix/Mac: file:///absolute/path (three slashes for absolute)
            file_uri = f"file://{abs_path}"
        
        # Alternative: Use local:file: URI if Mopidy-Local is configured
        # This requires the recordings directory to be in Mopidy's media_dir
        # For now, we'll use file:// and let Mopidy handle it
        
        log_event(f"[DEBUG] File URI: {file_uri}")
        log_event(f"[DEBUG] Note: Mopidy needs file backend enabled or local backend configured")
        
        # Verify file exists and is readable
        if not os.path.exists(abs_path):
            log_error(f"[DEBUG] File does not exist: {abs_path}")
            self._ui.on_error()
            return
        
        if not os.access(abs_path, os.R_OK):
            log_error(f"[DEBUG] File is not readable: {abs_path}")
            self._ui.on_error()
            return
        
        log_event(f"[DEBUG] Calling audio.play_uri() with: {file_uri}")
        
        # Try to play the file
        # Note: Mopidy needs one of these configured:
        # 1. File backend enabled (supports file:// URIs directly)
        # 2. Local backend with recordings directory in media_dir
        # 3. Stream backend (for HTTP-served files)
        try:
            # Track play initiation time and reset tracking state
            self._play_initiated_time = time.time()
            self._playback_confirmed = False
            self._playback_confirmed_time = None
            self._audio.play_uri(file_uri)
            log_event(f"[DEBUG] Playback command sent to Mopidy")
        except Exception as e:
            log_error(f"[DEBUG] Failed to play recording: {e}")
            log_error("[DEBUG] Mopidy may need file backend enabled or local backend configured")
            self._ui.on_error()
            return
        
        log_event(f"[DEBUG] Calling ui.on_play()")
        self._ui.on_play()
        
        # Track previous state so we can return to it on stop
        # If no chip loaded, we'll return to IDLE_NO_CHIP, otherwise IDLE_CHIP_LOADED
        self.device_state.previous_state = self.device_state.state
        
        # Update state to PLAYING
        self.device_state.state = State.PLAYING
        log_state(f"→ {self.device_state.state}")
    
    # =========================================================================
    # PLAYBACK STATUS MONITORING
    # =========================================================================
    
    def _check_playback_finished(self):
        """Check if playback has finished naturally and update state accordingly.
        
        Uses "playback confirmed" tracking to handle variable Spotify loading times:
        1. Wait for Mopidy to actually report "play" state (can take up to 10s for Spotify)
        2. Once confirmed, require minimum playback duration before considering "finished"
        3. This prevents false "finished" triggers during loading/buffering
        """
        # Only check when we think we're playing
        if self.device_state.state != State.PLAYING:
            return
        
        now = time.time()
        
        # Phase 1: Wait for playback to be confirmed
        if not self._playback_confirmed:
            # Force fresh check - don't rely on cached state since play() 
            # optimistically sets cache to "play" before Mopidy actually starts
            is_actually_playing = self._audio.is_playing(force_refresh=True)
            if is_actually_playing:
                # Mopidy now reports "play" - playback is confirmed!
                self._playback_confirmed = True
                self._playback_confirmed_time = now
                log_event("Playback confirmed by Mopidy")
                return
            else:
                # Still waiting for Mopidy to start playing
                if self._play_initiated_time is not None:
                    elapsed = now - self._play_initiated_time
                    if elapsed > MAX_WAIT_FOR_PLAYBACK:
                        # Timeout - playback never started, something went wrong
                        log_event(f"Playback timeout after {elapsed:.1f}s - Mopidy never started playing")
                        self._reset_playback_tracking()
                        
                        if self.device_state.loaded_chip is not None:
                            self.device_state.state = State.IDLE_CHIP_LOADED
                        else:
                            self.device_state.state = State.IDLE_NO_CHIP
                        
                        self._ui.on_error()
                        log_state(f"→ {self.device_state.state} (playback failed)")
                return
        
        # Phase 2: Playback was confirmed, now monitor for natural end
        # Cached state is fine here - we're just detecting when playback stops
        if not self._audio.is_playing():
            # Mopidy stopped - but only consider it "finished" if minimum duration passed
            if self._playback_confirmed_time is not None:
                playback_duration = now - self._playback_confirmed_time
                if playback_duration < MIN_PLAYBACK_DURATION:
                    # Too short - likely a transient state, ignore
                    log_event(f"Ignoring brief stop after {playback_duration:.1f}s (min: {MIN_PLAYBACK_DURATION}s)")
                    # Reset confirmed state to re-wait for playback
                    self._playback_confirmed = False
                    self._playback_confirmed_time = None
                    return
            
            # Playback genuinely finished
            log_event("Playback finished - returning to idle state")
            self._reset_playback_tracking()
            
            if self.device_state.loaded_chip is not None:
                self.device_state.state = State.IDLE_CHIP_LOADED
            else:
                self.device_state.state = State.IDLE_NO_CHIP
            
            self._ui.on_stop()
            log_state(f"→ {self.device_state.state} (track ended)")
    
    def _reset_playback_tracking(self):
        """Reset playback tracking state"""
        self._play_initiated_time = None
        self._playback_confirmed = False
        self._playback_confirmed_time = None
    
    # =========================================================================
    # PARENTAL CONTROLS
    # =========================================================================
    
    def _check_quiet_hours(self) -> bool:
        """Check if playback is blocked due to quiet hours.
        Returns True if blocked, False if allowed.
        """
        try:
            pc = get_parental_controls()
            if not pc.get('enabled', False):
                return False
            
            qh = pc.get('quiet_hours', {})
            if not qh.get('enabled', False):
                return False
            
            start_str = qh.get('start', '21:00')
            end_str = qh.get('end', '07:00')
            
            now = datetime.now().time()
            start_time = datetime.strptime(start_str, '%H:%M').time()
            end_time = datetime.strptime(end_str, '%H:%M').time()
            
            # Handle overnight quiet hours (e.g., 21:00 to 07:00)
            if start_time > end_time:
                # Quiet hours span midnight
                is_quiet = now >= start_time or now <= end_time
            else:
                # Quiet hours within same day
                is_quiet = start_time <= now <= end_time
            
            if is_quiet:
                log_event(f"[PARENTAL] Playback blocked - quiet hours active ({start_str}-{end_str})")
                return True
            
            return False
        except Exception as e:
            log_error(f"[PARENTAL] Error checking quiet hours: {e}")
            return False
    
    def _check_chip_allowed(self, uid: str) -> bool:
        """Check if a chip is allowed based on whitelist/blacklist.
        Returns True if blocked, False if allowed.
        """
        try:
            pc = get_parental_controls()
            if not pc.get('enabled', False):
                return False
            
            blacklist = pc.get('chip_blacklist', [])
            whitelist_mode = pc.get('chip_whitelist_mode', False)
            whitelist = pc.get('chip_whitelist', [])
            
            # Check blacklist first
            if uid in blacklist:
                log_event(f"[PARENTAL] Chip blocked - UID in blacklist")
                return True
            
            # Check whitelist mode
            if whitelist_mode and whitelist:
                if uid not in whitelist:
                    log_event(f"[PARENTAL] Chip blocked - UID not in whitelist")
                    return True
            
            return False
        except Exception as e:
            log_error(f"[PARENTAL] Error checking chip allowed: {e}")
            return False
    
    def _get_volume_limit(self) -> int:
        """Get the volume limit from parental controls.
        Returns 100 if no limit or parental controls disabled.
        """
        try:
            pc = get_parental_controls()
            if not pc.get('enabled', False):
                return 100
            
            return pc.get('volume_limit', 100)
        except Exception as e:
            log_error(f"[PARENTAL] Error getting volume limit: {e}")
            return 100
    
    def _enforce_volume_limit(self, volume: int) -> int:
        """Enforce volume limit from parental controls.
        Returns the capped volume value.
        """
        limit = self._get_volume_limit()
        if volume > limit:
            log_event(f"[PARENTAL] Volume capped at {limit}% (limit enforced)")
            return limit
        return volume
    
    # =========================================================================
    # NFC HANDLING
    # =========================================================================
    
    def _handle_nfc(self):
        """Handle NFC chip scans based on current state"""
        uid = self._nfc.read_uid()
        
        # Detect chip arrival/departure (edge detection)
        chip_now_present = (uid is not None)
        chip_just_arrived = chip_now_present and not self._nfc_chip_present
        chip_just_removed = not chip_now_present and self._nfc_chip_present
        
        self._nfc_chip_present = chip_now_present
        
        # Only process on chip arrival (edge detection)
        if not chip_just_arrived:
            if chip_just_removed:
                # Chip removed - reset tracking
                self._last_nfc_uid = None
            return
        
        # Chip just arrived - process it
        state = self.device_state.state
        
        # RECORDING: Ignore all NFC scans
        if state == State.RECORDING:
            log_event(f"NFC scan ignored (recording in progress)")
            self._ui.on_blocked_action()
            self._last_nfc_uid = uid  # Track it so we don't process again
            return
        
        # Look up chip data (auto-registers unknown chips)
        chip_data = self._chip_store.lookup(uid)
        
        if chip_data is None:
            # This shouldn't happen with auto-registration, but handle it
            log_event(f"Failed to look up chip: {uid}")
            self._ui.on_error()
            self._last_nfc_uid = uid
            return
        
        # Check if same chip is already loaded
        if self.device_state.loaded_chip and self.device_state.loaded_chip.uid == uid:
            log_event("Same chip scanned - no action")
            self._ui.on_same_chip_scanned()
            self._last_nfc_uid = uid
            return
        
        # Check parental controls - whitelist/blacklist
        if self._check_chip_allowed(uid):
            self._ui.on_blocked_action()
            self._last_nfc_uid = uid
            return
        
        # Check if chip has a song assigned
        if not chip_data.get('uri'):
            # Chip recognized but no song assigned
            if chip_data.get('is_new'):
                log_event(f"New chip registered: '{chip_data.get('name')}' - assign a song in the app!")
            else:
                log_event(f"Chip '{chip_data.get('name')}' has no song assigned - use the app to assign one")
            
            # Still load the chip so user can record on it
            self._reset_playback_tracking()  # Reset tracking when loading new chip
            self.device_state = actions.action_load_chip(
                self.device_state, chip_data, self._audio, self._ui
            )
            self._last_nfc_uid = uid
            return
        
        # Different chip or no chip loaded - load the new chip
        # If playing, this stops playback and loads new chip
        self._reset_playback_tracking()  # Reset tracking when loading new chip
        self.device_state = actions.action_load_chip(
            self.device_state, chip_data, self._audio, self._ui
        )
        self._last_nfc_uid = uid
    
    # =========================================================================
    # BUTTON HANDLING
    # =========================================================================
    
    def _handle_buttons(self):
        """Handle button presses based on current state"""
        state = self.device_state.state
        
        # Handle Play/Pause button
        self._handle_play_pause_button(state)
        
        # Handle Record button
        self._handle_record_button(state)
        
        # Handle Stop button
        self._handle_stop_button(state)
        
        # Handle Volume buttons (work in all states except recording)
        self._handle_volume_buttons(state)
        
        # Handle PTT (Push-to-Talk) button for voice commands
        self._handle_ptt_button(state)
    
    def _handle_play_pause_button(self, state: State):
        """Handle Play/Pause button logic
        - Long press (2s): Play latest recording
        - Short press: Toggle play/pause
        """
        # Check for long press first (play latest recording)
        if self._buttons.is_pressed(ButtonID.PLAY_PAUSE):
            hold_time = self._buttons.hold_duration(ButtonID.PLAY_PAUSE)
            if hold_time >= PLAY_LATEST_HOLD_DURATION and not self._play_pause_long_press_triggered:
                self._play_pause_long_press_triggered = True
                
                # Validate state before playing recording
                if state == State.IDLE_NO_CHIP:
                    log_event("Play latest recording blocked - no chip loaded")
                    self._ui.on_blocked_action()
                    return
                
                if state == State.RECORDING:
                    log_event("Play latest recording blocked - recording in progress")
                    self._ui.on_blocked_action()
                    return
                
                log_button(f"▶️ Play/Pause held {hold_time:.1f}s - PLAYING LATEST RECORDING")
                self._play_latest_recording()
                return
        
        # Reset long-press flag when button is released
        if self._buttons.just_released(ButtonID.PLAY_PAUSE):
            was_long_press = self._play_pause_long_press_triggered
            self._play_pause_long_press_triggered = False
            if was_long_press:
                # Long press was handled, skip short press
                return
        
        # Short press handling (only if not long press)
        if not self._buttons.just_released(ButtonID.PLAY_PAUSE):
            return
        
        log_button("Play/Pause button action")
        
        # IDLE_NO_CHIP: No effect
        if state == State.IDLE_NO_CHIP:
            log_event("Play/Pause blocked - no chip loaded")
            self._ui.on_blocked_action()
            return
        
        # RECORDING: Ignored
        if state == State.RECORDING:
            log_event("Play/Pause blocked - recording in progress")
            self._ui.on_blocked_action()
            return
        
        # IDLE_CHIP_LOADED: Start playback
        if state == State.IDLE_CHIP_LOADED:
            # Check parental controls - quiet hours
            if self._check_quiet_hours():
                self._ui.on_blocked_action()
                return
            
            # Track play initiation time and reset tracking state
            self._play_initiated_time = time.time()
            self._playback_confirmed = False
            self._playback_confirmed_time = None
            self.device_state = actions.action_play(
                self.device_state, self._audio, self._ui, self._chip_store
            )
            return
        
        # PLAYING: Pause
        if state == State.PLAYING:
            self._reset_playback_tracking()  # Reset tracking on user pause
            self.device_state = actions.action_pause(
                self.device_state, self._audio, self._ui
            )
            return
        
        # PAUSED: Resume
        if state == State.PAUSED:
            # Track resume time - resuming may also need buffering for Spotify
            self._play_initiated_time = time.time()
            self._playback_confirmed = False
            self._playback_confirmed_time = None
            self.device_state = actions.action_resume(
                self.device_state, self._audio, self._ui
            )
            return
    
    def _handle_record_button(self, state: State):
        """
        Handle Record button logic
        - Hold 3s (countdown plays): Release after countdown to start recording
        - Short press while recording: Save recording
        """
        # IDLE_NO_CHIP: No effect
        if state == State.IDLE_NO_CHIP:
            if self._buttons.just_released(ButtonID.RECORD):
                log_event("Record blocked - no chip loaded")
                self._ui.on_blocked_action()
            return
        
        # RECORDING: Press (not release) saves recording
        # Detect button press (transition from not pressed to pressed)
        if state == State.RECORDING:
            if self._buttons.just_pressed(ButtonID.RECORD):
                log_button("Record button pressed - saving recording")
                self.device_state = actions.action_save_recording(
                    self.device_state, self._recorder, self._ui
                )
            return
        
        # Other states: Track hold duration - recording starts at 3s automatically
        if self._buttons.is_pressed(ButtonID.RECORD):
            hold_time = self._buttons.hold_duration(ButtonID.RECORD)
            
            # Play countdown sound when button is first pressed and held
            if hold_time > 0.1 and not self._countdown_played:
                log_button("🎙️ Playing countdown - hold for 3 seconds")
                self._ui._sounds.play_record_start()  # Play countdown.wav
                self._countdown_played = True
            
            # Start recording when 3s threshold is reached (whether button is still held or not)
            if hold_time >= RECORD_HOLD_DURATION and not self._record_armed:
                self._record_armed = True
                log_button(f"🎙️ Record ARMED (held {hold_time:.1f}s) - starting recording now")
                # Stop countdown sound
                self._ui._sounds.stop()
                self._countdown_played = False
                # Start recording immediately (no need to wait for release)
                self.device_state = actions.action_start_recording(
                    self.device_state, self._audio, self._recorder, self._ui
                )
        
        # On release: only stop countdown if recording hasn't started yet
        if self._buttons.just_released(ButtonID.RECORD):
            if not self._record_armed:
                # Recording didn't start - stop countdown
                if self._countdown_played:
                    log_button("Stopping countdown sound (released before 3s)")
                    self._ui._sounds.stop()
                hold_time = self._buttons.get_release_duration(ButtonID.RECORD)
                if hold_time < RECORD_HOLD_DURATION:
                    log_button(f"Record released too early ({hold_time:.1f}s < {RECORD_HOLD_DURATION}s)")
            
            # Reset flags (but _record_armed is already True if recording started)
            self._countdown_played = False
        
        # Reset armed state if button released and we're not recording
        if not self._buttons.is_pressed(ButtonID.RECORD) and state != State.RECORDING:
            self._record_armed = False
            self._countdown_played = False
    
    def _handle_stop_button(self, state: State):
        """
        Handle Stop button logic
        - Short press: Stop playback OR cancel recording
        - Long press (5s): Clear chip
        """
        # IDLE_NO_CHIP: No effect
        if state == State.IDLE_NO_CHIP:
            if self._buttons.just_released(ButtonID.STOP):
                log_event("Stop blocked - no chip loaded")
                self._ui.on_blocked_action()
            return
        
        # Check for long press (3s) to clear chip
        # Exception: During RECORDING, long press just cancels (keeps chip loaded)
        if self._buttons.is_pressed(ButtonID.STOP):
            hold_time = self._buttons.hold_duration(ButtonID.STOP)
            
            # Only trigger once per long press (prevent repeated execution)
            if hold_time >= CLEAR_CHIP_HOLD_DURATION and not self._stop_long_press_triggered:
                self._stop_long_press_triggered = True
                
                if state == State.RECORDING:
                    # During recording: long press just cancels (keeps chip loaded)
                    log_button(f"🔄 Stop held {hold_time:.1f}s - CANCELING RECORDING (keeping chip)")
                    self.device_state = actions.action_cancel_recording(
                        self.device_state, self._recorder, self._audio, self._ui
                    )
                else:
                    # All other states: long press clears chip
                    log_button(f"🔄 Stop held {hold_time:.1f}s - CLEARING CHIP")
                    self._reset_playback_tracking()  # Reset tracking on clear chip
                    self.device_state = actions.action_clear_chip(
                        self.device_state, self._audio, self._ui, long_press=True
                    )
                return
        
        # Reset long-press flag when button is released
        if self._buttons.just_released(ButtonID.STOP):
            was_long_press = self._stop_long_press_triggered
            self._stop_long_press_triggered = False
            
            # If it was a long press, we already handled it above
            if was_long_press:
                return
            
            hold_time = self._buttons.get_release_duration(ButtonID.STOP)
            
            log_button(f"Stop short press ({hold_time:.2f}s)")
            
            # RECORDING: Cancel recording (no save) - returns to previous state
            if state == State.RECORDING:
                self.device_state = actions.action_cancel_recording(
                    self.device_state, self._recorder, self._audio, self._ui
                )
                return
            
            # IDLE_CHIP_LOADED: Clear chip (short press)
            if state == State.IDLE_CHIP_LOADED:
                self.device_state = actions.action_clear_chip(
                    self.device_state, self._audio, self._ui
                )
                return
            
            # PLAYING or PAUSED: Stop playback, keep chip
            if state in (State.PLAYING, State.PAUSED):
                self._reset_playback_tracking()  # Reset tracking on user stop
                self.device_state = actions.action_stop(
                    self.device_state, self._audio, self._ui
                )
                return
    
    def _handle_volume_buttons(self, state: State):
        """
        Handle Volume Up/Down buttons
        - Volume can be adjusted in any state except RECORDING
        - Works while playing, paused, or idle (via Mopidy's mixer API)
        """
        # RECORDING: Volume buttons are blocked
        if state == State.RECORDING:
            if self._buttons.just_pressed(ButtonID.VOLUME_UP) or self._buttons.just_pressed(ButtonID.VOLUME_DOWN):
                log_event("Volume adjustment blocked - recording in progress")
                self._ui.on_blocked_action()
            return
        
        # Volume Up - trigger on button press (not release) for responsive feel
        if self._buttons.just_pressed(ButtonID.VOLUME_UP):
            new_vol = self._audio.volume_up()
            # Enforce parental volume limit
            limit = self._get_volume_limit()
            if new_vol > limit:
                log_event(f"[PARENTAL] Volume capped at {limit}% (limit enforced)")
                self._audio.set_volume(limit)
                new_vol = limit
            log_button(f"🔊 Volume UP → {new_vol}")
            self._ui.on_volume_change(new_vol)
            return
        
        # Volume Down - trigger on button press (not release) for responsive feel
        if self._buttons.just_pressed(ButtonID.VOLUME_DOWN):
            new_vol = self._audio.volume_down()
            log_button(f"🔉 Volume DOWN → {new_vol}")
            self._ui.on_volume_change(new_vol)
            return
    
    def _handle_ptt_button(self, state: State):
        """
        Handle PTT (Push-to-Talk) button for voice commands.
        
        When pressed:
        1. Take over Light 1 (health LED) - set to BLUE (listening)
        2. Record audio for ~2.5 seconds
        3. Set Light 1 to CYAN (processing)
        4. Transcribe and parse command
        5. Execute command if recognized
        6. Flash GREEN (success) or RED (not recognized)
        7. Health monitor will restore Light 1 within 5 seconds
        
        Supported commands (must start with "hi speaker"):
        - "hi speaker play" -> play/resume
        - "hi speaker pause" -> pause
        - "hi speaker stop" -> stop
        - "hi speaker clear" -> clear chip
        """
        # Skip if PTT not enabled or not initialized
        if self._voice_command is None:
            return
        
        # Check if PTT button was just pressed
        if not self._buttons.just_pressed(ButtonID.PTT):
            return
        
        # Block PTT during recording
        if state == State.RECORDING:
            log_event("[PTT] Blocked - recording in progress")
            self._ui.on_blocked_action()
            return
        
        log_button("🎙️ PTT button pressed - listening for voice command")
        
        # Step 1: Take over Light 1 - BLUE (listening)
        if self._ptt_leds:
            self._ptt_leds.set_light(1, Colors.BLUE)
        
        # Step 2: Listen and transcribe
        if self._ptt_leds:
            self._ptt_leds.set_light(1, Colors.CYAN)  # CYAN = processing
        
        command = self._voice_command.listen_and_parse()
        
        # Step 3: Execute command if recognized
        if command == "play":
            # Check quiet hours
            if self._check_quiet_hours():
                self._ui.on_blocked_action()
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.RED)
                    time.sleep(0.3)
                return
            
            if state == State.PAUSED:
                # Resume paused playback
                self._play_initiated_time = time.time()
                self._playback_confirmed = False
                self._playback_confirmed_time = None
                self.device_state = actions.action_resume(
                    self.device_state, self._audio, self._ui
                )
            elif state == State.IDLE_CHIP_LOADED:
                # Start playback
                self._play_initiated_time = time.time()
                self._playback_confirmed = False
                self._playback_confirmed_time = None
                self.device_state = actions.action_play(
                    self.device_state, self._audio, self._ui, self._chip_store
                )
            elif state == State.IDLE_NO_CHIP:
                log_event("[PTT] Play blocked - no chip loaded")
                self._ui.on_blocked_action()
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.RED)
                    time.sleep(0.3)
                return
            else:
                # Already playing - do nothing special
                log_event("[PTT] Already playing")
            
            if self._ptt_leds:
                self._ptt_leds.set_light(1, Colors.GREEN)
                time.sleep(0.3)
        
        elif command == "pause":
            if state == State.PLAYING:
                self._reset_playback_tracking()
                self.device_state = actions.action_pause(
                    self.device_state, self._audio, self._ui
                )
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.GREEN)
                    time.sleep(0.3)
            else:
                log_event("[PTT] Pause ignored - not playing")
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.RED)
                    time.sleep(0.3)
        
        elif command == "stop":
            if state in (State.PLAYING, State.PAUSED):
                self._reset_playback_tracking()
                self.device_state = actions.action_stop(
                    self.device_state, self._audio, self._ui
                )
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.GREEN)
                    time.sleep(0.3)
            else:
                log_event("[PTT] Stop ignored - not playing or paused")
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.RED)
                    time.sleep(0.3)
        
        elif command == "clear":
            if state != State.IDLE_NO_CHIP:
                self._reset_playback_tracking()
                # Clear the song assignment from the chip (via HTTP), not just unload it
                self.device_state = actions.action_voice_clear_assignment(
                    self.device_state, self._audio, self._ui
                )
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.GREEN)
                    time.sleep(0.3)
            else:
                log_event("[PTT] Clear ignored - no chip loaded")
                if self._ptt_leds:
                    self._ptt_leds.set_light(1, Colors.RED)
                    time.sleep(0.3)
        
        else:
            # Command not recognized - flash RED
            log_event("[PTT] Command not recognized")
            if self._ptt_leds:
                self._ptt_leds.set_light(1, Colors.RED)
                time.sleep(0.3)
        
        # Health monitor will restore Light 1 to correct color within 5 seconds
