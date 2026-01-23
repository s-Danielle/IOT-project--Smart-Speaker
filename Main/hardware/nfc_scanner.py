"""
PN532 NFC reader (non-blocking read_uid)
"""

from typing import Optional

from config.settings import PN532_I2C_ADDRESS, NFC_TIMEOUT
from utils.logger import log_nfc, log_error
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


class NFCScanner:
    """PN532 NFC reader wrapper"""
    
    def __init__(self):
        """Initialize NFC reader"""
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
        
        if HAS_HARDWARE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self._pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
                self._pn532.SAM_configuration()
                fw = self._pn532.firmware_version
                log_nfc(f"PN532 initialized, firmware: {fw}")
            except Exception as e:
                log_error(f"Failed to initialize NFC reader: {e}")
                self._pn532 = None
        else:
            log_error("NFC Scanner not available - hardware libraries missing")
    
    def read_uid(self) -> Optional[str]:
        """
        Non-blocking read of NFC chip UID. 
        Returns UID string if chip present, None otherwise.
        Errors are expected when no chip is present, so we use health manager
        for rate-limited, filtered error logging.
        """
        if self._pn532 is None:
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
            
            # Check for persistent failure (but NFC has high threshold)
            if self._health.is_failed():
                self._health.log_failure_once("NFC reader disabled due to repeated hardware errors")
                self._pn532 = None
            
            return None
    
    def close(self):
        """Clean up NFC reader resources"""
        log_nfc("NFC Scanner closed")
        self._pn532 = None
