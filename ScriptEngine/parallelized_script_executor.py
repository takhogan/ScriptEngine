import sys
import pickle
import time
import cv2
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
            parallel_action["script_logger"] = (
                script_logger.get_log_header(),
                script_logger.get_log_folder(),
                script_logger.get_log_level(),
                action_log
            )
            input_obj = DetectObjectHelper.get_detect_area(parallel_action, script_executor.state)
            if input_obj['screencap_im_bgr'] is None:
                script_logger.log('No input expression, using cached screenshot')
                target_system = parallel_action['actionData']['targetSystem']
                if target_system == 'adb':
                    if "adb" in system_inputs:
                        input_obj = system_inputs['adb']
                    else:
                        input_obj['screencap_im_bgr'] = script_executor.device_manager.adb_host.screenshot()
                        original_image = cv2.copyMakeBorder(input_obj['screencap_im_bgr'].copy(), 15, 15, 15, 15,cv2.BORDER_REPLICATE)
                        original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                        input_obj["original_image"] = original_image[15:-15, 15:-15]
                        input_obj['original_height'] = input_obj['screencap_im_bgr'].shape[0]
                        input_obj['original_width'] = input_obj['screencap_im_bgr'].shape[1]
                        input_obj['fixed_scale'] = False
                        system_inputs['adb'] = input_obj
                elif target_system == 'python' or target_system == 'none':
                    if "python" in system_inputs:
                        input_obj = system_inputs['python']
                    else:
                        input_obj['screencap_im_bgr'] = script_executor.device_manager.python_host.screenshot()
                        original_image = cv2.copyMakeBorder(input_obj['screencap_im_bgr'].copy(), 15, 15, 15, 15,cv2.BORDER_REPLICATE)
                        original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                        input_obj["original_image"] = original_image[15:-15, 15:-15]
                        input_obj['original_height'] = input_obj['screencap_im_bgr'].shape[0]
                        input_obj['original_width'] = input_obj['screencap_im_bgr'].shape[1]
                        input_obj['fixed_scale'] = False
                        system_inputs['python'] = input_obj
                else:
                    raise Exception('unimplemented target system: ' + target_system)
                script_logger.log('using input_obj', list(f'{k} {type(input_obj[k])}' for k in list(input_obj)))

            parallel_action["input_obj"] = input_obj
            (action_handler, action_handler_args) = script_executor.handle_action(parallel_action, lazy_eval=True)
            helper = ParallelizedScriptExecutorHelper(action_handler)
            script_logger.log('Started parallel process for ' + str(parallel_action["actionGroup"]))

            future = self.executor.submit(
                helper.handle_parallel_action,
                action_handler_args
            )
            parallel_action["parallel_process"] = process_index

            self.processes.append(future)
