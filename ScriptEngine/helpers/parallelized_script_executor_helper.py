import sys
import time

from ScriptEngine.common.logging.script_logger import ScriptLogger

# Worker-side compute time above this gets one info line. Compared against the
# main thread's PARALLEL WAIT, it splits a slow batch into worker compute vs.
# IPC/pickle/queue overhead: if handler time ~= wait, the worker is slow (its own
# CPU or disk); if handler time << wait, the cost is dispatch/result transfer of
# the detection arrays, not the detection itself.
PARALLEL_WORKER_LOG_THRESHOLD_S = 5.0


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

        return handle_action_result
