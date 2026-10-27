#!/usr/bin/env python3
"""
WiFi Provisioning Service (NetworkManager-based)

Runs for as long as the speaker is on (no HTTP server, binds no ports):
- At boot it waits for NetworkManager to join a saved network
- Whenever there has been no network for NO_NETWORK_GRACE seconds (at boot, or
  later because the router went away or the speaker was moved), it starts AP
  mode (SmartSpeaker-Setup) and waits until the Pi is on a real network again
- While in AP mode, every AP_RETRY_INTERVAL seconds, if nobody is using the
  hotspot, it takes the hotspot down and tries the saved network again (a
  router that was slow or briefly away must not leave the speaker stuck in
  setup mode until someone reboots it)
- Credential intake and AP teardown are handled by the main server's
  captive portal (Main/server.py, /wifi-setup on port 8080)
- LED feedback via Light 1

This service uses the shared WiFiManager from hardware/wifi_manager.py
"""
import json
import os
import sys
import time
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware.wifi_manager import WiFiManager, AP_SSID, AP_IP, WEB_PORT
from utils.logger import log
from config.settings import SERVER_HOST, SERVER_PORT

NO_NETWORK_GRACE = 60  # Seconds without a network (at boot or later) before the setup hotspot starts
WATCH_INTERVAL = 10  # Seconds between network checks once the speaker is online
AP_POLL_INTERVAL = 3  # Seconds between connection checks while in AP mode
AP_RETRY_INTERVAL = 120  # Seconds in AP mode between tries at the saved network
AP_RETRY_WAIT = 30  # Seconds one such try waits for the network (the hotspot is down meanwhile)


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


def portal_is_connecting() -> bool:
    """Is the setup page (in the server, another program) in the middle of joining a network?

    Asked over localhost, which needs no token. If the server does not answer, nobody is using the
    portal, so the answer is no.
    """
    try:
        url = f"http://{SERVER_HOST}:{SERVER_PORT}/debug/wifi/connect-status"
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.loads(response.read().decode("utf-8")).get("state") == "connecting"
    except Exception:
        return False


class WiFiProvisioner:
    """Main WiFi provisioning orchestrator.

    `wifi`, `led`, `clock` and `sleep` can be replaced (the tests do), so the
    flow can be run without NetworkManager and without waiting.
    """

    def __init__(self, wifi=WiFiManager, led=None, clock=time.monotonic, sleep=time.sleep, portal_busy=None):
        self.wifi = wifi
        self.led = led if led is not None else LEDController()
        self._now = clock
        self._sleep = sleep
        self._portal_busy = portal_busy if portal_busy is not None else portal_is_connecting

    def run(self):
        """Boot, then watch the network for as long as the speaker is on."""
        self.boot()
        self.watch()

    def boot(self):
        """Wait for the saved network; if it does not come, set up through the hotspot."""
        log_wifi("Waiting for NetworkManager to connect...")
        self.led.connecting()

        # Give NetworkManager time to auto-connect to known networks
        if self._wait_for_wifi(NO_NETWORK_GRACE, announce=True):
            return  # Normal operation can proceed

        log_wifi("No connection, starting AP mode...")
        self._enter_setup_mode()

    def watch(self):
        """Online: check every WATCH_INTERVAL seconds. No network for NO_NETWORK_GRACE seconds
        in a row (a router that was moved, replaced or switched off): go back to setup mode.

        Time without a network that is shorter than the grace is left to NetworkManager, which
        keeps trying the saved networks by itself. While the setup page is in the middle of
        joining a network the speaker is offline on purpose, so that does not count.
        """
        lost_since = None
        while True:
            self._sleep(WATCH_INTERVAL)
            if self.wifi.is_online() or self._portal_busy():
                if lost_since is not None:
                    log_wifi("The network is back")
                    lost_since = None
                continue
            if lost_since is None:
                lost_since = self._now()
                log_wifi(f"No network. Setup mode starts in {NO_NETWORK_GRACE}s unless it comes back")
            elif self._now() - lost_since >= NO_NETWORK_GRACE:
                log_wifi(f"No network for {NO_NETWORK_GRACE}s, starting AP mode...")
                self._enter_setup_mode()
                lost_since = None

    def _enter_setup_mode(self):
        """Open the hotspot (unless it is already up), wait for the network, close the hotspot's helpers."""
        if self.wifi.get_current_ssid() == AP_SSID:
            # Somebody (the developer tools) started it. Restarting it would throw its clients off.
            self.led.ap_mode()
        else:
            self._start_ap()
        self._wait_for_provisioning()
        # The server took the hotspot down, but the port-80 helper lives in this program
        self.wifi.stop_captive_responder()

    def _wait_for_wifi(self, seconds: int, announce: bool = False) -> bool:
        """Wait up to `seconds` for a real WiFi connection with an address. True if it came."""
        for i in range(seconds):
            if self.wifi.is_online():
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
            # is_online() is False while the AP profile is the active connection
            if self.wifi.is_online():
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
        if self._portal_busy():
            # The portal has taken the hotspot down to join the network somebody just chose. That
            # leaves no client on the hotspot, but it is not "nobody is using it".
            log_wifi("The setup page is connecting to a network - not interfering")
            return False
        log_wifi("The setup hotspot is not in use - trying the saved WiFi again")
        self.led.connecting()
        self.wifi.stop_ap()
        self.wifi.reconnect()
        if self._wait_for_wifi(AP_RETRY_WAIT):
            return True
        log_wifi("Still no WiFi - bringing the setup hotspot back")
        self._start_ap()
        return False


if __name__ == '__main__':
    WiFiProvisioner().run()
