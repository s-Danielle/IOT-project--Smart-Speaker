"""
Load tags.json, UID lookup
"""

import json
from typing import Optional, Dict, Any
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.paths import TAGS_JSON
from utils.logger import log_nfc, log_error, log_success


class ChipStore:
    """Manages chip/tag data from tags.json"""
    
    def __init__(self, tags_path: str = None):
        """Load tags from JSON file"""
        self._tags_path = tags_path or TAGS_JSON
        self._tags: Dict[str, Dict[str, Any]] = {}
        self.reload()
    
    def lookup(self, uid: str) -> Optional[Dict[str, Any]]:
        """Look up chip data by UID. Returns dict with name, uri, etc."""
        if uid in self._tags:
            data = self._tags[uid].copy()
            data['uid'] = uid
            log_nfc(f"Found chip: {data.get('name', 'Unknown')} -> {data.get('uri', 'No URI')}")
            return data
        log_nfc(f"Unknown chip UID: {uid}")
        return None
    
    def reload(self):
        """Reload tags from disk"""
        try:
            if os.path.exists(self._tags_path):
                with open(self._tags_path, 'r') as f:
                    self._tags = json.load(f)
                log_success(f"Loaded {len(self._tags)} chips from {self._tags_path}")
            else:
                log_error(f"Tags file not found: {self._tags_path}")
                self._tags = {}
        except json.JSONDecodeError as e:
            log_error(f"Invalid JSON in tags file: {e}")
            self._tags = {}
        except Exception as e:
            log_error(f"Failed to load tags: {e}")
            self._tags = {}
    
    def get_all_uids(self) -> list:
        """Get all known UIDs"""
        return list(self._tags.keys())
