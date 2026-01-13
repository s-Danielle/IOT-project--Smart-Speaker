#!/usr/bin/env python3
"""
Entry point: create controller + run loop

Smart Speaker - Raspberry Pi IoT Project
=========================================

Controls:
- Play/Pause button: Toggle playback
- Record button: Hold 3s → release to start recording, short press to save
- Stop button: Short press = stop/cancel, Long press (5s) = clear chip

States:
1. IDLE_NO_CHIP - No chip loaded
2. IDLE_CHIP_LOADED - Chip loaded, ready to play
3. PLAYING - Music playing
4. PAUSED - Music paused  
5. RECORDING - Recording in progress
"""

import sys
import os

# Add Main directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.controller import Controller
from hardware.health import HealthChecker
from utils.logger import log, log_success, log_error, log_event
from utils.setup_check import check_and_install_dependencies, check_mopidy_connection
from server import start_server


def print_banner():
    """Print startup banner"""
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║   🔊 SMART SPEAKER - Raspberry Pi IoT Project 🔊          ║")
    print("║                                                            ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print("║  Controls:                                                 ║")
    print("║    • Play/Pause: Toggle playback                          ║")
    print("║    • Record: Hold 3s → release → short press to save      ║")
    print("║    • Stop: Short = stop, Long (5s) = clear chip           ║")
    print("║                                                            ║")
    print("║  Scan NFC chip to load music!                             ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()


def run_health_check():
    """Run optional health check on startup"""
    checker = HealthChecker()
    results = checker.run_all()
    
    # Count failures
    failures = [r for r in results if not r.healthy]
    if failures:
        log_error(f"Warning: {len(failures)} component(s) failed health check")
        log("Continuing anyway - some features may not work")
    else:
        log_success("All systems operational!")
    
    return len(failures) == 0


def main():
    """Initialize and run the main controller loop."""
    print_banner()
    
    # Check and install dependencies on startup
    if "--skip-setup" not in sys.argv:
        log("Checking dependencies...")
        deps_ok = check_and_install_dependencies()
        if not deps_ok:
            log_event("⚠️  Some dependencies are missing - some features may not work")
        check_mopidy_connection()
        print()
    
    # Optional: Run health check
    if "--health-check" in sys.argv or "-h" in sys.argv:
        all_healthy = run_health_check()
        if not all_healthy and "--strict" in sys.argv:
            log_error("Strict mode: exiting due to health check failures")
            sys.exit(1)
    
    # Start HTTP server in background thread
    log("Starting HTTP server...")
    server_thread = start_server(port=8080)
    # Give server a moment to start
    import time
    time.sleep(0.5)
    
    # Create and run controller
    try:
        controller = Controller()
        controller.run()
    except Exception as e:
        log_error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
