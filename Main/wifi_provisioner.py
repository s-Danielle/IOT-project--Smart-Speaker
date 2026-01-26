#!/usr/bin/env python3
"""
WiFi Provisioning Service (NetworkManager-based)
- Waits for NetworkManager to connect on boot
- If no connection after timeout, starts AP mode
- LED feedback via Light 1

This service uses the shared WiFiManager from hardware/wifi_manager.py
"""
import os
import sys
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware.wifi_manager import (
    WiFiManager, AP_SSID, AP_IP, WEB_PORT,
    render_network_list_html, render_status_html
)

CONNECT_TIMEOUT = 30  # Seconds to wait for auto-connect


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


class CaptivePortalHandler(BaseHTTPRequestHandler):
    """HTTP handler for captive portal - uses shared WiFiManager and HTML templates"""
    
    def log_message(self, format, *args):
        """Log requests for debugging"""
        print(f"[HTTP] WIFI-PROVISIONER: {self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests - show network list"""
        networks = WiFiManager.scan_networks()
        html = render_network_list_html(networks, connect_action="/connect")
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def do_POST(self):
        """Handle POST requests - connect to network"""
        length = int(self.headers['Content-Length'])
        data = parse_qs(self.rfile.read(length).decode())
        ssid = data.get('ssid', [''])[0]
        password = data.get('password', [''])[0]
        
        if self.server.led:
            self.server.led.connecting()
        
        success = WiFiManager.connect(ssid, password)
        
        if success:
            if self.server.led:
                self.server.led.connected()
            threading.Timer(5, lambda: subprocess.run(['sudo', 'reboot'])).start()
        else:
            if self.server.led:
                self.server.led.failed()
                time.sleep(1)
                self.server.led.ap_mode()
            WiFiManager.start_ap()
        
        html = render_status_html(success, ssid, connect_action="/connect")
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))


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
        
        # No connection after timeout - start AP mode
        print("[WiFi] No connection, starting AP mode...")
        self.led.ap_mode()
        WiFiManager.start_ap()
        
        # Start captive portal
        server = HTTPServer(('0.0.0.0', WEB_PORT), CaptivePortalHandler)
        server.led = self.led
        print(f"[WiFi] Captive portal running at http://{AP_IP}:{WEB_PORT}")
        print(f"[WiFi] Connect to '{AP_SSID}' WiFi to configure")
        server.serve_forever()


if __name__ == '__main__':
    WiFiProvisioner().run()
