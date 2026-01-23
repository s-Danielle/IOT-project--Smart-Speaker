"""
Wrap health_check: run startup diagnostics
"""

from dataclasses import dataclass
from typing import List


from utils.logger import log, log_success, log_error


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    component: str
    healthy: bool
    message: str = ""


class HealthChecker:
    """Run startup diagnostics on hardware components"""
    
    def __init__(self):
        """Initialize health checker"""
        log("Starting health checks...")
    
    def check_nfc(self) -> HealthCheckResult:
        """Check NFC reader health"""
        try:
            import board
            import busio
            from adafruit_pn532.i2c import PN532_I2C
            from config.settings import PN532_I2C_ADDRESS
            
            i2c = busio.I2C(board.SCL, board.SDA)
            pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
            fw = pn532.firmware_version
            return HealthCheckResult("NFC", True, f"PN532 firmware: {fw}")
        except Exception as e:
            return HealthCheckResult("NFC", False, str(e))
    
    def check_buttons(self) -> HealthCheckResult:
        """Check buttons health"""
        try:
            from smbus2 import SMBus
            from config.settings import PCF8574_ADDRESS
            
            bus = SMBus(1)
            value = bus.read_byte(PCF8574_ADDRESS)
            bus.close()
            return HealthCheckResult("Buttons", True, f"PCF8574 read: {hex(value)}")
        except Exception as e:
            return HealthCheckResult("Buttons", False, str(e))
    
    def check_audio(self) -> HealthCheckResult:
        """Check audio system health"""
        try:
            import subprocess
            result = subprocess.run(["which", "arecord"], capture_output=True)
            if result.returncode == 0:
                return HealthCheckResult("Audio", True, "arecord available")
            return HealthCheckResult("Audio", False, "arecord not found")
        except Exception as e:
            return HealthCheckResult("Audio", False, str(e))
    
    def check_mopidy(self) -> HealthCheckResult:
        """Check Mopidy connection via MPD protocol"""
        try:
            from mpd import MPDClient
            from mpd.base import ConnectionError as MPDConnectionError
            from config.settings import MOPIDY_HOST, MPD_PORT
            
            client = MPDClient()
            client.timeout = 2
            client.connect(MOPIDY_HOST, MPD_PORT)
            version = client.mpd_version
            client.disconnect()
            return HealthCheckResult("Mopidy", True, f"MPD version: {version}")
        except MPDConnectionError as e:
            return HealthCheckResult("Mopidy", False, f"Connection failed: {e}")
        except Exception as e:
            return HealthCheckResult("Mopidy", False, str(e))
    
    def run_all(self) -> List[HealthCheckResult]:
        """Run all health checks"""
        results = [
            self.check_nfc(),
            self.check_buttons(),
            self.check_audio(),
            self.check_mopidy(),
        ]
        
        print("\n" + "=" * 50)
        print("HEALTH CHECK RESULTS")
        print("=" * 50)
        
        for result in results:
            status = "✅" if result.healthy else "❌"
            print(f"{status} {result.component}: {result.message}")
        
        print("=" * 50 + "\n")
        
        healthy_count = sum(1 for r in results if r.healthy)
        if healthy_count == len(results):
            log_success(f"All {len(results)} health checks passed!")
        else:
            log_error(f"{len(results) - healthy_count}/{len(results)} health checks failed")
        
        return results
