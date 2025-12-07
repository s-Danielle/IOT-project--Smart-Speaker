"""
Pure action handlers (play, stop, record…)
These update state and call I/O, but contain no hardware code directly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state import DeviceState, State, ChipData
from utils.logger import log_action, log_state


def action_load_chip(device_state: DeviceState, chip_data: dict, audio_player, ui) -> DeviceState:
    """Load a chip and transition to IDLE_CHIP_LOADED"""
    # Stop any current playback (whether playing or paused)
    if device_state.state in (State.PLAYING, State.PAUSED):
        audio_player.stop()
    
    # Create chip data
    chip = ChipData(
        uid=chip_data.get('uid', ''),
        name=chip_data.get('name', 'Unknown'),
        uri=chip_data.get('uri', ''),
        metadata=chip_data
    )
    
    log_action(f"Loading chip: {chip.name}")
    device_state.loaded_chip = chip
    device_state.state = State.IDLE_CHIP_LOADED
    device_state.was_playing_before_recording = False
    
    ui.on_chip_loaded()
    log_state(f"→ {device_state.state}")
    return device_state


def action_play(device_state: DeviceState, audio_player, ui) -> DeviceState:
    """Start playback from loaded chip"""
    if device_state.loaded_chip is None:
        log_action("Cannot play: no chip loaded")
        ui.on_blocked_action()
        return device_state
    
    log_action(f"Starting playback: {device_state.loaded_chip.name}")
    audio_player.play_uri(device_state.loaded_chip.uri)
    device_state.state = State.PLAYING
    
    ui.on_play()
    log_state(f"→ {device_state.state}")
    return device_state


def action_resume(device_state: DeviceState, audio_player, ui) -> DeviceState:
    """Resume paused playback"""
    log_action("Resuming playback")
    audio_player.resume()
    device_state.state = State.PLAYING
    
    ui.on_play()
    log_state(f"→ {device_state.state}")
    return device_state


def action_pause(device_state: DeviceState, audio_player, ui) -> DeviceState:
    """Pause playback"""
    log_action("Pausing playback")
    audio_player.pause()
    device_state.state = State.PAUSED
    
    ui.on_pause()
    log_state(f"→ {device_state.state}")
    return device_state


def action_stop(device_state: DeviceState, audio_player, ui) -> DeviceState:
    """Stop playback, return to IDLE_CHIP_LOADED"""
    log_action("Stopping playback")
    audio_player.stop()
    device_state.state = State.IDLE_CHIP_LOADED
    
    ui.on_stop()
    log_state(f"→ {device_state.state}")
    return device_state


def action_clear_chip(device_state: DeviceState, audio_player, ui) -> DeviceState:
    """Clear loaded chip, return to IDLE_NO_CHIP"""
    log_action("Clearing chip")
    audio_player.stop()
    device_state.loaded_chip = None
    device_state.state = State.IDLE_NO_CHIP
    device_state.was_playing_before_recording = False
    
    ui.on_clear_chip()
    log_state(f"→ {device_state.state}")
    return device_state


def action_start_recording(device_state: DeviceState, audio_player, recorder, ui) -> DeviceState:
    """Start recording (chip must be loaded)"""
    if device_state.loaded_chip is None:
        log_action("Cannot record: no chip loaded")
        ui.on_blocked_action()
        return device_state
    
    # Remember if we had active music context (PLAYING or PAUSED)
    # After recording, we return to PAUSED if music was active, else IDLE_CHIP_LOADED
    device_state.was_playing_before_recording = (device_state.state in (State.PLAYING, State.PAUSED))
    device_state.previous_state = device_state.state
    
    # Pause music if playing
    if device_state.state == State.PLAYING:
        log_action("Pausing music for recording")
        audio_player.pause()
    
    log_action(f"Starting recording for chip: {device_state.loaded_chip.name}")
    recorder.start(device_state.loaded_chip.name)
    device_state.state = State.RECORDING
    
    ui.on_record_start()
    log_state(f"→ {device_state.state}")
    return device_state


def action_save_recording(device_state: DeviceState, recorder, ui) -> DeviceState:
    """Save current recording"""
    log_action("Saving recording")
    saved_path = recorder.stop()
    
    # Return to appropriate state
    if device_state.was_playing_before_recording:
        device_state.state = State.PAUSED
    else:
        device_state.state = State.IDLE_CHIP_LOADED
    
    device_state.was_playing_before_recording = False
    
    ui.on_record_saved()
    log_state(f"→ {device_state.state} (recording saved: {saved_path})")
    return device_state


def action_cancel_recording(device_state: DeviceState, recorder, ui) -> DeviceState:
    """Cancel recording without saving"""
    log_action("Canceling recording")
    recorder.cancel()
    
    # Return to appropriate state  
    if device_state.was_playing_before_recording:
        device_state.state = State.PAUSED
    else:
        device_state.state = State.IDLE_CHIP_LOADED
    
    device_state.was_playing_before_recording = False
    
    ui.on_record_canceled()
    log_state(f"→ {device_state.state}")
    return device_state


def action_cancel_recording_and_clear(device_state: DeviceState, recorder, audio_player, ui) -> DeviceState:
    """Cancel recording and clear chip"""
    log_action("Canceling recording and clearing chip")
    recorder.cancel()
    audio_player.stop()
    
    device_state.loaded_chip = None
    device_state.state = State.IDLE_NO_CHIP
    device_state.was_playing_before_recording = False
    
    ui.on_clear_chip()
    log_state(f"→ {device_state.state}")
    return device_state
