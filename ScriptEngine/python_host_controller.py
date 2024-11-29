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
import re
from image_matcher import ImageMatcher
from script_engine_utils import is_null, apply_state_to_cmd_str, DummyFile
from typing import Callable, Dict, List, Tuple

import time
from color_compare_helper import ColorCompareHelper
from click_path_generator import ClickPathGenerator
from device_action_interpeter import DeviceActionInterpreter
from script_execution_state import ScriptExecutionState
from scipy.stats import truncnorm
from click_action_helper import ClickActionHelper
from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_logger import ScriptLogger,thread_local_storage
from script_action_log import ScriptActionLog


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
        self.click_path_generator = None

        self.xmax = self.width
        self.ymax = self.height

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

    def mouse_up(self, x, y, button):
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
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
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
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
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('scroll: adjusted coords for pyautogui', x, y, flush=True)
        pyautogui.moveTo(x, y)
        pyautogui.scroll(distance)

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
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('clickAction: adjusted coords for pyautogui', x, y, flush=True)
        pyautogui.click(x=x, y=y, button=button)

    def smooth_move(self, source_x, source_y, target_x, target_y, drag=False, button='left'):
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

    def draw_click_and_drag(self, thread_script_logger,
                            source_point, source_point_list,
                            target_point, target_point_list,
                            delta_x, delta_y):
        thread_local_storage.script_logger = thread_script_logger
        thread_script_logger.log('started draw click thread')
        delta_x = list(map(lambda x: (x / self.xmax) * self.width, delta_x))
        delta_y = list(map(lambda y: (y / self.ymax) * self.height, delta_y))

        ClickActionHelper.draw_click_and_drag(
            self.screenshot(),
            source_point, source_point_list,
            target_point, target_point_list,
            zip(delta_x, delta_y)
        )

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

    def handle_action(self, action, state, context, run_queue, lazy_eval=False) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List] | Tuple[Callable, Tuple]:
        self.initialize_host()
        update_queue = []
        if action["actionName"] == "detectObject":
            if not lazy_eval:
                input_obj = DetectObjectHelper.get_detect_area(action, state)
                if input_obj['screencap_im_bgr'] is None:
                    script_logger.log('No cached screenshot or input expression, taking screenshot')
                    screencap_im_bgr = self.screenshot()
                    script_logger.log('Storing original image')

                    input_obj['screencap_im_bgr'] = screencap_im_bgr
                    original_image = cv2.copyMakeBorder(screencap_im_bgr.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
                    original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                    input_obj["original_image"] = original_image[15:-15, 15:-15]

                    input_obj['original_height'] = screencap_im_bgr.shape[0]
                    input_obj['original_width'] = screencap_im_bgr.shape[1]
                    input_obj['fixed_scale'] = False
                action["input_obj"] = input_obj
            script_mode = self.props["scriptMode"]
            if lazy_eval:
                return DetectObjectHelper.handle_detect_object, (
                    action,
                    script_mode
                )
            else:
                handle_action_result = DetectObjectHelper.handle_detect_object(
                    action,
                    script_mode=script_mode
                )
                action, status, state, context, run_queue, update_queue = DetectObjectHelper.handle_detect_action_result(
                    self.io_executor, handle_action_result, state, context, run_queue
                )


        elif action["actionName"] == "mouseInteractionAction":
            point_choice, log_point_choice, point_list, log_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["sourceDetectTypeData"],
                action["actionData"]["sourceDetectTypeData"]["inputExpression"],
                action["actionData"]["sourcePointList"],
                state,
                self.width,
                self.height,
                1
            )
            script_logger.log('ADB CONTROLLER: starting draw click thread')
            thread_script_logger = script_logger.copy()
            self.io_executor.submit(
                self.draw_click,
                thread_script_logger,
                log_point_choice,
                log_point_list
            )

            if action["actionData"]["mouseActionType"] == "click":
                click_counts = int(action["actionData"]["clickCount"])
                if click_counts > 1 and action["actionData"]["betweenClickDelay"]:
                    delays = RandomVariableHelper.get_rv_val(
                        action["actionData"]["randomVariableTypeData"],
                        click_counts
                    )
                else:
                    delays = [0]
                for click_count in range(0, click_counts):
                    self.click(*point_choice, action["actionData"]["mouseButton"])
                    time.sleep(delays[click_count])

            elif action["actionData"]["mouseActionType"] == "mouseUp":
                if not context["mouse_down"]:
                    script_logger.log("mouseUp selected but no mouseDown to release")
                else:
                    self.mouse_up(context["last_mouse_position"][0], context["last_mouse_position"][1])
                    context["mouse_down"] = False
            elif action["actionData"]["mouseActionType"] == "mouseDown":
                context["mouse_down"] = True
                context["last_mouse_position"] = point_choice
                self.mouse_down(*point_choice)
            elif action["actionData"]["mouseActionType"] == "scroll":
                scroll_distance = action["actionData"]["scrollDistance"]
                self.scroll(*point_choice, scroll_distance)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "mouseMoveAction":
            source_point, log_source_point_choice, point_list, log_source_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["sourceDetectTypeData"],
                action["actionData"]["sourceDetectTypeData"]["inputExpression"],
                action["actionData"]["sourcePointList"],
                state,
                self.width,
                self.height,
                1
            )

            target_point, log_target_point_choice, point_list, log_target_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["targetDetectTypeData"],
                action["actionData"]["targetDetectTypeData"]["inputExpression"],
                action["actionData"]["targetPointList"],
                state,
                self.width,
                self.height,
                2
            )

            if action["actionData"]["dragMouse"]:
                drag_log = 'Dragging from {} to {}'.format(
                    str(source_point),
                    str(target_point)
                )

                script_logger.log(drag_log)
                delta_x, delta_y = self.click_and_drag(
                    source_point[0],
                    source_point[1],
                    target_point[0],
                    target_point[1],
                    mouse_up=action["actionData"]["releaseMouseOnCompletion"]
                )

                thread_script_logger = script_logger.copy()
                self.io_executor.submit(
                    self.draw_click_and_drag,
                    thread_script_logger,
                    log_source_point_choice,
                    log_source_point_list,
                    log_target_point_choice,
                    log_target_point_list,
                    delta_x,
                    delta_y
                )
            else:
                if context["mouse_down"]:
                    drag_log = 'Moving from {} to {} with mouse down'.format(
                        str(source_point),
                        str(target_point)
                    )

                    script_logger.log(drag_log)
                    delta_x, delta_y = self.click_and_drag(
                        source_point[0],
                        source_point[1],
                        target_point[0],
                        target_point[1],
                        mouse_up=action["actionData"]["releaseMouseOnCompletion"]
                    )

                    thread_script_logger = script_logger.copy()
                    self.io_executor.submit(
                        self.draw_click_and_drag,
                        thread_script_logger,
                        log_source_point_choice,
                        log_source_point_list,
                        log_target_point_choice,
                        log_target_point_list,
                        delta_x,
                        delta_y
                    )
                else:
                    drag_log = 'Moving from {} to {} with mouse up. Note mouse movement on Android has no effect'.format(
                        str(source_point),
                        str(target_point)
                    )
                    script_logger.log(drag_log)
                    context["last_mouse_position"] = target_point
            script_logger.get_action_log().add_supporting_file(
                'text',
                'drag-log.txt',
                drag_log
            )

            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "shellScript":
            state = self.run_shell_script(action, state)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(
                self, action, state, context
            )
        elif action["actionName"] == "colorCompareAction":
            input_obj = DetectObjectHelper.get_detect_area(
                action, state, output_type='matched_pixels'
            )
            if input_obj['screencap_im_bgr'] is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.screenshot()
                input_obj['screencap_im_bgr'] = screencap_im_bgr
                original_image = cv2.copyMakeBorder(screencap_im_bgr.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
                original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                input_obj["original_image"] = original_image[15:-15, 15:-15]

                input_obj['original_height'] = screencap_im_bgr.shape[0]
                input_obj['original_width'] = screencap_im_bgr.shape[1]
                input_obj['fixed_scale'] = False
            action["input_obj"] = input_obj

            color_score = ColorCompareHelper.handle_color_compare(action)
            if color_score > float(action['actionData']['threshold']):
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction successful. Color Score of {} was above threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction failed. Color Score of {} was below threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                status = ScriptExecutionState.FAILURE
        elif action["actionName"] == "dragLocationSource":
            point_choice, point_list, state, context = ClickActionHelper.get_point_choice(
                action, action['actionData']['inputExpression'], state, context,
                self.width, self.height
            )
            context["dragLocationSource"] = {
                'point_choice' : point_choice,
                'point_list' : point_list
            }
            thread_script_logger = script_logger.copy()
            self.io_executor.submit(self.draw_click, thread_script_logger, point_choice, point_list)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "dragLocationTarget":
            source_point = context["dragLocationSource"]["point_choice"]
            source_point_list = context["dragLocationSource"]["point_list"]
            target_point, target_point_list, state, context = ClickActionHelper.get_point_choice(
                action, action['actionData']['inputExpression'], state, context,
                self.width, self.height
            )
            drag_log = 'Dragging from {} to {}'.format(
                str(source_point),
                str(target_point)
            )
            script_logger.log(drag_log)
            delta_x, delta_y = self.click_and_drag(source_point[0], source_point[1], target_point[0], target_point[1])
            thread_script_logger = script_logger.copy()
            self.io_executor.submit(
                self.draw_click_and_drag,
                thread_script_logger,
                source_point,
                source_point_list,
                target_point,
                target_point_list,
                delta_x,
                delta_y
            )
            script_logger.get_action_log().add_supporting_file(
                'text',
                'drag-log.txt',
                drag_log
            )
            status = ScriptExecutionState.SUCCESS
        #TODO: deprecated
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                log_image = self.screenshot()
                cv2.imwrite(script_logger.get_log_path_prefix() + '-logImage.png', log_image)
                status = ScriptExecutionState.SUCCESS
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
            status = ScriptExecutionState.SUCCESS
        else:
            exception_text = "action unimplemented on python/desktop " + action["actionName"]
            script_logger.log(exception_text)
            raise Exception(exception_text)
        return action, status, state, context, run_queue, update_queue

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
            process_python_host = python_host({
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