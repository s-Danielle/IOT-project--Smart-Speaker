"""
Enums + dataclasses for device state
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class State(Enum):
    """Device states"""
    IDLE_NO_CHIP = auto()
    IDLE_CHIP_LOADED = auto()
    PLAYING = auto()
    PAUSED = auto()
    RECORDING = auto()
    
    def __str__(self):
        return self.name.replace("_", " ")


@dataclass
class ChipData:
    """Data associated with a loaded chip"""
    uid: str = ""
    name: str = ""
    uri: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self):
        return f"Chip({self.name}, uri={self.uri})"


@dataclass 
class DeviceState:
    """Current state of the device"""
    state: State = State.IDLE_NO_CHIP
    loaded_chip: Optional[ChipData] = None
    was_playing_before_recording: bool = False
    previous_state: Optional[State] = None  # For returning after recording
    
    def __str__(self):
        chip_info = f", chip={self.loaded_chip.name}" if self.loaded_chip else ""
        return f"DeviceState({self.state}{chip_info})"
