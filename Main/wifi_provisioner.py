#!/usr/bin/env python3
"""
WiFi Provisioning Service (NetworkManager-based)

Boot-time state machine (no HTTP server, binds no ports):
- Waits for NetworkManager to auto-connect on boot
- If no connection after timeout, starts AP mode (SmartSpeaker-Setup)
  and monitors until the Pi is connected to a real network
- Credential intake and AP teardown are handled by the main server's
  captive portal (Main/server.py, /wifi-setup on port 8080)
- LED feedback via Light 1

This service uses the shared WiFiManager from hardware/wifi_manager.py
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware.wifi_manager import WiFiManager, AP_SSID, AP_IP, WEB_PORT

CONNECT_TIMEOUT = 30  # Seconds to wait for auto-connect
AP_POLL_INTERVAL = 3  # Seconds between connection checks while in AP mode


class LEDController:
    """Simplified LED control for provisioning - uses Light 1"""
    LIGHT = 1
    
    def __init__(self):
        try:
            from hardware.leds import RGBLeds, Colors
            self.leds = RGBLeds()
            self.Colors = Colors
            self._enabled = True
        except Exception:
            self._enabled = False
        self._pulsing = False
    
    def ap_mode(self):
        """AP mode - blue pulsing"""
        if self._enabled:
            self._pulse(self.Colors.BLUE)
    
    def connecting(self):
        """Waiting for connection - yellow pulsing"""
        if self._enabled:
            self._pulse(self.Colors.YELLOW)
    
    def connected(self):
        """Connected - solid green"""
        if self._enabled:
            self.stop_pulse()
            self.leds.set_light(self.LIGHT, self.Colors.GREEN)
    
    def failed(self):
        """Connection failed - red triple flash"""
        if self._enabled:
            self.stop_pulse()
            for _ in range(3):
                self.leds.set_light(self.LIGHT, self.Colors.RED)
                time.sleep(0.2)
                self.leds.off(self.LIGHT)
                time.sleep(0.2)
    
    def _pulse(self, color):
        """Start pulsing LED with given color"""
        self.stop_pulse()
        self._pulsing = True
        def do_pulse():
            while self._pulsing:
                self.leds.set_light(self.LIGHT, color)
                time.sleep(0.5)
                self.leds.off(self.LIGHT)
                time.sleep(0.5)
        threading.Thread(target=do_pulse, daemon=True).start()
    
    def stop_pulse(self):
        """Stop pulsing"""
        self._pulsing = False
        time.sleep(0.1)


class WiFiProvisioner:
    """Main WiFi provisioning orchestrator"""
    
    def __init__(self):
        self.led = LEDController()
    
    def run(self):
        """Main provisioning flow - wait for WiFi, fallback to AP mode"""
        print("[WiFi] Waiting for NetworkManager to connect...")
        self.led.connecting()
        
        # Give NetworkManager time to auto-connect to known networks
        for i in range(CONNECT_TIMEOUT):
            if WiFiManager.is_connected():
                ssid = WiFiManager.get_current_ssid()
                print(f"[WiFi] Connected to {ssid}")
                self.led.connected()
                return  # Exit - normal operation can proceed
            time.sleep(1)
            if i % 5 == 0:
                print(f"[WiFi] Waiting... ({CONNECT_TIMEOUT - i}s remaining)")
        
        # No connection after timeout - start AP mode and wait for the
        # main server's captive portal to provision credentials
        print("[WiFi] No connection, starting AP mode...")
        self.led.ap_mode()
        WiFiManager.start_ap()
        print(f"[WiFi] AP '{AP_SSID}' active")
        print(f"[WiFi] Setup portal at http://{AP_IP}:{WEB_PORT}/wifi-setup "
              "(served by the main server)")
        self._wait_for_provisioning()
    
    def _wait_for_provisioning(self):
        """Monitor until the Pi is connected to a real network (not the AP).
        
        The main server handles credential intake and AP teardown; this loop
        just watches for the result. Requires two consecutive positive checks
        so a transient state mid-connection-attempt isn't mistaken for success.
        """
        consecutive = 0
        while True:
            # is_connected() is False while the AP profile is the active connection
            if WiFiManager.is_connected():
                consecutive += 1
                if consecutive >= 2:
                    ssid = WiFiManager.get_current_ssid()
                    print(f"[WiFi] Provisioned - connected to {ssid}")
                    self.led.connected()
                    return
            else:
                consecutive = 0
            time.sleep(AP_POLL_INTERVAL)


if __name__ == '__main__':
    WiFiProvisioner().run()
