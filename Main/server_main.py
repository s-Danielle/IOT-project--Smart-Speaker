#!/usr/bin/env python3
"""
Standalone HTTP server entry point.

This runs the API server as an independent service, separate from the
hardware controller. The server handles:
- REST API for Flutter app communication
- Chip and library data management
- Parental controls
- Debug/developer tools endpoints
- Speaker service lifecycle management

Usage:
    python server_main.py

The server listens on the port specified in config/settings.py (default: 5050).
"""

from server import run_server_blocking
from config.settings import SERVER_PORT
from utils.logger import log, log_success

if __name__ == "__main__":
    log("=" * 60)
    log("SMART SPEAKER API SERVER")
    log("=" * 60)
    log(f"Starting standalone server on port {SERVER_PORT}...")
    run_server_blocking(port=SERVER_PORT)
