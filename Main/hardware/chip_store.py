"""
Chip/Tag data lookup - fetches data from local HTTP server

When an NFC chip is scanned:
1. Look up by UID via HTTP API call to local server
2. If found, the server answers with the chip and the link of its song
3. If not found, register as new chip via HTTP API (so it appears in the app)

This approach avoids consistency issues by ensuring all data access
goes through the centralized HTTP server.
"""

from typing import Optional, Dict, Any
import json
import urllib.parse
import urllib.request
import urllib.error

from config.settings import SERVER_HOST, SERVER_PORT
from utils.logger import log_nfc, log_error, log_success


# Server configuration
SERVER_BASE_URL = f'http://{SERVER_HOST}:{SERVER_PORT}'


class ChipStore:
    """Manages chip/tag data via HTTP calls to local server"""
    
    def __init__(self):
        """Initialize chip store"""
        log_success(f"ChipStore initialized (using HTTP server at {SERVER_BASE_URL})")
    
    def _http_get(self, endpoint: str) -> Optional[Dict]:
        """Make HTTP GET request to local server"""
        try:
            url = f'{SERVER_BASE_URL}{endpoint}'
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log_error(f"HTTP GET error: {e.code} {e.reason}")
            return None
        except Exception as e:
            log_error(f"HTTP GET failed: {e}")
            return None
    
    def _http_post(self, endpoint: str, data: Dict) -> Optional[Dict]:
        """Make HTTP POST request to local server"""
        try:
            url = f'{SERVER_BASE_URL}{endpoint}'
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=json_data,
                method='POST',
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            log_error(f"HTTP POST failed: {e}")
            return None
    
    def _find_chip(self, uid: str):
        """Ask the server about one chip, by number. One request.

        Returns ('found', chip), ('unknown', None) or ('error', None). An unknown chip and a
        server that cannot be reached are different things: the first is registered, the second
        must not be.
        """
        url = f'{SERVER_BASE_URL}/chips/lookup?{urllib.parse.urlencode({"uid": uid})}'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method='GET'), timeout=5) as response:
                return 'found', json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            try:
                reason = json.loads(e.read().decode('utf-8')).get('error')
            except Exception:
                reason = None
            if e.code == 404 and reason == 'unknown chip':
                return 'unknown', None
            log_error(f"Chip lookup failed: {e.code} {e.reason} (is the server the same version as the controller?)")
            return 'error', None
        except Exception as e:
            log_error(f"Chip lookup failed: {e}")
            return 'error', None

    def lookup(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Look up chip data by UID with one request to the local server.
        Returns dict with uid, name, uri, etc.
        
        - If chip is unknown, it will be auto-registered and returned with uri=''
        - If chip has no song assigned, returns with uri=''
        - If chip has song assigned, returns with uri set
        
        Returns None only on error.
        """
        outcome, chip_data = self._find_chip(uid)
        if outcome == 'error':
            log_error("Failed to look up the chip on the server")
            return None
        
        if outcome == 'unknown':
            # Unknown chip - register it so it appears in the app
            log_nfc(f"New chip detected, registering: {uid[:30]}...")
            new_chip = self._http_post('/chips', {'uid': uid})
            
            if new_chip is None:
                log_error("Failed to register new chip via HTTP")
                return None
            
            log_nfc(f"Registered new chip: {new_chip.get('name', 'Unknown')} - assign a song in the app!")
            
            # Return chip data with empty uri (no song assigned yet)
            return {
                'id': new_chip.get('id'),
                'uid': uid,
                'name': new_chip.get('name', 'New Chip'),
                'uri': '',  # No song assigned
                'is_new': True,  # Flag to indicate this was just registered
            }
        
        result = {
            'id': chip_data.get('id'),  # the server's chip id (voice "clear" needs it)
            'uid': uid,
            'name': chip_data.get('name', 'Unknown'),
            'uri': chip_data.get('uri', ''),  # the server resolves it from the song
            'song_id': chip_data.get('song_id'),
            'song_name': chip_data.get('song_name', ''),
        }
        
        # Check if chip has a song assigned
        if not result['uri']:
            log_nfc(f"Chip '{result['name']}' has no song assigned - use the app to assign one")
        else:
            log_nfc(f"Found chip: {result['name']} -> {result['uri']}")
        
        return result
    
    def reload(self):
        """Reload is not needed - data is always fetched fresh from server"""
        # No-op: data is always fetched fresh via HTTP calls
    
    def get_all_uids(self) -> list:
        """Get all known UIDs via HTTP API call"""
        chips = self._http_get('/chips')
        if chips is None:
            return []
        return [chip.get('uid') for chip in chips if chip.get('uid')]
