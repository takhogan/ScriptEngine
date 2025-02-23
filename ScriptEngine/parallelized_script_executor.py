import sys
import pickle
import time
import cv2
from .helpers.detect_object_helper import DetectObjectHelper
from ScriptEngine.common.logging.script_logger import ScriptLogger
from .helpers.parallelized_script_executor_helper import ParallelizedScriptExecutorHelper
script_logger = ScriptLogger()
from .device_controller import DeviceController
from .custom_process_pool import CustomProcessPool



class ParallelizedScriptExecutor:
    def __init__(self, device_controller : DeviceController, process_executor : CustomProcessPool):
        self.device_controller = device_controller
        self.process_executor = process_executor
        self.processes = {}

    def clear_processes(self):
        for _, process in self.processes.items():
            process.cancel()
        self.processes = {}

    def get_process(self, action_group):
        if action_group in self.processes:
            return self.processes[action_group]
        else:
            return None

    def start_processes(self, script_executor, parallel_actions):
        self.processes = {}
        parent_action_log = script_executor.parent_action_log
        script_logger.log('CONTROL FLOW: starting parallel execution')
        # if you want to implement for other actions keep in mind you should filter here
        system_inputs = {}
        for process_index,parallel_action in enumerate(parallel_actions):
            script_logger.log('Creating parallel process for ' + str(parallel_action["actionGroup"]))
            script_executor.context["script_counter"] += 1
            action_log = script_logger.configure_action_logger(parallel_action, script_executor.context["script_counter"], parent_action_log)
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
                if target_system in system_inputs:
                    input_obj = system_inputs[target_system]
                else:
                    input_obj['screencap_im_bgr'] = self.device_controller.get_device_action(target_system, 'screenshot')()
                    original_image = cv2.copyMakeBorder(input_obj['screencap_im_bgr'].copy(), 15, 15, 15, 15,cv2.BORDER_REPLICATE)
                    original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                    input_obj["original_image"] = original_image[15:-15, 15:-15]
                    input_obj['original_height'] = input_obj['screencap_im_bgr'].shape[0]
                    input_obj['original_width'] = input_obj['screencap_im_bgr'].shape[1]
                    input_obj['fixed_scale'] = False
                    system_inputs[target_system] = input_obj
                
            script_logger.log('Generating parallel action handler for ' + str(parallel_action["actionGroup"]))
            parallel_action["input_obj"] = input_obj
            (action_handler, action_handler_args) = script_executor.handle_action(parallel_action, lazy_eval=True)
            helper = ParallelizedScriptExecutorHelper(action_handler)
            script_logger.log('Started parallel process for ' + str(parallel_action["actionGroup"]))

            future = self.process_executor.submit(
                helper.handle_parallel_action,
                action_handler_args
            )

            script_logger.log('Parallel process submitted to pool for ' + str(parallel_action["actionGroup"]))

            self.processes[parallel_action["actionGroup"]] = future
