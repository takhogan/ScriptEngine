from enum import Enum, auto


class ScriptExecutionState(Enum):
    STARTING = auto(),
    ERROR = auto(),
    FINISHED = auto(),
    SUCCESS = auto(),
    FAILURE = ()