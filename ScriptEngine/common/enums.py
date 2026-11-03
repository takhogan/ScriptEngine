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
    # The run stopped before a step that needs the user's approval (a getSecret
    # for a secret --approved-secrets does not list). Only ever a node status.
    NEEDS_APPROVAL = auto()

class ScriptExecutionStatusDetail(Enum):
    TIMED_OUT = auto()
    MAX_ATTEMPTS = auto()
    CANCELLED = auto()