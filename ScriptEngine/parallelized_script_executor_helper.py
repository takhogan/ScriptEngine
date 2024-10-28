import sys
sys.path.append("..")

from script_logger import ScriptLogger


class ParallelizedScriptExecutorHelper:
    def __init__(self, action_handler):
        self.action_handler = action_handler

    def handle_parallel_action(self, log_header, log_folder, log_level, action_log, action_handler_args):
        script_logger = ScriptLogger()
        script_logger.configure_action_logger_from_strs(log_header, log_folder, log_level, action_log)

        script_logger.set_action_log(action_log)
        handle_action_result = self.action_handler(*action_handler_args)
        _, status, _, context, _, _ = handle_action_result

        if "status_detail" in context:
            status_detail = context["status_detail"]
            del context["status_detail"]
        else:
            status_detail = None
        if status_detail is not None:
            script_logger.get_action_log().set_status(status_detail)
        else:
            script_logger.get_action_log().set_status(status.name)
        return handle_action_result
