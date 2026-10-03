"""Who may change what: the rules the server applies to every request.

Plain reads (status, chips, library, settings, the web app) are open to anyone on the network. Anything
that changes something, and everything under /debug (logs, restart, reboot, WiFi), needs the speaker's
API token in the X-Speaker-Token header. Exceptions:

  - Requests from the speaker itself (the controller and the health monitor call the server on
    localhost) need no token.
  - While the setup hotspot is up, the few routes the WiFi setup needs are open, because a phone
    that has just joined the hotspot has no token yet.

The token stops other websites from making a browser on your network change the speaker, and stops
casual meddling by other devices. It does not hide anything from someone who can watch the
network traffic: this is plain HTTP.

Nothing here touches the network or the file system, so it can be tested on its own.
"""

import hmac
import ipaddress
from urllib.parse import urlparse

TOKEN_HEADER = "X-Speaker-Token"

# Answers of protection()
NEVER = "never"                       # open to everyone
ALWAYS = "always"                     # needs the token
UNLESS_SETUP_MODE = "unless_setup"    # needs the token, except while the setup hotspot is up

# The WiFi setup, which has to work for a phone that has only just joined the open hotspot.
SETUP_ROUTES = frozenset({
    "/wifi-setup",
    "/wifi-setup/connect",
    "/debug/wifi/status",
    "/debug/wifi/scan",
    "/debug/wifi/connect",
    "/debug/wifi/connect-status",
})


def normalize(path: str) -> str:
    """The route without the query string and without a trailing slash."""
    return urlparse(path).path.rstrip("/")


def protection(method: str, path: str) -> str:
    route = normalize(path)
    if route in SETUP_ROUTES:
        return UNLESS_SETUP_MODE
    if route == "/debug" or route.startswith("/debug/"):
        return ALWAYS  # even reads: the logs, the system and the saved WiFi networks are not for everyone
    if method.upper() in ("GET", "HEAD"):
        return NEVER
    return ALWAYS


def is_local_address(address: str) -> bool:
    """True for a request that came from the speaker itself."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def token_matches(supplied, expected) -> bool:
    """Compare in constant time, so the time taken doesn't give the token away a character at a time."""
    if not supplied or not expected:
        return False
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
