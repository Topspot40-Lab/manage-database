from enum import Enum

class ModeFlag(str, Enum):
    SOLO = "SOLO"
    DUET = "DUET"
    FEATURED = "FEATURED"
    GROUP = "GROUP"
    UNKNOWN = "UNKNOWN"
