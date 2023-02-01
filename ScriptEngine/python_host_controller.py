import subprocess
import sys
import datetime
import os

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
from forward_detect_peek_helper import ForwardDetectPeekHelper

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
            print('Warning: python host dims mismatch, expected : ', self.props['height'], self.props['width'],
                  'observed :', height, width)
        self.props['width'] = width
        self.props['height'] = height

    def run_script(self, action, state):
        # print('run_script: ', action)
        if action["actionData"]["openInNewWindow"]:
            run_command = "start cmd /K " + action["actionData"]["shellScript"]
            print('shellScript-' + str(action["actionGroup"]), ' opening in new window run command : ', run_command)
            os.system(run_command)
            return state
        elif action["actionData"]["awaitScript"]:
            print('shellScript-' + str(action["actionGroup"]), ' running command ', action["actionData"]["shellScript"], ' and awaiting output')
            outputs = subprocess.run(action["actionData"]["shellScript"], cwd="/", shell=True, capture_output=True)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            # print('output : ', outputs, 'state : ', state)
            return state
        else:
            print('shellScript-' + str(action["actionGroup"]), ' starting process ', action["actionData"]['shellScript'], ' without awaiting output')
            proc = subprocess.Popen(action["actionData"]["shellScript"], cwd="/", shell=True)
            return state

    def screenshot(self):
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)


    def handle_action(self, action, state, context, log_level, log_folder):
        # print('inside host', self.width, self.height)
        logs_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state), context
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state.copy())))
            return ScriptExecutionState.SUCCESS, state, context
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

            ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path)
            for click_count in range(0, action["actionData"]["clickCount"]):
                pyautogui.click(x=point_choice[0], y=point_choice[1], button=action['actionData']['mouseButton'])
                time.sleep(delays[click_count])



            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "mouseScrollAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice, state, context = ClickActionHelper.get_point_choice(action, var_name, state, context)
            pyautogui.scroll(action["actionData"]["scrollDistance"])
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "keyboardAction":
            if action["actionData"]["keyboardActionType"] == "keyPress":
                print('keyboard-expression-' + str(action["actionGroup"]), ' : ',
                      action["actionData"]["keyboardActionType"], ' : ',
                      action["actionData"]["keyboardExpression"])
                if action["actionData"]["isHotKey"] == 'isHotKey':
                    pyautogui.hotkey(*action["actionData"]["keyboardExpression"].split(","))
                else:
                    is_escaped_char = False
                    escaped_char = ''
                    for char_index,expression_char in enumerate(str(action["actionData"]["keyboardExpression"])):
                        if is_escaped_char:
                            if expression_char == '}':
                                is_escaped_char = False
                                if escaped_char in KEYBOARD_KEYS:
                                    pyautogui.press(escaped_char)
                                else:
                                    eval_expression = str(eval(escaped_char, state.copy()))
                                    for eval_expression_char in eval_expression:
                                        pyautogui.press(eval_expression_char)
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
        # elif action["actionName"] == "detectScene":
        #     forward_peek_result = ForwardDetectPeekHelper.load_forward_peek_result(action, state, context)
        #     if forward_peek_result is not None:
        #         return forward_peek_result
        #
        #     # screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
        #     screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, None)
        #     if screencap_im_bgr is None:
        #         screencap_im_bgr = self.screenshot()
        #
        #     matches, ssim_coeff = DetectSceneHelper.get_match(
        #         action,
        #         screencap_im_bgr.copy(),
        #         action["actionData"]["positiveExamples"][0]["img"],
        #         action["actionData"]["positiveExamples"][0]["mask"],
        #         action["actionData"]["positiveExamples"][0]["mask_single_channel"],
        #         self.props["dir_path"],
        #         logs_path,
        #         output_cropping=action["actionData"]["maskLocation"] if
        #         (action["actionData"]["maskLocation"] != 'null' and
        #          "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
        #          ) else None,
        #     )
        #     if ssim_coeff > action["actionData"]["threshold"]:
        #         state[action["actionData"]["outputVarName"]] = matches
        #         action_result = ScriptExecutionState.SUCCESS
        #     else:
        #         action_result = ScriptExecutionState.FAILURE
        #     action, context = ForwardDetectPeekHelper.save_forward_peek_results(action, {}, action_result, context)
        #     return action_result, state, context

        elif action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/

            forward_peek_result = ForwardDetectPeekHelper.load_forward_peek_result(action, state, context)
            if forward_peek_result is not None:
                return forward_peek_result

            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)
            if screencap_im_bgr is None:
                screencap_im_bgr = self.screenshot()


            screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + '-search_img.png', screencap_search_bgr)
            is_detect_object_first_match = (
                        action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
                    'matchMode'] == 'firstMatch')

            if is_detect_object_first_match or \
                    action['actionData']['detectActionType'] == 'detectScene':
                matches, ssim_coeff = DetectSceneHelper.get_match(
                    action,
                    screencap_im_bgr.copy(),
                    action["actionData"]["positiveExamples"][0]["sceneimg"],
                    action["actionData"]["positiveExamples"][0]["scenemask"],
                    action["actionData"]["positiveExamples"][0]["scenemask_single_channel"],
                    action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                    action["actionData"]["positiveExamples"][0]["outputMask"],
                    self.props["dir_path"],
                    logs_path,
                    output_cropping=action["actionData"]["maskLocation"] if
                    (action["actionData"]["maskLocation"] != 'null' and
                     "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                    ) else None
                )

            if (action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
                'matchMode'] == 'bestMatch') or \
                    (is_detect_object_first_match and ssim_coeff < action['actionData']['threshold']):
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
                    check_image_scale=check_image_scale,
                    output_cropping=action["actionData"]["maskLocation"] if
                    (action["actionData"]["maskLocation"] != 'null' and
                     "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                     ) else None,
                    threshold=float(action["actionData"]["threshold"]),
                    use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
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

            action, context = ForwardDetectPeekHelper.save_forward_peek_results(action, update_dict, action_result, context)
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
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            return ScriptExecutionState.SUCCESS, state, context
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)