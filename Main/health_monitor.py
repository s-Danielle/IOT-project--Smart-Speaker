#!/usr/bin/env python3
"""
Health Monitor Service - Controls Light 1 (Health LED)

Monitors:
- Internet connectivity (ping 8.8.8.8)
- Server status (GET localhost:5000/health)
- Hardware controller status (GET /debug/speaker/status)

Long Press Actions:
- Volume Up (5s): Reboot system
- Volume Down (5s): Restart all smart speaker services

Button Error Recovery:
- If button hardware fails repeatedly (20+ consecutive errors)
- LED blinks red for 10 seconds
- Health service restarts automatically to reinitialize buttons

LED Colors (R/G/B only):
- GREEN solid: All systems OK
- BLUE blinking: No server/internet (connectivity issues)
- RED blinking: No hardware (but internet/server OK)
- RED solid: Nothing works
- BLUE blinking: AP mode / Long press detected
"""

import sys
import os
import time
import subprocess

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware.leds import RGBLeds, Colors
from hardware.buttons import Buttons, ButtonID
from utils.hardware_health import HardwareHealthManager
from config.settings import (
    SERVER_HOST, 
    SERVER_PORT,
    LONG_PRESS_REBOOT_DURATION,
    LONG_PRESS_RESTART_SERVICES_DURATION,
    LOOP_INTERVAL,
)


