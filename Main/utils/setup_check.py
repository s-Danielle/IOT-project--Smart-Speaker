"""
Check and install dependencies on startup
"""

import sys
import subprocess
from utils.logger import log, log_error, log_success, log_event


def check_and_install_dependencies():
    """Check if required dependencies are installed, offer to install if missing"""
    missing = []
    
    # Check requests (required for Mopidy)
    try:
        import requests
        log_success("✅ requests library available")
    except ImportError:
        missing.append("requests")
        log_error("❌ requests library not found (required for Mopidy)")
    
    # Check hardware libraries (required for full functionality)
    try:
        import board
        import busio
        from adafruit_pn532.i2c import PN532_I2C
        log_success("✅ NFC hardware libraries available")
    except ImportError:
        log_error("❌ NFC hardware libraries not found (required for NFC scanning)")
        missing.append("adafruit-circuitpython-pn532")
    
    try:
        from smbus2 import SMBus
        log_success("✅ Button hardware libraries available")
    except ImportError:
        log_error("❌ Button hardware libraries not found (required for button input)")
        missing.append("smbus2")
    
    # If critical dependencies missing, offer to install
    if missing:
        print("\n" + "=" * 60)
        print("MISSING DEPENDENCIES DETECTED")
        print("=" * 60)
        print(f"Missing: {', '.join(missing)}")
        print("\nTo install dependencies, run:")
        print("  pip3 install -r requirements.txt")
        print("  OR")
        print("  ./setup.sh")
        print("\nOr install manually:")
        for dep in missing:
            print(f"  pip3 install {dep}")
        print("=" * 60 + "\n")
        
        # Try to auto-install if in interactive mode
        if sys.stdin.isatty():
            try:
                response = input("Attempt to install missing dependencies now? (y/n): ").strip().lower()
                if response == 'y':
                    log_event("Installing missing dependencies...")
                    for dep in missing:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
                    log_success("Dependencies installed! Restart the application.")
                    return True
            except (KeyboardInterrupt, EOFError):
                pass
            except Exception as e:
                log_error(f"Failed to install dependencies: {e}")
        
        return False
    
    return True


def check_mopidy_connection():
    """Check if Mopidy is accessible"""
    try:
        import requests
        response = requests.post(
            "http://localhost:6680/mopidy/rpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "core.get_version"},
            timeout=2
        )
        data = response.json()
        version = data.get("result", "unknown")
        log_success(f"✅ Mopidy connected (version: {version})")
        return True
    except ImportError:
        log_error("❌ Cannot check Mopidy (requests not installed)")
        return False
    except Exception as e:
        log_error(f"❌ Mopidy not accessible at localhost:6680: {e}")
        log_error("Make sure Mopidy is running: sudo systemctl start mopidy")
        return False

