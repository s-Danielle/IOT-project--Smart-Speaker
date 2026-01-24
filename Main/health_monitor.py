#!/usr/bin/env python3
"""
Health Monitor Service - Controls Light 1 (Device Health LED)

Monitors:
- Internet connectivity (ping 8.8.8.8)
- Server status (GET localhost:5000/health)
- Hardware controller status (GET /debug/speaker/status)

LED Colors:
- Green: All systems OK (internet + server + hardware)
- Yellow: Server + Hardware OK, no internet
- Cyan: Hardware only (server down)
- Magenta: Server only (hardware down)
- Red: All down
- White blink: Booting
"""

import sys
import os
import time
import subprocess
import threading

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware.leds import RGBLeds, Colors


class HealthMonitor:
    """Monitor system health and control Light 1"""
    
    LIGHT = 1  # Health uses Light 1
    CHECK_INTERVAL = 5  # seconds between checks
    SERVER_URL = "http://localhost:5000"
    
    def __init__(self):
        """Initialize health monitor"""
        self._leds = RGBLeds()
        self._running = False
        self._last_state = None
        print("[HEALTH] Health monitor initialized")
    
    def check_internet(self) -> bool:
        """Check internet connectivity by pinging Google DNS"""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', '8.8.8.8'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def check_server(self) -> bool:
        """Check if API server is responding"""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.SERVER_URL}/health",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status == 200
        except Exception:
            return False
    
    def check_hardware(self) -> bool:
        """Check if hardware controller (Main) is running"""
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                f"{self.SERVER_URL}/debug/speaker/status",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    # Server returns {"status": "active", "running": true}
                    return data.get('running', False) or data.get('status') == 'active'
        except Exception:
            pass
        return False
    
    def update_led(self):
        """Check all systems and update LED accordingly"""
        internet = self.check_internet()
        server = self.check_server()
        hardware = self.check_hardware()
        
        # Determine state
        state = (internet, server, hardware)
        
        # Only log if state changed
        if state != self._last_state:
            print(f"[HEALTH] Internet={internet}, Server={server}, Hardware={hardware}")
            self._last_state = state
        
        # Set LED color based on state
        if internet and server and hardware:
            # All systems go - GREEN
            self._leds.set_light(self.LIGHT, Colors.GREEN)
        elif server and hardware and not internet:
            # No internet but local services OK - YELLOW
            self._leds.set_light(self.LIGHT, Colors.YELLOW)
        elif hardware and not server:
            # Hardware running but server down - CYAN
            self._leds.set_light(self.LIGHT, Colors.CYAN)
        elif server and not hardware:
            # Server running but hardware down - MAGENTA
            self._leds.set_light(self.LIGHT, Colors.MAGENTA)
        else:
            # Critical - nothing working - RED
            self._leds.set_light(self.LIGHT, Colors.RED)
    
    def boot_animation(self):
        """White blink animation during startup"""
        print("[HEALTH] Boot animation...")
        for _ in range(3):
            self._leds.set_light(self.LIGHT, Colors.WHITE)
            time.sleep(0.3)
            self._leds.off(self.LIGHT)
            time.sleep(0.3)
    
    def run(self):
        """Main loop"""
        print("[HEALTH] Starting health monitor service")
        self._running = True
        
        # Boot animation
        self.boot_animation()
        
        # Main monitoring loop
        while self._running:
            try:
                self.update_led()
            except Exception as e:
                print(f"[HEALTH] Error: {e}")
                self._leds.set_light(self.LIGHT, Colors.RED)
            
            time.sleep(self.CHECK_INTERVAL)
        
        print("[HEALTH] Health monitor stopped")
    
    def stop(self):
        """Stop the monitor"""
        self._running = False
        self._leds.off(self.LIGHT)


def main():
    """Entry point"""
    monitor = HealthMonitor()
    
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n[HEALTH] Shutdown requested...")
    finally:
        monitor.stop()
        print("[HEALTH] Goodbye!")


if __name__ == '__main__':
    main()
