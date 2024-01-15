import subprocess
import sys
import datetime
import json
import os
import asyncio
import base64
import shlex
import pandas as pd

sys.path.append("..")

import numpy as np
import pyautogui
import random
import cv2
import glob
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from image_matcher import ImageMatcher
from script_engine_utils import is_null, apply_state_to_cmd_str

import matplotlib.pyplot as plt
import time
from device_action_interpeter import DeviceActionInterpreter
from script_execution_state import ScriptExecutionState
from scipy.stats import truncnorm
from click_action_helper import ClickActionHelper
from detect_scene_helper import DetectSceneHelper
from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_engine_utils import generate_context_switch_action
from forward_detect_peek_helper import ForwardDetectPeekHelper


class python_host:
    def __init__(self, props):
        print('Initializing Python Host')
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height
        self.props = props
        self.image_matcher = ImageMatcher()
        height,width,_ = np.array(pyautogui.screenshot()).shape
        if (not is_null(self.props['width']) and (self.props['width'] != width)) or \
                (not is_null(self.props['height']) and self.props['height'] != height):
            print('Warning: python host dims mismatch, expected : ', self.props['height'], self.props['width'],
                  'observed :', height, width)
        self.props['width'] = width
        self.props['height'] = height

    def screenshot(self):
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

    def keyUp(self, key):
        pyautogui.keyUp(key)

    def keyDown(self, key):
        pyautogui.keyDown(key)

    def press(self, key):
        pyautogui.press(key)

    def hotkey(self, keys):
        print('keys : ', keys)
        pyautogui.hotkey(*keys)

    def click(self, x, y, button):
        if (self.width != self.props['width'] or self.height != self.props['height']):
            x = (self.width / self.props['width']) * x
            y = (self.height / self.props['height']) * y
            print('clickAction: adjusted coords for pyautogui', x, y)
        pyautogui.click(x=x, y=y, button=button)

    def run_script(self, action, state):
        # print('run_script: ', action)
        if action["actionData"]["openInNewWindow"]:

            run_command = "start cmd /K " + apply_state_to_cmd_str(action["actionData"]["shellScript"], state)
            print('shellScript-' + str(action["actionGroup"]), ' opening in new window run command : ', run_command)
            os.system(run_command)
            return state
        elif action["actionData"]["awaitScript"]:
            await_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)
            print('shellScript-' + str(action["actionGroup"]), ' running command ', await_command, ' and awaiting output')
            outputs = subprocess.run(await_command, cwd="/", shell=True, capture_output=True)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            state[action["actionData"]["returnCodeOutputVarName"]] = outputs.returncode
            print('shellScript-' + str(action["actionGroup"]), 'command output : ', outputs)
            return state
        else:
            process_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)
            print('shellScript-' + str(action["actionGroup"]), ' starting process ', process_command, ' without awaiting output')
            proc = subprocess.Popen(process_command, cwd="/", shell=True)
            return state


    def handle_action(self, action, state, context, run_queue, log_level, log_folder, lazy_eval=False):
        # print('inside host', self.width, self.height)
        logs_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'
        if action["actionName"] == "shellScript":
            return action, ScriptExecutionState.SUCCESS, self.run_script(action, state), context, run_queue, []
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state.copy())))
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "clickAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context, self.width, self.height)
            # print('debug', point_choice, self.width, self.height, self.props['width'])
            # point_choice = (point_choice[0] * self.width / self.props['width'],point_choice[1] * self.height / self.props['height'])
            print('clickAction-' + str(action["actionGroup"]), ' input: ', var_name, ' output : ', point_choice)
            delays = []
            if action["actionData"]["delayState"] == "active":
                if action["actionData"]["distType"] == 'normal':
                    mean = action["actionData"]["mean"]
                    stddev = action["actionData"]["stddev"]
                    mins = (np.repeat(action["actionData"]["min"], action["actionData"]["clickCount"]) - mean) / stddev
                    maxes = (np.repeat(action["actionData"]["max"], action["actionData"]["clickCount"]) - mean) / stddev
                    delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev) if action["actionData"]["clickCount"] > 1 else [truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)]

            ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path, log_level=log_level)
            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1], button=action['actionData']['mouseButton'])
                time.sleep(delays[click_count])



            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "mouseScrollAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context)
            pyautogui.scroll(action["actionData"]["scrollDistance"])
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(self, action, state, context)
            return action, status, state, context, run_queue, []
        elif action["actionName"] == "detectObject":
            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)


            if screencap_im_bgr is None:
                print('detectObject-' + str(action["actionGroup"]) + ' taking screenshot')
                screencap_im_bgr = self.screenshot()
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
                    log_level,
                    logs_path,
                    self.props['dir_path'],
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
                    log_level=log_level,
                    logs_path=logs_path,
                    dir_path=self.props['dir_path']
                )
                return action, status, state, context, run_queue, update_queue
        elif action["actionName"] == "randomVariable":
            delays = RandomVariableHelper.get_rv_val(action)
            state[action["actionData"]["outputVarName"]] = delays
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                # print(np.array(pyautogui.screenshot()).shape)
                # exit(0)
                log_image = self.screenshot()
                cv2.imwrite(logs_path + '-logImage.png', log_image)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                print('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)


@staticmethod
def parse_inputs(process_host, inputs):
    device_action = inputs[1]
    if device_action == 'screen_capture':
        screenshot = process_host.screenshot()
        _, buffer = cv2.imencode('.jpg', screenshot)
        byte_array = buffer.tobytes()
        base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
        return {
            "data": base64_encoded_string
        }
    elif device_action == "click":
        process_host.click(inputs[2], inputs[3], 'left')
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        # process_host.click_and_drag(inputs[2], inputs[3], inputs[4], inputs[5])
        print('click and drag not implemented on python host')
        return {
            "data" : "failure"
        }
    elif device_action == "send_keys":
        for c in inputs[2]:
            process_host.press(c)
        return {
            "data": "success"
        }


PROCESS_DELIMITER = '<--DEVICE-RESPONSE-->'

async def read_input():
    print("ADB CONTROLLER PROCESS: listening for input")
    process_python_host = None
    device_key = None
    while True:
        input_line = await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = shlex.split(input_line)
        print('ADB CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[0]
        elif device_key != inputs[0]:
            print('ADB CONTROLLER: device key mismatch ', device_key, inputs[0])
            continue
        if process_python_host is None:
            print('ADB CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            with open('adb-host-controller-{}-process.txt'.format(device_key.replace(':', '-')), 'w') as process_file:
                process_file.write(str(datetime.datetime.now()) + '\n')
                # process_file.write(json.dumps(adb_args) + '\n')
            process_python_host = python_host({
                "dir_path": "./",
                "width" : None,
                "height" : None,
                "scriptMode" : 'train'
            })
        if len(inputs) > 1:
            print(PROCESS_DELIMITER + json.dumps(parse_inputs(process_python_host, inputs)) + PROCESS_DELIMITER)

async def adb_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    asyncio.run(adb_controller_main())