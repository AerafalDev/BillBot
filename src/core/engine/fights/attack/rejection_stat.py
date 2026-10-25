from enum import StrEnum, auto


class RejectionStat(StrEnum):
    MAX_CAST_PER_TARGET = auto()
    MAX_CAST_PER_TURN = auto()
    INSUFICIENT_AP = auto()
    INITIAL_COOLDOWN = auto()
    GLOBAL_COOLDOWN = auto()
    MIN_CAST_INTERVAL = auto()
    STATE_CRITERION = auto()
    CELL_NOT_WALKABLE = auto()
    CELL_NOT_FREE = auto()
    NO_LOS = auto()
    TARGET_NOT_VISIBLE = auto()
    MAX_STACK_REACHED = auto()
