"""
Chip/Tag data lookup - uses server_data.json as single source of truth

When an NFC chip is scanned:
1. Look up by UID in server_data.json
2. If found, get the song_id and resolve URI from library
3. If not found, register as new chip (so it appears in the app)
"""

from typing import Optional, Dict, Any
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import log_nfc, log_error, log_success


class ChipStore:
    """Manages chip/tag data from server_data.json (unified with HTTP server)"""
    
    def __init__(self):
        """Initialize chip store"""
        log_success("ChipStore initialized (using server_data.json)")
    
    def lookup(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Look up chip data by UID. 
        Returns dict with uid, name, uri, etc.
        
        - If chip is unknown, it will be auto-registered and returned with uri=''
        - If chip has no song assigned, returns with uri=''
        - If chip has song assigned, returns with uri set
        
        Returns None only on error.
        """
        # Import here to avoid circular imports
        from server import lookup_chip_by_uid, register_new_chip
        
        chip_data = lookup_chip_by_uid(uid)
        
        if chip_data is None:
            # Unknown chip - register it so it appears in the app
            log_nfc(f"New chip detected, registering: {uid[:30]}...")
            new_chip = register_new_chip(uid)
            log_nfc(f"Registered new chip: {new_chip.get('name', 'Unknown')} - assign a song in the app!")
            
            # Return chip data with empty uri (no song assigned yet)
            return {
                'uid': uid,
                'name': new_chip.get('name', 'New Chip'),
                'uri': '',  # No song assigned
                'is_new': True,  # Flag to indicate this was just registered
            }
        
        # Check if chip has a song assigned
        if not chip_data.get('uri'):
            log_nfc(f"Chip '{chip_data.get('name', 'Unknown')}' has no song assigned - use the app to assign one")
            chip_data['uri'] = ''  # Ensure uri is empty string, not None
        else:
            log_nfc(f"Found chip: {chip_data.get('name', 'Unknown')} -> {chip_data.get('uri')}")
        
        return chip_data
    
    def reload(self):
        """Reload is not needed - data is always read fresh from server_data.json"""
        pass
    
    def get_all_uids(self) -> list:
        """Get all known UIDs"""
        from server import get_all_chip_uids
        return get_all_chip_uids()
