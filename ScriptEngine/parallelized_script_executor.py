import sys
import pickle
import time
sys.path.append("..")
from detect_object_helper import DetectObjectHelper
from script_logger import ScriptLogger
from parallelized_script_executor_helper import ParallelizedScriptExecutorHelper
script_logger = ScriptLogger()



class ParallelizedScriptExecutor:
    def __init__(self, executor):
        self.executor = executor
        self.processes = []

    def clear_processes(self):
        for process in self.processes:
            process.cancel()
        self.processes = []

    def start_processes(self, script_executor, parallel_actions):
        self.processes = []
        script_counter = script_executor.context["script_counter"]
        parent_action_log = script_executor.parent_action_log
        script_logger.log('CONTROL FLOW: starting parallel execution')
        for parallel_action in parallel_actions:
            del parallel_action["parallel_group"]

        # if you want to implement for other actions keep in mind you should filter here
        system_inputs = {}
        for process_index,parallel_action in enumerate(parallel_actions):
            script_counter += 1
            action_log = script_logger.configure_action_logger(parallel_action, script_counter, parent_action_log)

            input_obj = DetectObjectHelper.get_detect_area(parallel_action, script_executor.state)
            if input_obj['screencap_im_bgr'] is None:
                target_system = parallel_action['actionData']['targetSystem']
                if target_system == 'adb':
                    if "adb" in system_inputs:
                        device_screenshot = system_inputs['adb']
                    else:
                        device_screenshot = system_inputs['adb'] = script_executor.device_manager.adb_host.screenshot()
                elif target_system == 'python' or target_system == 'none':
                    if "python" in system_inputs:
                        device_screenshot = system_inputs['python']
                    else:
                        device_screenshot = system_inputs['python'] = script_executor.device_manager.python_host.screenshot()
                else:
                    raise Exception('unimplemented target system: ' + target_system)
                input_obj['screencap_im_bgr'] = device_screenshot
                input_obj['original_height'] = device_screenshot.shape[0]
                input_obj['original_width'] = device_screenshot.shape[1]
                input_obj['fixed_scale'] = False
            parallel_action["input_obj"] = input_obj
            (action_handler, action_handler_args) = script_executor.handle_action(parallel_action, lazy_eval=True)
            helper = ParallelizedScriptExecutorHelper(action_handler)

            future = self.executor.submit(
                helper.handle_parallel_action,
                script_logger.get_log_header(),
                script_logger.get_log_folder(),
                script_logger.get_log_level(),
                action_log,
                action_handler_args
            )
            parallel_action["parallel_process"] = process_index
            self.processes.append(future)
