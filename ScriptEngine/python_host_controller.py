import subprocess
import sys
import datetime
import json
import os
import asyncio
import base64
import shlex

sys.path.append("..")

import numpy as np
import pyautogui
import cv2
from image_matcher import ImageMatcher
from script_engine_utils import is_null, apply_state_to_cmd_str, DummyFile

import time
from color_compare_helper import ColorCompareHelper
from device_action_interpeter import DeviceActionInterpreter
from script_execution_state import ScriptExecutionState
from scipy.stats import truncnorm
from click_action_helper import ClickActionHelper
from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from forward_detect_peek_helper import ForwardDetectPeekHelper
from script_logger import ScriptLogger,thread_local_storage

script_logger = ScriptLogger()
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

class python_host:
    def __init__(self, props, io_executor, input_source=None):
        script_logger.log('Initializing Python Host')
        self.width = None
        self.height = None
        self.props = props
        self.io_executor = io_executor
        self.image_matcher = ImageMatcher()

        if input_source is not None:
            self.dummy_mode = True
            self.input_source = input_source
            self.width = input_source["width"]
            self.props['width'] = self.width
            self.height = input_source["height"]
            self.props['height'] = self.height
        else:
            self.dummy_mode = False

    def initialize_host(self):
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from intialize host')
            return
        if self.width is None or self.height is None:
            script_logger.log('PythonHostController: Taking screenshot to initialize python host')
            host_dimensions = pyautogui.size()
            self.width = host_dimensions.width
            self.height = host_dimensions.height
            height, width, _ = np.array(pyautogui.screenshot()).shape
            if (not is_null(self.props['width']) and (self.props['width'] != width)) or \
                    (not is_null(self.props['height']) and self.props['height'] != height):
                script_logger.log('Warning: python host dims mismatch, expected : ', self.props['height'],
                                  self.props['width'],
                                  'observed :', height, width)
            self.props['width'] = width
            self.props['height'] = height

    def screenshot(self):
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning screenshot from input source')
            return self.input_source['screenshot']()
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

    def keyUp(self, key):
        pyautogui.keyUp(key)

    def keyDown(self, key):
        pyautogui.keyDown(key)

    def press(self, key):
        pyautogui.press(key)

    def hotkey(self, keys):
        script_logger.log('keys : ', keys)
        pyautogui.hotkey(*keys)

    def draw_click(self, thread_script_logger, point_choice, point_list):
        thread_local_storage.script_logger = thread_script_logger
        thread_script_logger.log('started draw click thread')
        ClickActionHelper.draw_click(
            self.screenshot(), point_choice, point_list
        )

    def click(self, x, y, button):
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        if (self.width != self.props['width'] or self.height != self.props['height']):
            x = (self.width / self.props['width']) * x
            y = (self.height / self.props['height']) * y
            script_logger.log('clickAction: adjusted coords for pyautogui', x, y, flush=True)
        pyautogui.click(x=x, y=y, button=button)

    def run_shell_script(self, action, state):
        pre_log = 'Running Shell Script: {}'.format(action["actionData"]["shellScript"])
        script_logger.log(pre_log)
        pre_log_2 = 'Shell Script options: openinNewWindow: {} awaitScript: {}'.format(
            str(action["actionData"]["openInNewWindow"]),
            str(action["actionData"]["awaitScript"])
        )
        script_logger.log(pre_log_2)
        if action["actionData"]["openInNewWindow"]:
            run_command = "start cmd /K " + apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using os.system'.format(run_command)
            script_logger.log(mid_log)

            outputs = os.system(run_command)

            post_log = 'Command completed successfully'
            script_logger.log(post_log)

            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            state[action["actionData"]["returnCodeOutputVarName"]] = outputs.returncode


        elif action["actionData"]["awaitScript"]:
            await_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using subprocess.run cwd="/", shell=True, capture_output=True'.format(
                await_command
            )
            script_logger.log(mid_log)

            outputs = subprocess.run(await_command, cwd="/", shell=True, capture_output=True)

            post_log = 'Command completed successfully'
            script_logger.log(post_log)

            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            state[action["actionData"]["returnCodeOutputVarName"]] = outputs.returncode

        else:
            process_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using subprocess.Popen cwd="/", shell=True'.format(
                process_command
            )
            script_logger.log(mid_log)
            proc = subprocess.Popen(process_command, cwd="/", shell=True)

            post_log = 'Command process started successfully'
            script_logger.log(post_log)
        script_logger.get_action_log().add_post_file(
            'text',
            'shellScript-log.txt',
            pre_log + '\n' + pre_log_2 + '\n' + mid_log + '\n' + post_log
        )
        return state


    def handle_action(self, action, state, context, run_queue, lazy_eval=False):
        self.initialize_host()
        if action["actionName"] == "shellScript":
            return action, ScriptExecutionState.SUCCESS, self.run_shell_script(action, state), context, run_queue, []
        elif action["actionName"] == "clickAction":
            action["actionData"]["clickCount"] = int(action["actionData"]["clickCount"])
            var_name = action["actionData"]["inputExpression"]
            point_choice, point_list, state, context = ClickActionHelper.get_point_choice(
                action, var_name, state, context,
                self.width, self.height
            )
            delays = [0] * action["actionData"]["clickCount"]
            if action["actionData"]["delayState"] == "active":
                delays = RandomVariableHelper.get_rv_val(action, action["actionData"]["clickCount"])
            thread_script_logger = script_logger.copy()
            self.io_executor.submit(self.draw_click, thread_script_logger, point_choice, point_list)
            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1])
                time.sleep(delays[click_count] if click_count > 1 else delays)

            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "mouseScrollAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, point_list, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context)

            if script_logger.get_log_level() == 'info':
                ClickActionHelper.draw_click(
                    self.screenshot(), point_choice, point_list
                )
            pyautogui.scroll(action["actionData"]["scrollDistance"])
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(
                self, action, state, context
            )
            return action, status, state, context, run_queue, []
        elif action["actionName"] == "detectObject":
            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)


            if screencap_im_bgr is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.screenshot()

            if script_logger.get_log_level() == 'info':
                input_image_relative_path = 'detectObject-inputImage.png'
                cv2.imwrite(script_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
                script_logger.get_action_log().set_pre_file(
                    'image',
                    input_image_relative_path
                )

            if lazy_eval:
                return DetectObjectHelper.handle_detect_object, (
                    action,
                    screencap_im_bgr,
                    state,
                    context,
                    run_queue,
                    match_point,
                    check_image_scale,
                    self.props['scriptMode'],
                    True
                )
            else:
                action, status, state, context, run_queue, update_queue = DetectObjectHelper.handle_detect_object(
                    action,
                    screencap_im_bgr,
                    state,
                    context,
                    run_queue,
                    match_point=match_point,
                    check_image_scale=check_image_scale,
                    script_mode=self.props['scriptMode'],
                )
                return action, status, state, context, run_queue, update_queue
        elif action["actionName"] == "colorCompareAction":
            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(
                action, state, output_type='matched_pixels'
            )
            if screencap_im_bgr is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.screenshot()

            if script_logger.get_log_level() == 'info':
                input_image_relative_path = script_logger.get_log_header() + '-colorCompareAction-inputImage.png'
                cv2.imwrite(script_logger.get_log_folder() + input_image_relative_path, screencap_im_bgr)
                script_logger.get_action_log().set_pre_file(
                    'image',
                    input_image_relative_path
                )

            color_score = ColorCompareHelper.handle_color_compare(screencap_im_bgr, action, state)
            if color_score > float(action['actionData']['threshold']):
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction successful. Color Score of {} was above threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction failed. Color Score of {} was below threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                return action, ScriptExecutionState.FAILURE, state, context, run_queue, []
        #TODO: deprecated
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                log_image = self.screenshot()
                cv2.imwrite(script_logger.get_log_path_prefix() + '-logImage.png', log_image)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                exception_text = 'log type unimplemented ' + action["actionData"]["logType"]
                script_logger.log(exception_text)
                raise Exception(exception_text)
        # TODO: deprecated
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        else:
            exception_text = "action unimplemented on python/desktop " + action["actionName"]
            script_logger.log(exception_text)
            raise Exception(exception_text)


@staticmethod
def parse_inputs(process_host, inputs):
    device_action = inputs[2]
    if device_action == 'screen_capture':
        screenshot = process_host.screenshot()
        _, buffer = cv2.imencode('.jpg', screenshot)
        byte_array = buffer.tobytes()
        base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
        return {
            "data": base64_encoded_string
        }
    elif device_action == "click":
        process_host.initialize_host()
        script_logger.log('clicked location', inputs[3], inputs[4], flush=True)
        process_host.click(int(float(inputs[3])), int(float(inputs[4])), 'left')
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        # process_host.click_and_drag(inputs[3], inputs[4], inputs[5], inputs[6])
        script_logger.log('click and drag not implemented on python host')
        process_host.initialize_host()
        return {
            "data" : "failure"
        }
    elif device_action == "send_keys":
        for c in inputs[3]:
            process_host.press(c)
        return {
            "data": "success"
        }



async def read_input():
    script_logger.log("PYTHON CONTROLLER PROCESS: listening for input")
    process_python_host = None
    device_key = None
    while True:
        input_line = await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = shlex.split(input_line)
        script_logger.log('PYTHON CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[1]
        elif device_key != inputs[1]:
            script_logger.log('PYTHON CONTROLLER: device key mismatch ', device_key, inputs[1])
            continue
        if process_python_host is None:
            script_logger.set_log_file_path('./logs/{}-python-host-controller-{}-process.txt'.format(formatted_today, device_key.replace(':', '-')))
            script_logger.set_log_header('')
            script_logger.log('PYTHON CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            script_logger.log('PYTHON CONTROLLER PROCESS: processing inputs ', inputs)
            process_python_host = python_host({
                "dir_path": "./",
                "width" : None,
                "height" : None,
                "scriptMode" : 'train'
            }, None)
        if len(inputs) > 1:
            try:
                script_logger.log('<--{}-->'.format(inputs[0]) + json.dumps(parse_inputs(process_python_host, inputs)) + '<--{}-->'.format(inputs[0]) , file=DummyFile(),flush=True)
                script_logger.log('ADB CONTROLLER: Response sent for {}'.format(inputs[0]), flush=True)
            except pyautogui.FailSafeException as e:
                script_logger.log('PYTHON CONTROLLER PROCESS: fail safe exception triggered', e)

async def python_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    script_logger.set_log_file_path('./logs/{}-python-host-main.txt'.format(formatted_today))
    script_logger.set_log_header('')
    os.makedirs('./logs', exist_ok=True)
    asyncio.run(python_controller_main())