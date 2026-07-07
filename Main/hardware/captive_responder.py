"""
Captive-portal HTTP responder.

While the setup AP is active, OS captive-portal probes hit port 80 on
arbitrary hosts (e.g. http://connectivitycheck.gstatic.com/generate_204,
http://captive.apple.com/hotspot-detect.html). Combined with the dnsmasq
catch-all (services/nm-dnsmasq-captive.conf resolves every name to the
Pi), this responder answers ALL of them with a 302 redirect to the WiFi
setup portal, which makes phones show the "sign in to network" sheet.

Lifecycle is owned by WiFiManager: started in start_ap(), stopped in
stop_ap(). Binding port 80 requires root; failure to bind is logged and
never breaks AP mode.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.logger import log

CAPTIVE_PORT = 80

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None


def _make_handler(redirect_url: str):
    class CaptiveRedirectHandler(BaseHTTPRequestHandler):
        # Don't wait for slow/broken probe clients
        timeout = 10

        def _redirect(self):
            self.send_response(302)
            self.send_header('Location', redirect_url)
            self.send_header('Content-Length', '0')
            # Probe clients shouldn't cache the redirect
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        do_GET = _redirect
        do_POST = _redirect
        do_HEAD = _redirect

        def log_message(self, format, *args):
            # Probes are frequent and noisy; stay quiet
            pass

    return CaptiveRedirectHandler


def start(redirect_url: str, port: int = CAPTIVE_PORT) -> bool:
    """Start the responder on 0.0.0.0:port. Idempotent.

    Returns True if running (newly started or already running). A bind
    failure (port in use, no root) is logged and returns False without
    raising, so AP mode itself is never affected.
    """
    global _server, _thread
    with _lock:
        if _server is not None:
            return True
        try:
            server = ThreadingHTTPServer(('0.0.0.0', port), _make_handler(redirect_url))
        except OSError as e:
            log(f"Captive responder: cannot bind port {port} "
                f"({e}); captive-portal auto-popup disabled", "WARN")
            return False
        server.daemon_threads = True
        _server = server
        _thread = threading.Thread(
            target=server.serve_forever, name='captive-responder', daemon=True
        )
        _thread.start()
        log(f"Captive responder listening on :{port}, "
            f"redirecting to {redirect_url}")
        return True


def stop() -> None:
    """Stop the responder and release the port. Idempotent."""
    global _server, _thread
    with _lock:
        if _server is None:
            return
        server, thread = _server, _thread
        _server = None
        _thread = None
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)
    log("Captive responder stopped")


def is_running() -> bool:
    return _server is not None
