from enum import Enum, auto


class ScriptExecutionState(Enum):
    STARTING = auto()
    ERROR = auto()
    FINISHED = auto()
    SUCCESS = auto()
    FAILURE = auto()
    RETURN = auto()
    OUT_OF_ATTEMPTS = auto()
    FINISHED_FAILURE = auto()
    FINISHED_BRANCH = auto()
    FINISHED_FAILURE_BRANCH = auto()