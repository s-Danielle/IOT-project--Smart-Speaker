"""
PN532 NFC reader (non-blocking read_uid)
"""

import time
from typing import Optional

from config.settings import PN532_I2C_ADDRESS, NFC_TIMEOUT
from utils.logger import log_nfc, log_error, log
from utils.hardware_health import HardwareHealthManager

# Hardware imports - will fail gracefully on non-Pi systems
try:
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    log_error("NFC hardware libraries not available - NFC scanning will not work")


# Retry settings for NFC initialization
NFC_INIT_RETRY_DELAY = 5  # seconds between retries
NFC_INIT_MAX_RETRIES = None  # None = retry forever


class NFCScanner:
    """PN532 NFC reader wrapper"""
    
    def __init__(self):
        """Initialize NFC reader with retry until success."""
        self._pn532 = None
        self._last_uid: Optional[str] = None
        
        # Register with health manager for error throttling
        self._health = HardwareHealthManager.get_instance().register(
            "nfc",
            expected_errors=[
                "Input/output error",
                "Response frame preamble does not contain 0x00FF",
                "Did not receive expected ACK from PN532",
                "Timeout waiting for",
            ],
            log_interval=5.0,
            failure_threshold=50  # NFC has more transient errors, higher threshold
        )
        
        if not HAS_HARDWARE:
            log_error("NFC hardware libraries not available - cannot start without NFC")
            raise RuntimeError("NFC hardware libraries not available")
        
        # Keep retrying until NFC initializes - service is useless without it
        self._init_with_retry()
    
    def _init_with_retry(self):
        """Initialize NFC with retry loop until success."""
        attempt = 0
        while True:
            attempt += 1
            try:
                log_nfc(f"Initializing NFC reader (attempt {attempt})...")
                i2c = busio.I2C(board.SCL, board.SDA)
                self._pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
                self._pn532.SAM_configuration()
                fw = self._pn532.firmware_version
                log_nfc(f"PN532 initialized successfully, firmware: {fw}")
                return  # Success!
                
            except Exception as e:
                log_error(f"NFC init failed (attempt {attempt}): {e}")
                self._pn532 = None
                
                # Check if we should keep retrying
                if NFC_INIT_MAX_RETRIES is not None and attempt >= NFC_INIT_MAX_RETRIES:
                    log_error(f"NFC init failed after {attempt} attempts - giving up")
                    raise RuntimeError(f"Failed to initialize NFC after {attempt} attempts")
                
                log(f"[NFC] Retrying in {NFC_INIT_RETRY_DELAY}s...")
                time.sleep(NFC_INIT_RETRY_DELAY)
    
    def read_uid(self) -> Optional[str]:
        """
        Non-blocking read of NFC chip UID. 
        Returns UID string if chip present, None otherwise.
        Errors are expected when no chip is present, so we use health manager
        for rate-limited, filtered error logging.
        """
        if self._pn532 is None:
            # Try to reinitialize if NFC was lost
            self._try_reinit()
            return None
        
        try:
            uid = self._pn532.read_passive_target(timeout=NFC_TIMEOUT)
            if uid is not None:
                # Convert to uppercase hex string (e.g., "9903EEB9")
                uid_str = ''.join(f'{b:02X}' for b in uid)
                self._health.report_success()
                return uid_str
            return None
        except Exception as e:
            # Use health manager for rate-limited, filtered error logging
            if self._health.report_error(e):
                log_error(f"NFC read error: {e}")
            
            # Check for persistent failure - try to reinitialize
            if self._health.is_failed():
                log_error("NFC reader failed - attempting to reinitialize...")
                self._pn532 = None
                self._health.reset()  # Reset health tracking for fresh start
                self._try_reinit()
            
            return None
    
    def _try_reinit(self):
        """Try to reinitialize NFC (non-blocking, single attempt)."""
        if self._pn532 is not None:
            return  # Already initialized
        
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
            self._pn532.SAM_configuration()
            fw = self._pn532.firmware_version
            log_nfc(f"NFC reinitialized successfully, firmware: {fw}")
        except Exception as e:
            # Silent fail - will try again next read
            self._pn532 = None
    
    def close(self):
        """Clean up NFC reader resources"""
        log_nfc("NFC Scanner closed")
        self._pn532 = None
