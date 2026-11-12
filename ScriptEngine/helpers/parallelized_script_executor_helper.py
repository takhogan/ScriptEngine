import sys
import time

from ScriptEngine.common.logging.script_logger import ScriptLogger

# Worker-side compute time above this gets one info line. Compared against the
# main thread's PARALLEL WAIT, it splits a slow batch into worker compute vs.
# IPC/pickle/queue overhead: if handler time ~= wait, the worker is slow (its own
# CPU or disk); if handler time << wait, the cost is dispatch/result transfer of
# the detection arrays, not the detection itself.
PARALLEL_WORKER_LOG_THRESHOLD_S = 5.0

# Keys of the action dict the worker leaves out of its result: the screenshot
# and its blurred copy (input_obj) and the template images and masks
# (actionData). They are most of the result's pickled size (~17 MB for a
# detect), the worker only reads them, and the main process still holds the
# action it sent (ParallelizedScriptExecutor.sent_actions).
SENT_ONLY_ACTION_KEYS = ('input_obj', 'actionData')


def slim_parallel_result(action, handle_action_result):
    """The worker's result without the action keys the main process already has.

    A handler that returns the action it was given (detectObject:
    (action, matches, log_objs)) gets that action back as a copy without
    SENT_ONLY_ACTION_KEYS. What is left is the action's other top-level keys,
    among them script_logger, whose ActionLog the worker filled in. Any other
    result is returned as it is.
    """
    if (
        isinstance(handle_action_result, tuple)
        and len(handle_action_result) > 0
        and handle_action_result[0] is action
    ):
        slim_action = {
            key: value for key, value in action.items()
            if key not in SENT_ONLY_ACTION_KEYS
        }
        return (slim_action,) + handle_action_result[1:]
    return handle_action_result


def restore_parallel_result(sent_action, handle_action_result):
    """The worker's result with its action rebuilt from the action that was sent.

    The rebuilt action is a copy of sent_action with the returned keys laid
    over it, so it holds the sent input_obj and actionData and the worker's
    script_logger and other keys. sent_action itself is left as it is.
    Workers only add or change keys, never delete them, so the overlay is the
    whole action the worker ended with. A result that carries no action dict,
    or no sent_action, is returned as it is.
    """
    if (
        sent_action is None
        or not isinstance(handle_action_result, tuple)
        or len(handle_action_result) == 0
        or not isinstance(handle_action_result[0], dict)
    ):
        return handle_action_result
    action = dict(sent_action)
    action.update(handle_action_result[0])
    return (action,) + handle_action_result[1:]


class ParallelizedScriptExecutorHelper:
    def __init__(self, action_handler):
        self.action_handler = action_handler

    def handle_parallel_action(self, action_handler_args):
        script_logger = ScriptLogger()
        action = action_handler_args[0]
        script_logger.configure_action_logger_from_strs(*action["script_logger"])
        script_logger.log('handling parallel action')
        _handler_start = time.monotonic()
        handle_action_result = self.action_handler(*action_handler_args)
        _handler_s = time.monotonic() - _handler_start
        if _handler_s >= PARALLEL_WORKER_LOG_THRESHOLD_S:
            script_logger.log(
                'PARALLEL WORKER: action {}-{} handler ran {:.2f}s'.format(
                    action.get('actionName'), action.get('actionGroup'), _handler_s
                ),
                level='info'
            )

        return slim_parallel_result(action, handle_action_result)
