from enum import Enum, auto

class ScriptExecutionStatusDetail(Enum):
    TIMED_OUT = auto()
    MAX_ATTEMPTS = auto()
    CANCELLED = auto()