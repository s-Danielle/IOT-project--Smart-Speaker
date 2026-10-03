"""Rules that every way of storing the speaker's data shares.

The JSON file store and the later SQLite store both call these, so the two behave the same.
Nothing here touches a file.
"""

import copy
import re
import uuid

DEFAULT_PARENTAL_CONTROLS = {
    "enabled": False,
    "volume_limit": 100,
    "quiet_hours": {
        "enabled": False,
        "start": "21:00",
        "end": "07:00",
    },
    "daily_limit_minutes": 0,
    "chip_blacklist": [],
    "chip_whitelist_mode": False,
    "chip_whitelist": [],
}

# What a brand-new speaker starts with.
DEFAULT_LIBRARY = [
    {"id": "song001", "name": "Surprise", "uri": "spotify:track:4PTG3Z6ehGkBFwjybzWkR8"},
    {"id": "song002", "name": "Lights", "uri": "file:///home/iot-proj/lights.mp3"},
]


def default_data() -> dict:
    """A fresh copy every time, so nobody can change the defaults by accident."""
    return {
        "chips": [],
        "library": copy.deepcopy(DEFAULT_LIBRARY),
        "parental_controls": copy.deepcopy(DEFAULT_PARENTAL_CONTROLS),
        "daily_usage": {},
    }


def new_chip_id(taken=()) -> str:
    return _new_id("chip", taken)


def new_song_id(taken=()) -> str:
    return _new_id("song", taken)


def _new_id(prefix: str, taken) -> str:
    while True:
        candidate = f"{prefix}{uuid.uuid4().hex[:6]}"
        if candidate not in taken:
            return candidate


def same_uid(a, b) -> bool:
    """Chip numbers are hex text, so 'e41c9dbb' and 'E41C9DBB' are the same chip."""
    return isinstance(a, str) and isinstance(b, str) and a.casefold() == b.casefold()


# ---------------------------------------------------------------------------
# Parental controls
# ---------------------------------------------------------------------------

_TIME_OF_DAY = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def complete_parental_controls(stored) -> dict:
    """The stored settings with any missing field filled in from the defaults (older files lack some)."""
    result = copy.deepcopy(DEFAULT_PARENTAL_CONTROLS)
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key == "quiet_hours" and isinstance(value, dict):
                result["quiet_hours"].update(value)
            else:
                result[key] = copy.deepcopy(value)
    return result


def apply_parental_changes(stored, changes) -> dict:
    """Return the settings after applying `changes`. Only the fields given change.

    Raises ValueError for a value of the wrong kind, so junk never reaches the file.
    """
    if not isinstance(changes, dict):
        raise ValueError("settings must be an object")
    pc = complete_parental_controls(stored)

    if "enabled" in changes:
        pc["enabled"] = _flag(changes["enabled"], "enabled")
    if "volume_limit" in changes:
        pc["volume_limit"] = max(0, min(100, _whole_number(changes["volume_limit"], "volume_limit")))
    if "quiet_hours" in changes:
        quiet = changes["quiet_hours"]
        if not isinstance(quiet, dict):
            raise ValueError("quiet_hours must be an object")
        if "enabled" in quiet:
            pc["quiet_hours"]["enabled"] = _flag(quiet["enabled"], "quiet_hours.enabled")
        for field in ("start", "end"):
            if field in quiet:
                pc["quiet_hours"][field] = _time_of_day(quiet[field], "quiet_hours." + field)
    if "daily_limit_minutes" in changes:
        pc["daily_limit_minutes"] = max(0, _whole_number(changes["daily_limit_minutes"], "daily_limit_minutes"))
    if "chip_blacklist" in changes:
        pc["chip_blacklist"] = _text_list(changes["chip_blacklist"], "chip_blacklist")
    if "chip_whitelist_mode" in changes:
        pc["chip_whitelist_mode"] = _flag(changes["chip_whitelist_mode"], "chip_whitelist_mode")
    if "chip_whitelist" in changes:
        pc["chip_whitelist"] = _text_list(changes["chip_whitelist"], "chip_whitelist")
    return pc


def _flag(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _whole_number(value, name):
    # bool is a kind of int in Python, and True would silently become 1
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return int(value)


def _time_of_day(value, name):
    if not isinstance(value, str) or not _TIME_OF_DAY.match(value):
        raise ValueError(f"{name} must look like 21:30")
    hours, minutes = value.split(":")
    return f"{int(hours):02d}:{minutes}"


def _text_list(value, name):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of text")
    return list(value)
