import subprocess
import sys
import datetime

import pandas as pd

sys.path.append(".")

import numpy as np
import pyautogui
import random
import cv2
import glob
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from image_matcher import ImageMatcher
from script_engine_utils import is_null

import matplotlib.pyplot as plt
import time
from script_execution_state import ScriptExecutionState
from scipy.stats import truncnorm
from click_action_helper import ClickActionHelper
from detect_scene_helper import DetectSceneHelper
from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_engine_utils import generate_context_switch_action

KEYBOARD_KEYS = set(pyautogui.KEYBOARD_KEYS)

class python_host:
    def __init__(self, props):
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height
        self.props = props
        self.image_matcher = ImageMatcher()
        height,width,_ = np.array(pyautogui.screenshot()).shape
        if (not is_null(self.props['width']) and (self.props['width'] != width)) or \
                (not is_null(self.props['height']) and self.props['height'] != height):
            print('python host dims mismatch, expected : ', self.props['height'], self.props['width'],
                  'observed :', height, width)
        self.props['width'] = width
        self.props['height'] = height

    def run_script(self, action, state):
        # print('run_script: ', action)
        if action["actionData"]["awaitScript"]:
            outputs = subprocess.run(action["actionData"]["shellScript"], cwd="/", shell=True, capture_output=True)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            # print('output : ', outputs, 'state : ', state)
            return state
        else:
            proc = subprocess.Popen(action["actionData"]["shellScript"], cwd="/", shell=True)
            return state

    def screenshot(self):
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)


    def handle_action(self, action, state, context, log_level, log_folder):
        # print('inside host', self.width, self.height)
        logs_path = log_folder + str(context['script_counter']) + '-' + action["actionName"] + '-'
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state), context
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state.copy())))
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "clickAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context)
            point_choice = (point_choice[0] * self.width / self.props['width'],point_choice[1] * self.height / self.props['height'])
            print(point_choice)
            delays = []
            if action["actionData"]["delayState"] == "active":
                if action["actionData"]["distType"] == 'normal':
                    mean = action["actionData"]["mean"]
                    stddev = action["actionData"]["stddev"]
                    mins = (np.repeat(action["actionData"]["min"], action["actionData"]["clickCount"]) - mean) / stddev
                    maxes = (np.repeat(action["actionData"]["max"], action["actionData"]["clickCount"]) - mean) / stddev
                    delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev) if action["actionData"]["clickCount"] > 1 else [truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)]

            for click_count in range(0, action["actionData"]["clickCount"]):
                pyautogui.click(x=point_choice[0], y=point_choice[1], button=action['actionData']['mouseButton'])
                time.sleep(delays[click_count])

            ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path)

            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "mouseScrollAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context)
            pyautogui.scroll(action["actionData"]["scrollDistance"])
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "keyboardAction":
            if action["actionData"]["keyboardActionType"] == "keyPress":
                if action["actionData"]["isHotKey"] == 'isHotKey':
                    pyautogui.hotkey(*action["actionData"]["keyboardExpression"].split(","))
                else:
                    is_escaped_char = False
                    escaped_char = ''
                    for char_index,expression_char in enumerate(action["actionData"]["keyboardExpression"]):
                        if is_escaped_char:
                            if expression_char == '}':
                                is_escaped_char = False
                                if escaped_char in KEYBOARD_KEYS:
                                    pyautogui.press(escaped_char)
                                else:
                                    print('eval : ', escaped_char)
                                    pyautogui.press(eval(escaped_char, state.copy()))
                                escaped_char = ''
                            else:
                                escaped_char += expression_char
                        elif expression_char == '{':
                            is_escaped_char = True
                        else:
                            pyautogui.press(expression_char)
            elif action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                if action["actionData"]["isHotKey"] == 'isHotKey':
                    hotKeyKeys = action["actionData"]["keyboardExpression"].split(",")
                    for hotKeyKey in hotKeyKeys:
                        pyautogui.keyDown(hotKeyKey)
                    time.sleep(RandomVariableHelper.get_rv_val(action))
                    for hotKeyKey in reversed(hotKeyKeys):
                        pyautogui.keyUp(hotKeyKey)
                else:
                    is_escaped_char = False
                    escaped_char = ''
                    keyPressKeys = []
                    for char_index,expression_char in enumerate(action["actionData"]["keyboardExpression"]):
                        if is_escaped_char:
                            if expression_char == '}':
                                is_escaped_char = False
                                keyPressKeys.append(escaped_char)
                                escaped_char = ''
                            else:
                                escaped_char += expression_char
                        elif expression_char == '{':
                            is_escaped_char = True
                        else:
                            keyPressKeys.append(expression_char)
                    for keyPressKey in keyPressKeys:
                        pyautogui.keyDown(keyPressKey)
                    time.sleep(RandomVariableHelper.get_rv_val(action))
                    for keyPressKey in keyPressKeys:
                        pyautogui.keyUp(keyPressKey)
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "detectScene":
            screencap_im = self.screenshot()
            matches,ssim_coeff = DetectSceneHelper.get_match(action, screencap_im, self.props["dir_path"], logs_path)
            if ssim_coeff > action["actionData"]["threshold"]:
                state[action["actionData"]["outputVarName"]] = matches
                return ScriptExecutionState.SUCCESS, state, context
            else:
                return ScriptExecutionState.FAILURE, state, context
        elif action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/
            if 'results_precalculated' in action['actionData'] and action['actionData']['results_precalculated']:
                if action['actionGroup'] == 31:
                    print(action['actionGroup'], 'update block', action["actionData"]["update_dict"])
                if 'state' in action["actionData"]["update_dict"]:
                    for key, value in action["actionData"]["update_dict"]["state"].items():
                        state[key] = value
                if 'context' in action["actionData"]["update_dict"]:
                    for key, value in action["actionData"]["update_dict"]["context"].items():
                        context[key] = value
                return_tuple = (action['actionData']['action_result'], state, context)
                action['actionData']['screencap_im_bgr'] = None
                action['actionData']['results_precalculated'] = False
                action['actionData']['update_dict'] = None
                print("'detectObject_4' in state",'detectObject_4' in state)
                return return_tuple
            screencap_im_bgr,match_point = DetectObjectHelper.get_detect_area(action, state)
            if screencap_im_bgr is None:
                print('screencap_im_bgr is None')
                if 'screencap_im_bgr' in action['actionData'] and action['actionData']['screencap_im_bgr'] is not None:
                    screencap_im_bgr = action['actionData']['screencap_im_bgr']
                    print('loading previous im')
                else:
                    screencap_im_bgr = self.screenshot()
                    print('loading new img')

            # print('props dims: ', (self.props['height'],  self.props['width']), ' im dims: ', screencap_im_bgr.shape)
            # exit(0)
            # print('imshape: ', np.array(screencap_im_rgb).shape, ' width: ', self.props['width'], ' height: ', self.props['height'])
            # if is_null(self.props['width']) or is_null(self.props['height']):
            #     pass
            # else:
            #     screencap_im_bgr = cv2.resize(screencap_im_bgr, (self.props['width'], self.props['height']), interpolation=cv2.INTER_LINEAR)
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)

            screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
            # screencap_search_bgr = cv2.cvtColor(screencap_search.copy(), cv2.COLOR_RGB2BGR)
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search_bgr)
            matches = self.image_matcher.template_match(
                action,
                screencap_im_bgr,
                screencap_search_bgr,
                action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                action["actionData"]["positiveExamples"][0]["outputMask"],
                action["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
                action['actionData']['detectorName'],
                logs_path,
                self.props["scriptMode"],
                match_point,
                output_cropping=action["actionData"]["maskLocation"] if
                    (action["actionData"]["maskLocation"] != 'null' and
                     "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                     ) else None,
                threshold=float(action["actionData"]["threshold"])
            )
            if len(matches) > 0:
                state, context, update_dict = DetectObjectHelper.append_to_run_queue(
                    action, state, context, matches,
                    action['actionData']['detect_run_type'] if 'detect_run_type' in action['actionData'] else 'normal'
                )
                action_result = ScriptExecutionState.SUCCESS
            else:
                update_dict = {}
                action_result = ScriptExecutionState.FAILURE

            if 'detect_run_type' in action['actionData'] and\
                    action['actionData']['detect_run_type'] == 'result_precalculation':
                action['actionData']['results_precalculated'] = True
                action['actionData']['update_dict'] = update_dict
                action['actionData']['action_result'] = action_result
                action['actionData']['detect_run_type'] = None
                context['action'] = action
            return action_result, state, context
        elif action["actionName"] == "randomVariable":
            delays = RandomVariableHelper.get_rv_val(action)
            state[action["actionData"]["outputVarName"]] = delays
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                # print(np.array(pyautogui.screenshot()).shape)
                # exit(0)
                log_image = self.screenshot()
                cv2.imwrite(logs_path + '-logImage.png', log_image)
                return ScriptExecutionState.SUCCESS, state, context
            else:
                print('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        elif action["actionName"] == "timeAction":
            state[action["actionData"]["outputVarName"]] = datetime.datetime.now()
            # self.state[action["actionData"]["outputVarName"]] = expression
            return ScriptExecutionState.SUCCESS, state, context
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)