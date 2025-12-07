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
    CLEAR_CHIP_HOLD_DURATION
)
from utils.logger import log, log_state, log_event, log_error, log_button


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
        
        # Track stop button long-press to prevent repeated execution
        self._stop_long_press_triggered = False
        
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
    
    # =========================================================================
    # NFC HANDLING
    # =========================================================================
    
    def _handle_nfc(self):
        """Handle NFC chip scans based on current state"""
        uid = self._nfc.read_uid()
        
        if uid is None:
            return
        
        state = self.device_state.state
        
        # RECORDING: Ignore all NFC scans
        if state == State.RECORDING:
            log_event(f"NFC scan ignored (recording in progress)")
            self._ui.on_blocked_action()
            return
        
        # Look up chip data
        chip_data = self._chip_store.lookup(uid)
        
        if chip_data is None:
            log_event(f"Unknown chip scanned: {uid}")
            self._ui.on_error()
            return
        
        # Check if same chip is already loaded
        if self.device_state.loaded_chip and self.device_state.loaded_chip.uid == uid:
            log_event("Same chip scanned - no action")
            self._ui.on_same_chip_scanned()
            return
        
        # Different chip or no chip loaded - load the new chip
        # If playing, this stops playback and loads new chip
        self.device_state = actions.action_load_chip(
            self.device_state, chip_data, self._audio, self._ui
        )
    
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
        """Handle Play/Pause button logic"""
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
        - Hold 3s to arm recording
        - Release after armed to start recording
        - Short press while recording to save
        """
        # IDLE_NO_CHIP: No effect
        if state == State.IDLE_NO_CHIP:
            if self._buttons.just_released(ButtonID.RECORD):
                log_event("Record blocked - no chip loaded")
                self._ui.on_blocked_action()
            return
        
        # RECORDING: Short press saves recording
        if state == State.RECORDING:
            if self._buttons.just_released(ButtonID.RECORD):
                log_button("Record button pressed - saving recording")
                self.device_state = actions.action_save_recording(
                    self.device_state, self._recorder, self._ui
                )
            return
        
        # Other states: Track hold duration for arming
        if self._buttons.is_pressed(ButtonID.RECORD):
            hold_time = self._buttons.hold_duration(ButtonID.RECORD)
            
            # Check if we just hit the 3s threshold
            if hold_time >= RECORD_HOLD_DURATION and not self._record_armed:
                self._record_armed = True
                log_button(f"🎙️ Record ARMED (held {hold_time:.1f}s) - release to start recording")
        
        # On release: start recording if armed
        if self._buttons.just_released(ButtonID.RECORD):
            if self._record_armed:
                self._record_armed = False
                log_button("Record button released - starting recording")
                self.device_state = actions.action_start_recording(
                    self.device_state, self._audio, self._recorder, self._ui
                )
            else:
                hold_time = self._buttons.get_release_duration(ButtonID.RECORD)
                log_button(f"Record released too early ({hold_time:.1f}s < {RECORD_HOLD_DURATION}s)")
        
        # Reset armed state if button released without triggering
        if not self._buttons.is_pressed(ButtonID.RECORD):
            self._record_armed = False
    
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
                        self.device_state, self._audio, self._ui
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
            
            # RECORDING: Cancel recording (no save)
            if state == State.RECORDING:
                self.device_state = actions.action_cancel_recording(
                    self.device_state, self._recorder, self._ui
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
