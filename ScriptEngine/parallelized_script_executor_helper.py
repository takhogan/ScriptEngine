import sys
sys.path.append("..")

from script_logger import ScriptLogger


class ParallelizedScriptExecutorHelper:
    def __init__(self, action_handler):
        self.action_handler = action_handler

    def handle_parallel_action(self, action_handler_args):
        script_logger = ScriptLogger()
        action = action_handler_args[0]
        script_logger.configure_action_logger_from_strs(*action["script_logger"])
        script_logger.log('handling parallel action')
        handle_action_result = self.action_handler(*action_handler_args)

        return handle_action_result
