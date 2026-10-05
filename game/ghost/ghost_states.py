from enum import Enum, auto


class GhostState(Enum):
    PATROL = auto()
    INVESTIGATE = auto()
    SEARCH = auto()
    CHASE = auto()
    JUMPSCARE = auto()
