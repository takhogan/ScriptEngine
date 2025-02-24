import subprocess
import sys
import datetime
import json
import os
import asyncio
import base64


import numpy as np
import pyautogui 
import cv2
from ScriptEngine.common.script_engine_utils import is_null, DummyFile
from typing import Callable, Dict, List, Tuple
import time

from ..helpers.color_compare_helper import ColorCompareHelper
from ..helpers.click_path_generator import ClickPathGenerator
from ..helpers.device_action_interpreter import DeviceActionInterpreter
from ScriptEngine.common.enums import ScriptExecutionState
from ..helpers.click_action_helper import ClickActionHelper
from ..helpers.detect_object_helper import DetectObjectHelper
from ..helpers.random_variable_helper import RandomVariableHelper
from ScriptEngine.common.logging.script_logger import ScriptLogger,thread_local_storage
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from .device_manager import DeviceManager

script_logger = ScriptLogger()
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

class DesktopDeviceManager(DeviceManager):
    def __init__(self, props, input_source=None):
        script_logger.log('Initializing Python Host')
        self.width = None
        self.height = None
        self.props = props
        self.click_path_generator = None

        self.xmax = self.width
        self.ymax = self.height

        if input_source is not None:
            self.dummy_mode = True
            self.input_source = input_source
        else:
            self.dummy_mode = False
        

    def ensure_device_initialized(self):
        if self.width is None or self.height is None:
            if self.dummy_mode:
                self.width = self.input_source["width"]
                self.props['width'] = self.width
                self.height = self.input_source["height"]
                self.props['height'] = self.height
                script_logger.log('PythonHostController: script in dummy mode, initialized to input source')
                return
            script_logger.log('PythonHostController: Taking screenshot to initialize python host')
            host_dimensions = pyautogui.size()
            self.width = host_dimensions.width
            self.height = host_dimensions.height
            self.xmax = self.width
            self.ymax = self.height
            height, width, _ = np.array(pyautogui.screenshot()).shape
            if (not is_null(self.props['width']) and (self.props['width'] != width)) or \
                    (not is_null(self.props['height']) and self.props['height'] != height):
                script_logger.log('Warning: python host dims mismatch, expected : ', self.props['height'],
                                  self.props['width'],
                                  'observed :', height, width)
            self.props['width'] = width
            self.props['height'] = height
            self.click_path_generator = ClickPathGenerator(2, 3, self.width, self.height, 45, 0.4)

    def screenshot(self):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning screenshot from input source')
            return self.input_source['screenshot']()
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

    def keyUp(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from keyUp')
        pyautogui.keyUp(key)

    def keyDown(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from keyDown')
        pyautogui.keyDown(key)

    def keyPress(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from press')
        pyautogui.press(key)

    def hotkey(self, keys):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from hotKey')
        pyautogui.hotkey(*keys)

    def mouse_up(self, x, y, button):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from mouse_up')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('mouse_up: adjusted coords for pyautogui', x, y, flush=True)
        current_position = pyautogui.position()
        if current_position != (x, y):
            self.smooth_move(*current_position, x, y)
        pyautogui.mouseUp(x=x, y=y, button=button)


    def mouse_down(self, x, y, button):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from mouse_down')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('mouse_down: adjusted coords for pyautogui', x, y, flush=True)
        current_position = pyautogui.position()
        if current_position != (x, y):
            self.smooth_move(*current_position, x, y)
        pyautogui.mouseDown(x=x, y=y, button=button)


    def scroll(self, x, y, distance):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('scroll: adjusted coords for pyautogui', x, y, flush=True)
        pyautogui.moveTo(x, y)
        pyautogui.scroll(distance)


    def click(self, x, y, button):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('clickAction: adjusted coords for pyautogui', x, y, flush=True)
        pyautogui.click(x=x, y=y, button=button)

    def smooth_move(self, source_x, source_y, target_x, target_y, drag=False, button='left'):
        self.ensure_device_initialized()
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     source_x = (self.width / self.props['width']) * source_x
        #     source_y = (self.height / self.props['height']) * source_y
        #     target_x = (self.width / self.props['width']) * target_x
        #     target_y = (self.height / self.props['height']) * target_y
        #     script_logger.log('smooth_move: adjusted coords for pyautogui', source_x, source_y, target_x, target_y, flush=True)
        frac_source_x = (source_x / self.width)
        frac_target_x = (target_x / self.width)
        frac_source_y = (source_y / self.height)
        frac_target_y = (target_y / self.height)
        delta_x, delta_y = self.click_path_generator.generate_click_path(
            frac_source_x, frac_source_y,
            frac_target_x, frac_target_y
        )
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click and drag returning')
            return delta_x, delta_y

        traverse_x = source_x
        traverse_y = source_y
        script_logger.log('delta_x', delta_x, 'delta_y', delta_y)
        for delta_pair in zip(delta_x, delta_y):
            if drag and sys.platform == 'darwin':
                pyautogui.dragTo(
                    traverse_x + delta_pair[0],
                    traverse_y + delta_pair[1],
                    button=button,
                    mouseDownUp=False
                )
            else:
                pyautogui.moveTo(traverse_x + delta_pair[0], traverse_y + delta_pair[1])
            traverse_x += delta_pair[0]
            traverse_y += delta_pair[1]
        return delta_x, delta_y

    def click_and_drag(self, source_x, source_y, target_x, target_y, mouse_down=True, mouse_up=True):
        self.ensure_device_initialized()
        script_logger.log('pyautogui size', pyautogui.size())
        script_logger.log(
            'moving from initial position {} to click and drag start {}'.format(
                str(pyautogui.position()), str((source_x, source_y))
            )
        )

        if mouse_down:
            self.mouse_down(source_x, source_y, button='left')
        delta_x, delta_y = self.smooth_move(source_x, source_y, target_x, target_y, drag=True, button='left')
        if mouse_up:
            self.mouse_up(target_x, target_y, button='left')
        return delta_x, delta_y
    
    def start_device(self):
        return super().start_device()
    
    def stop_device(self):
        return super().stop_device()

    

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
        process_host.ensure_device_initialized()
        script_logger.log('clicked location', inputs[3], inputs[4], flush=True)
        process_host.click(int(float(inputs[3])), int(float(inputs[4])), 'left')
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        # process_host.click_and_drag(inputs[3], inputs[4], inputs[5], inputs[6])
        script_logger.log('click and drag not implemented on python host')
        process_host.ensure_device_initialized()
        return {
            "data" : "failure"
        }
    elif device_action == "send_keys":
        DeviceActionInterpreter.parse_keyboard_action(
            process_host, json.loads(inputs[3]), {}, {}
        )
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
        inputs = input_line.strip().split('###')
        inputs = inputs[0:2] + inputs[2].split(' ')
        script_logger.log('PYTHON CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[1]
        elif device_key != inputs[1]:
            script_logger.log('PYTHON CONTROLLER: device key mismatch ', device_key, inputs[1])
            continue
        if process_python_host is None:
            script_logger.set_log_file_path('./logs/{}-python-host-controller-{}-process.txt'.format(formatted_today, device_key.replace(':', '-')))
            script_logger.log('PYTHON CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            script_logger.log('PYTHON CONTROLLER PROCESS: processing inputs ', inputs)
            script_logger.set_log_header('{}-python-host-controller-{}-process'.format(formatted_today, device_key.replace(':', '-')))
            script_logger.set_action_log(ScriptActionLog(
                {
                    'actionName' : 'configurationAction',
                    'actionGroup' : 0,
                    'actionData' : {
                        'targetSystem': 'python'
                    }
                },
                script_logger.get_log_folder(),
                script_logger.get_log_header(),
                0
            ))
            process_python_host = DesktopDeviceManager({
                "dir_path": "./",
                "width" : None,
                "height" : None,
                "scriptMode" : 'train'
            }, None)
        if len(inputs) > 1:
            try:
                script_logger.log('<--{}-->'.format(inputs[0]) + json.dumps(parse_inputs(process_python_host, inputs)) + '<--{}-->'.format(inputs[0]), file=DummyFile(), flush=True)
                script_logger.log('PYTHON CONTROLLER: Response sent for {}'.format(inputs[0]), flush=True)
            except pyautogui.FailSafeException as e:
                script_logger.log('PYTHON CONTROLLER PROCESS: fail safe exception triggered', e)

async def python_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    script_logger.set_log_file_path('./logs/{}-python-host-main.txt'.format(formatted_today))
    script_logger.set_log_header('{}-python-host-main-'.format(formatted_today))
    script_logger.set_log_folder('./logs/')
    os.makedirs('./logs', exist_ok=True)
    asyncio.run(python_controller_main())