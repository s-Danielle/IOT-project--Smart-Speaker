#!/usr/bin/env python3
"""
WiFi Provisioning Service (NetworkManager-based)

Boot-time state machine (no HTTP server, binds no ports):
- Waits for NetworkManager to auto-connect on boot
- If no connection after timeout, starts AP mode (SmartSpeaker-Setup)
  and monitors until the Pi is connected to a real network
- While in AP mode, every AP_RETRY_INTERVAL seconds, if nobody is using the
  hotspot, it takes the hotspot down and tries the saved network again (a
  router that was slow or briefly away must not leave the speaker stuck in
  setup mode until someone reboots it)
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
from utils.logger import log

CONNECT_TIMEOUT = 30  # Seconds to wait for auto-connect
AP_POLL_INTERVAL = 3  # Seconds between connection checks while in AP mode
AP_RETRY_INTERVAL = 120  # Seconds in AP mode between tries at the saved network


def log_wifi(message: str):
    """Log with the WIFI category"""
    log(message, "WIFI")


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
    """Main WiFi provisioning orchestrator.

    `wifi`, `led`, `clock` and `sleep` can be replaced (the tests do), so the
    flow can be run without NetworkManager and without waiting.
    """

    def __init__(self, wifi=WiFiManager, led=None, clock=time.monotonic, sleep=time.sleep):
        self.wifi = wifi
        self.led = led if led is not None else LEDController()
        self._now = clock
        self._sleep = sleep

    def run(self):
        """Main provisioning flow - wait for WiFi, fallback to AP mode"""
        log_wifi("Waiting for NetworkManager to connect...")
        self.led.connecting()

        # Give NetworkManager time to auto-connect to known networks
        if self._wait_for_wifi(CONNECT_TIMEOUT, announce=True):
            return  # Exit - normal operation can proceed

        # No connection after timeout - start AP mode and wait for the
        # main server's captive portal to provision credentials
        log_wifi("No connection, starting AP mode...")
        self._start_ap()
        self._wait_for_provisioning()

    def _wait_for_wifi(self, seconds: int, announce: bool = False) -> bool:
        """Wait up to `seconds` for a real WiFi connection. True if it came."""
        for i in range(seconds):
            if self.wifi.is_connected():
                ssid = self.wifi.get_current_ssid()
                log_wifi(f"Connected to {ssid}")
                self.led.connected()
                return True
            self._sleep(1)
            if announce and i % 5 == 0:
                log_wifi(f"Waiting... ({seconds - i}s remaining)")
        return False

    def _start_ap(self):
        self.led.ap_mode()
        self.wifi.start_ap()
        log_wifi(f"AP '{AP_SSID}' active")
        log_wifi(f"Setup portal at http://{AP_IP}:{WEB_PORT}/wifi-setup "
                 "(served by the main server)")

    def _wait_for_provisioning(self):
        """Monitor until the Pi is connected to a real network (not the AP).

        The main server handles credential intake and AP teardown; this loop
        mostly just watches for the result. Requires two consecutive positive
        checks so a transient state mid-connection-attempt isn't mistaken for
        success. Every AP_RETRY_INTERVAL seconds it also tries the saved
        network again (see _retry_saved_wifi).
        """
        consecutive = 0
        last_try = self._now()
        while True:
            # is_connected() is False while the AP profile is the active connection
            if self.wifi.is_connected():
                consecutive += 1
                if consecutive >= 2:
                    ssid = self.wifi.get_current_ssid()
                    log_wifi(f"Provisioned - connected to {ssid}")
                    self.led.connected()
                    return
            else:
                consecutive = 0
            self._sleep(AP_POLL_INTERVAL)

            if self._now() - last_try >= AP_RETRY_INTERVAL:
                if self._retry_saved_wifi():
                    return
                last_try = self._now()
                consecutive = 0

    def _retry_saved_wifi(self) -> bool:
        """Nobody has set up WiFi through the hotspot for a while: try the saved network again.

        The speaker used to sit in setup mode for ever after one slow start (on Sep 5 it did,
        twice in ten minutes, and had no internet until it was rebooted). If someone is
        connected to the hotspot they are probably setting it up, so they are left alone.
        Returns True if the WiFi is back.
        """
        if self.wifi.has_ap_clients():
            log_wifi("Someone is connected to the setup hotspot - leaving it up")
            return False
        log_wifi("The setup hotspot is not in use - trying the saved WiFi again")
        self.led.connecting()
        self.wifi.stop_ap()
        self.wifi.reconnect()
        if self._wait_for_wifi(CONNECT_TIMEOUT):
            return True
        log_wifi("Still no WiFi - bringing the setup hotspot back")
        self._start_ap()
        return False


if __name__ == '__main__':
    WiFiProvisioner().run()