class HealthMonitor:
    """Monitor system health and control Light 1"""
    
    LIGHT = 1  # Health uses Light 1
    CHECK_INTERVAL = 5  # seconds between checks
    SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
    
    # Services to restart on long press Volume Down
    SERVICES_TO_RESTART = [
        'smart_speaker',
        'smart_speaker_server',
    ]
    
    # Button error handling
    BUTTON_ERROR_BLINK_DURATION = 10.0  # Blink red for 10 seconds before restart
    
    def __init__(self):
        """Initialize health monitor"""
        self._leds = RGBLeds()
        self._buttons = Buttons()
        self._running = False
        self._last_state = None
        
        # Long press tracking - prevent re-triggering while held
        self._reboot_triggered = False
        self._restart_triggered = False
        
        # Button error tracking
        self._button_error_handling = False
        
        # Get reference to health manager for button health checks
        self._health_manager = HardwareHealthManager.get_instance()
        
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
            # Use /status endpoint - simple and fast
            req = urllib.request.Request(
                f"{self.SERVER_URL}/status",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status == 200
        except Exception as e:
            print(f"[HEALTH] Server check failed: {e}")
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
                    result = data.get('running', False) or data.get('status') == 'active'
                    if not result:
                        print(f"[HEALTH] Hardware check got: {data}")
                    return result
        except Exception as e:
            print(f"[HEALTH] Hardware check failed: {e}")
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
        
        # Set LED color based on state (R/G/B only)
        if internet and server and hardware:
            # All systems go - GREEN solid
            self._leds.set_light(self.LIGHT, Colors.GREEN)
        elif hardware and (not internet or not server):
            # Hardware OK but connectivity issues - BLUE blinking
            self._blink(Colors.BLUE)
        elif (internet or server) and not hardware:
            # Internet/server OK but no hardware - RED blinking
            self._blink(Colors.RED)
        else:
            # Nothing working - RED solid
            self._leds.set_light(self.LIGHT, Colors.RED)
    
    def _blink(self, color: tuple):
        """Single blink for status indication"""
        if int(time.time() * 2) % 2 == 0:
            self._leds.set_light(self.LIGHT, color)
        else:
            self._leds.off(self.LIGHT)
    
    def boot_animation(self):
        """Blue blink animation during startup"""
        print("[HEALTH] Boot animation...")
        for _ in range(3):
            self._leds.set_light(self.LIGHT, Colors.BLUE)
            time.sleep(0.3)
            self._leds.off(self.LIGHT)
            time.sleep(0.3)
    
    def _do_reboot(self):
        """Reboot the system"""
        print("[HEALTH] *** REBOOTING SYSTEM ***")
        # Visual feedback - rapid red blinks
        for _ in range(5):
            self._leds.set_light(self.LIGHT, Colors.RED)
            time.sleep(0.1)
            self._leds.off(self.LIGHT)
            time.sleep(0.1)
        
        try:
            subprocess.run(['sudo', 'reboot'], check=True)
        except Exception as e:
            print(f"[HEALTH] Reboot failed: {e}")
            # Error indication - solid red
            self._leds.set_light(self.LIGHT, Colors.RED)
    
    def _do_restart_services(self):
        """Restart all smart speaker services"""
        print("[HEALTH] *** RESTARTING SERVICES ***")
        # Visual feedback - rapid blue blinks
        for _ in range(5):
            self._leds.set_light(self.LIGHT, Colors.BLUE)
            time.sleep(0.1)
            self._leds.off(self.LIGHT)
            time.sleep(0.1)
        
        for service in self.SERVICES_TO_RESTART:
            try:
                print(f"[HEALTH] Restarting {service}...")
                result = subprocess.run(
                    ['sudo', 'systemctl', 'restart', service],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    print(f"[HEALTH] {service} restarted successfully")
                else:
                    print(f"[HEALTH] {service} restart failed: {result.stderr}")
            except Exception as e:
                print(f"[HEALTH] Failed to restart {service}: {e}")
        
        print("[HEALTH] Service restart complete")
    
    def _do_restart_health_service(self):
        """Restart the health monitor service itself"""
        print("[HEALTH] *** RESTARTING HEALTH SERVICE ***")
        try:
            # Use subprocess to restart ourselves - systemd will handle it
            subprocess.run(
                ['sudo', 'systemctl', 'restart', 'smart_speaker_health'],
                check=True
            )
        except Exception as e:
            print(f"[HEALTH] Failed to restart health service: {e}")
    
    def _handle_button_errors(self) -> bool:
        """
        Check for button hardware errors and handle recovery.
        
        If buttons are in failed state:
        - Blink red LED for 10 seconds
        - Restart the health service
        
        Returns:
            True if button errors are being handled (skip normal processing)
        """
        button_tracker = self._health_manager.get_tracker("buttons")
        if button_tracker is None:
            return False
        
        if not button_tracker.is_failed():
            return False
        
        # Don't re-enter error handling
        if self._button_error_handling:
            return True
        
        self._button_error_handling = True
        print("[HEALTH] Button hardware errors detected - starting recovery")
        
        # Blink red LED for 10 seconds
        blink_start = time.time()
        while time.time() - blink_start < self.BUTTON_ERROR_BLINK_DURATION:
            self._leds.set_light(self.LIGHT, Colors.RED)
            time.sleep(0.25)
            self._leds.off(self.LIGHT)
            time.sleep(0.25)
        
        print("[HEALTH] Red blink complete, restarting health service...")
        
        # Restart health service to reinitialize buttons
        self._do_restart_health_service()
        
        # If we get here, the restart failed - reset flag
        self._button_error_handling = False
        return True
    
    def _handle_buttons(self):
        """Handle long press on volume buttons"""
        self._buttons.update()
        
        # Volume Up - long press to reboot
        vol_up_duration = self._buttons.hold_duration(ButtonID.VOLUME_UP)
        if vol_up_duration >= LONG_PRESS_REBOOT_DURATION:
            if not self._reboot_triggered:
                self._reboot_triggered = True
                self._do_reboot()
        elif vol_up_duration > 0:
            # Show progress - blink blue faster as we approach threshold
            progress = vol_up_duration / LONG_PRESS_REBOOT_DURATION
            if progress > 0.5:
                # Blink to indicate long press is being detected
                if int(time.time() * 4) % 2 == 0:
                    self._leds.set_light(self.LIGHT, Colors.BLUE)
                else:
                    self._leds.off(self.LIGHT)
        else:
            # Button released - reset trigger
            self._reboot_triggered = False
        
        # Volume Down - long press to restart services
        vol_down_duration = self._buttons.hold_duration(ButtonID.VOLUME_DOWN)
        if vol_down_duration >= LONG_PRESS_RESTART_SERVICES_DURATION:
            if not self._restart_triggered:
                self._restart_triggered = True
                self._do_restart_services()
        elif vol_down_duration > 0:
            # Show progress - blink blue faster as we approach threshold
            progress = vol_down_duration / LONG_PRESS_RESTART_SERVICES_DURATION
            if progress > 0.5:
                # Blink to indicate long press is being detected
                if int(time.time() * 4) % 2 == 0:
                    self._leds.set_light(self.LIGHT, Colors.BLUE)
                else:
                    self._leds.off(self.LIGHT)
        else:
            # Button released - reset trigger
            self._restart_triggered = False
    
    def run(self):
        """Main loop"""
        print("[HEALTH] Starting health monitor service")
        print(f"[HEALTH] Long press Vol Up ({LONG_PRESS_REBOOT_DURATION}s) -> Reboot")
        print(f"[HEALTH] Long press Vol Down ({LONG_PRESS_RESTART_SERVICES_DURATION}s) -> Restart services")
        self._running = True
        
        # Boot animation
        self.boot_animation()
        
        # Track when we last did health check
        last_health_check = 0
        
        # Main monitoring loop - fast polling for buttons
        while self._running:
            try:
                current_time = time.time()
                
                # Check for button hardware errors first
                # If errors detected, handle recovery (blink red, restart service)
                if self._handle_button_errors():
                    time.sleep(LOOP_INTERVAL)
                    continue
                
                # Handle button presses (fast polling)
                self._handle_buttons()
                
                # Health checks at longer interval (only if not in a long press)
                vol_up_held = self._buttons.hold_duration(ButtonID.VOLUME_UP) > 0
                vol_down_held = self._buttons.hold_duration(ButtonID.VOLUME_DOWN) > 0
                
                if not vol_up_held and not vol_down_held:
                    if current_time - last_health_check >= self.CHECK_INTERVAL:
                        self.update_led()
                        last_health_check = current_time
                
            except Exception as e:
                print(f"[HEALTH] Error: {e}")
                self._leds.set_light(self.LIGHT, Colors.RED)
            
            # Fast polling interval for responsive button detection
            time.sleep(LOOP_INTERVAL)
        
        print("[HEALTH] Health monitor stopped")
    
    def stop(self):
        """Stop the monitor"""
        self._running = False
        self._leds.off(self.LIGHT)
        self._buttons.close()


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
