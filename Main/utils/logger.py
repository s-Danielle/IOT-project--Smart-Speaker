"""
Timestamped logging utility for all actions
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


LOG_FILE_ENV = "SMART_SPEAKER_LOG_FILE"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("smart_speaker")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_file = os.environ.get(LOG_FILE_ENV)
    if log_file:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(logging.Formatter(
        "[%(asctime)s.%(msecs)03d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


_LOGGER = _build_logger()
_LEVELS = {
    "ERROR": logging.ERROR,
}


def log(message: str, category: str = "INFO"):
    """Write a timestamped log message."""
    _LOGGER.log(_LEVELS.get(category, logging.INFO), f"[{category}] {message}")


def log_action(action: str):
    """Log a user action"""
    log(action, "ACTION")


def log_state(state: str):
    """Log a state change"""
    log(state, "STATE")


def log_event(event: str):
    """Log an event"""
    log(event, "EVENT")


def log_sound(message: str):
    """Log sound playback"""
    log(message, "SOUND")


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

