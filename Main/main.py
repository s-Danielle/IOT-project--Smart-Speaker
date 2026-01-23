#!/home/iot-proj/IOT-project--Smart-Speaker/venv/bin/python
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
import time


from core.controller import Controller
from hardware.health import HealthChecker
from config.settings import SERVER_PORT
from utils.logger import log, log_success, log_error, log_event
from server import start_server



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
    # Optional: Run health check
    if "--health-check" in sys.argv or "-h" in sys.argv:
        all_healthy = run_health_check()
        if not all_healthy and "--strict" in sys.argv:
            log_error("Strict mode: exiting due to health check failures")
            sys.exit(1)
    
    # Start HTTP server in background thread
    log("Starting HTTP server...")
    server_thread = start_server(port=SERVER_PORT)
    # Give server a moment to start
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
    finally:
        # the thread is running as a daemon, but it won't hurt to join it
        log("Shutting down HTTP server...")
        server_thread.stop()  # Gracefully stop the server
        server_thread.join()  # Wait for thread to finish
        log("HTTP server shut down")


if __name__ == "__main__":
    main()
