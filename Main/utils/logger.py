"""
Timestamped logging utility for all actions
"""

from datetime import datetime


def log(message: str, category: str = "INFO"):
    """Print a timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [{category}] {message}")


def log_action(action: str):
    """Log a user action"""
    log(action, "ACTION")


def log_state(state: str):
    """Log a state change"""
    log(state, "STATE")


def log_event(event: str):
    """Log an event"""
    log(event, "EVENT")


def log_sound(sound: str):
    """Log sound playback"""
    log(f"🔊 Playing: {sound}", "SOUND")


def log_nfc(message: str):
    """Log NFC events"""
    log(message, "NFC")


def log_button(message: str):
    """Log button events"""
    log(message, "BUTTON")


def log_audio(message: str):
    """Log audio player events"""
    log(message, "AUDIO")


def log_recording(message: str):
    """Log recording events"""
    log(message, "RECORD")


def log_error(message: str):
    """Log errors"""
    log(f"❌ {message}", "ERROR")


def log_success(message: str):
    """Log success"""
    log(f"✅ {message}", "SUCCESS")

