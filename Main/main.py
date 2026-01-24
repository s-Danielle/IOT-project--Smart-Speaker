#!/home/iot-proj/IOT-project--Smart-Speaker/venv/bin/python
"""
Smart Speaker Hardware Controller

This is the hardware controller entry point. It runs the main event loop
that handles NFC scanning, button presses, LED feedback, and audio playback.

NOTE: This does NOT start the HTTP server. The server runs as a separate
service (smart_speaker_server.service). This controller communicates with
the server via HTTP to fetch chip data and parental controls.

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
import time

from core.controller import Controller
from hardware.health import HealthChecker
from utils.logger import log, log_success, log_error, log_event
from utils.server_client import check_server_health


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


def wait_for_server(max_attempts=30, delay=1.0):
    """Wait for the API server to be available.
    
    Args:
        max_attempts: Maximum number of connection attempts
        delay: Delay between attempts in seconds
        
    Returns:
        True if server is available, False if timed out
    """
    log("Waiting for API server...")
    for attempt in range(max_attempts):
        if check_server_health():
            log_success("API server is available")
            return True
        if attempt < max_attempts - 1:
            time.sleep(delay)
    
    log_error(f"API server not available after {max_attempts} attempts")
    return False


def main():
    log("=" * 60)
    log("SMART SPEAKER HARDWARE CONTROLLER")
    log("=" * 60)
    
    # Optional: Run health check
    if "--health-check" in sys.argv:
        all_healthy = run_health_check()
        if not all_healthy and "--strict" in sys.argv:
            log_error("Strict mode: exiting due to health check failures")
            sys.exit(1)
    
    # Wait for the API server to be available
    # (Server runs as separate service: smart_speaker_server.service)
    if not wait_for_server():
        log_error("Cannot start without API server. Is smart_speaker_server.service running?")
        sys.exit(1)
    
    # Create and run controller
    log("Starting hardware controller...")
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
