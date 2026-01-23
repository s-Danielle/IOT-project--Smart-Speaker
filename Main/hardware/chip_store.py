"""
Chip/Tag data lookup - fetches data from local HTTP server

When an NFC chip is scanned:
1. Look up by UID via HTTP API call to local server
2. If found, get the song_id and resolve URI from library
3. If not found, register as new chip via HTTP API (so it appears in the app)

This approach avoids consistency issues by ensuring all data access
goes through the centralized HTTP server.
"""

from typing import Optional, Dict, Any
import json
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
    
    def lookup(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Look up chip data by UID via HTTP API call.
        Returns dict with uid, name, uri, etc.
        
        - If chip is unknown, it will be auto-registered and returned with uri=''
        - If chip has no song assigned, returns with uri=''
        - If chip has song assigned, returns with uri set
        
        Returns None only on error.
        """
        # Get all chips and filter by UID client-side
        chips = self._http_get('/chips')
        if chips is None:
            log_error("Failed to fetch chips from server")
            return None
        
        # Find chip with matching UID
        chip_data = None
        for chip in chips:
            if chip.get('uid') == uid:
                chip_data = chip
                break
        
        if chip_data is None:
            # Unknown chip - register it so it appears in the app
            log_nfc(f"New chip detected, registering: {uid[:30]}...")
            new_chip = self._http_post('/chips', {'uid': uid})
            
            if new_chip is None:
                log_error("Failed to register new chip via HTTP")
                return None
            
            log_nfc(f"Registered new chip: {new_chip.get('name', 'Unknown')} - assign a song in the app!")
            
            # Return chip data with empty uri (no song assigned yet)
            return {
                'uid': uid,
                'name': new_chip.get('name', 'New Chip'),
                'uri': '',  # No song assigned
                'is_new': True,  # Flag to indicate this was just registered
            }
        
        # Resolve URI from library if chip has a song assigned
        uri = ''
        song_id = chip_data.get('song_id')
        if song_id:
            library = self._http_get('/library')
            if library:
                for song in library:
                    if song.get('id') == song_id:
                        uri = song.get('uri', '')
                        break
        
        result = {
            'uid': uid,
            'name': chip_data.get('name', 'Unknown'),
            'uri': uri,
            'song_id': song_id,
            'song_name': chip_data.get('song_name', ''),
        }
        
        # Check if chip has a song assigned
        if not uri:
            log_nfc(f"Chip '{result['name']}' has no song assigned - use the app to assign one")
        else:
            log_nfc(f"Found chip: {result['name']} -> {uri}")
        
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
