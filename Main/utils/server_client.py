"""
HTTP client for speaker to communicate with server.

This module provides functions for the smart speaker hardware controller
to fetch data from the server via HTTP. This replaces direct Python imports
from server.py, enabling the server and speaker to run as separate processes.

All data fetching goes through HTTP to ensure the server is the single
source of truth for all configuration and chip data.
"""

import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

from config.settings import SERVER_HOST, SERVER_PORT
from utils.logger import log_error, log


# Server configuration
SERVER_BASE_URL = f'http://{SERVER_HOST}:{SERVER_PORT}'


def _http_get(endpoint: str, timeout: int = 5) -> Optional[Any]:
    """Make HTTP GET request to local server.
    
    Args:
        endpoint: API endpoint (e.g., '/parental')
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response, or None on error
    """
    try:
        url = f'{SERVER_BASE_URL}{endpoint}'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        log_error(f"HTTP GET {endpoint} error: {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        log_error(f"HTTP GET {endpoint} connection error: {e.reason}")
        return None
    except Exception as e:
        log_error(f"HTTP GET {endpoint} failed: {e}")
        return None


def _http_post(endpoint: str, data: Dict, timeout: int = 5) -> Optional[Any]:
    """Make HTTP POST request to local server.
    
    Args:
        endpoint: API endpoint
        data: Data to send as JSON
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response, or None on error
    """
    try:
        url = f'{SERVER_BASE_URL}{endpoint}'
        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=json_data,
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        log_error(f"HTTP POST {endpoint} failed: {e}")
        return None


# =============================================================================
# Parental Controls API
# =============================================================================

def get_parental_controls() -> Dict[str, Any]:
    """Fetch parental controls settings from server.
    
    Returns:
        Parental controls dict, or safe defaults on error
    """
    result = _http_get('/parental')
    if result is None:
        # Return safe defaults if server is unreachable
        return {
            'enabled': False,
            'volume_limit': 100,
            'quiet_hours': {
                'enabled': False,
                'start': '21:00',
                'end': '07:00'
            },
            'daily_limit_minutes': 0,
            'chip_blacklist': [],
            'chip_whitelist_mode': False,
            'chip_whitelist': []
        }
    return result


# =============================================================================
# Chip Data API
# =============================================================================

def get_chips() -> List[Dict[str, Any]]:
    """Fetch all chips from server.
    
    Returns:
        List of chip dicts, or empty list on error
    """
    result = _http_get('/chips')
    return result if result is not None else []


def get_chip_by_uid(uid: str) -> Optional[Dict[str, Any]]:
    """Fetch chip data by UID from server.
    
    Args:
        uid: NFC chip UID
        
    Returns:
        Chip dict with resolved URI, or None if not found
    """
    chips = get_chips()
    for chip in chips:
        if chip.get('uid') == uid:
            # Resolve URI from library if chip has song_id
            uri = ''
            song_id = chip.get('song_id')
            if song_id:
                library = get_library()
                for song in library:
                    if song.get('id') == song_id:
                        uri = song.get('uri', '')
                        break
            
            return {
                'uid': uid,
                'name': chip.get('name', 'Unknown'),
                'uri': uri,
                'song_id': song_id,
                'song_name': chip.get('song_name', ''),
            }
    return None


# =============================================================================
# Library API
# =============================================================================

def get_library() -> List[Dict[str, Any]]:
    """Fetch library songs from server.
    
    Returns:
        List of song dicts, or empty list on error
    """
    result = _http_get('/library')
    return result if result is not None else []


# =============================================================================
# Status API
# =============================================================================

def get_status() -> Optional[Dict[str, Any]]:
    """Fetch current status from server.
    
    Returns:
        Status dict, or None on error
    """
    return _http_get('/status')


def check_server_health() -> bool:
    """Check if server is reachable and healthy.
    
    Returns:
        True if server responds, False otherwise
    """
    try:
        status = get_status()
        return status is not None
    except Exception:
        return False
