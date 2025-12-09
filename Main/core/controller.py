"""
Main loop: polls inputs, updates state
Implements the full state machine from States.txt
"""

import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    PLAY_LATEST_HOLD_DURATION
)
from utils.logger import log, log_state, log_event, log_error, log_button
from typing import Optional


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
        # Alternative: Use local:file: URI if Mopidy-Local is configured
        # This requires the recordings directory to be in Mopidy's media_dir
        # For now, we'll use file:// and let Mopidy handle it
        
        # Unix/Linux: file:///absolute/path (three slashes for absolute)
        file_uri = f"file://{abs_path}"
        
        
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
        
        # Look up chip data
        chip_data = self._chip_store.lookup(uid)
        
        if chip_data is None:
            log_event(f"Unknown chip scanned: {uid}")
            self._ui.on_error()
            self._last_nfc_uid = uid
            return
        
        # Check if same chip is already loaded
        if self.device_state.loaded_chip and self.device_state.loaded_chip.uid == uid:
            log_event("Same chip scanned - no action")
            self._ui.on_same_chip_scanned()
            self._last_nfc_uid = uid
            return
        
        # Different chip or no chip loaded - load the new chip
        # If playing, this stops playback and loads new chip
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
            self.device_state = actions.action_play(
                self.device_state, self._audio, self._ui
            )
            return
        
        # PLAYING: Pause
        if state == State.PLAYING:
            self.device_state = actions.action_pause(
                self.device_state, self._audio, self._ui
            )
            return
        
        # PAUSED: Resume
        if state == State.PAUSED:
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
        
        # Check for long press (5s) to clear chip
        if self._buttons.is_pressed(ButtonID.STOP):
            hold_time = self._buttons.hold_duration(ButtonID.STOP)
            
            # Only trigger once per long press (prevent repeated execution)
            if hold_time >= CLEAR_CHIP_HOLD_DURATION and not self._stop_long_press_triggered:
                self._stop_long_press_triggered = True
                log_button(f"🔄 Stop held {hold_time:.1f}s - CLEARING CHIP")
                
                if state == State.RECORDING:
                    self.device_state = actions.action_cancel_recording_and_clear(
                        self.device_state, self._recorder, self._audio, self._ui
                    )
                else:
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
                self.device_state = actions.action_stop(
                    self.device_state, self._audio, self._ui
                )
                return
