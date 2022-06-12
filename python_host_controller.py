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

class python_host:
    def __init__(self, props):
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height
        self.props = props
        self.image_matcher = ImageMatcher()
        if is_null(self.props['width']) or is_null(self.props['height']):
            self.props['height'],self.props['width'],_ = pyautogui.screenshot().shape

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
        # print(action["actionName"])
        time.sleep(1)
        # print('inside host', self.width, self.height)
        logs_path = log_folder + str(context['script_counter']) + '-' + action["actionName"] + '-'
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state), context
        elif action["actionName"] == "sleepStatement":
            time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state)))
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
                pyautogui.click(point_choice)
                time.sleep(delays[click_count])

                ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path)

            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "keyboardAction":
            if action["actionData"]["isHotKey"] == 'isHotKey':
                pyautogui.hotkey(*action["actionData"]["keyboardExpression"].split(","))
            else:
                is_escaped_char = False
                escaped_char = ''
                for char_index,expression_char in enumerate(action["actionData"]["keyboardExpression"]):
                    if is_escaped_char:
                        if expression_char == '}':
                            is_escaped_char = False
                            pyautogui.press(escaped_char)
                            escaped_char = ''
                        else:
                            escaped_char += expression_char
                    elif expression_char == '{':
                        is_escaped_char = True
                    else:
                        pyautogui.press(expression_char)
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
            screencap_im_bgr,match_point = DetectObjectHelper.get_detect_area(action, state)
            if screencap_im_bgr is None:
                screencap_im_bgr = self.screenshot()

            # print('props dims: ', (self.props['height'],  self.props['width']), ' im dims: ', screencap_im_bgr.shape)
            # exit(0)
            # print('imshape: ', np.array(screencap_im_rgb).shape, ' width: ', self.props['width'], ' height: ', self.props['height'])
            # if is_null(self.props['width']) or is_null(self.props['height']):
            #     pass
            # else:
            #     screencap_im_bgr = cv2.resize(screencap_im_bgr, (self.props['width'], self.props['height']), interpolation=cv2.INTER_LINEAR)
            screencap_mask_bgr = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)

            screencap_search_bgr = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])

            # screencap_search_bgr = cv2.cvtColor(screencap_search.copy(), cv2.COLOR_RGB2BGR)
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search_bgr)
            matches = self.image_matcher.template_match(
                screencap_im_bgr,
                screencap_mask_bgr,
                screencap_search_bgr,
                action['actionData']['detectorName'],
                logs_path,
                self.props["scriptMode"],
                match_point,
                threshold=float(action["actionData"]["threshold"])
            )
            if len(matches) > 0:

                state[action['actionData']['outputVarName']] = matches[:action["actionData"]["maxMatches"]]
                return ScriptExecutionState.SUCCESS, state, context
            else:
                return ScriptExecutionState.FAILURE, state, context

        elif action["actionName"] == "randomVariable":
            if action["actionData"]["distType"] == 'normal':
                mean = action["actionData"]["mean"]
                stddev = action["actionData"]["stddev"]
                mins = (action["actionData"]["min"] - mean) / stddev
                maxes = (action["actionData"]["max"] - mean) / stddev
                delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
                print(delays)
                state[action["actionData"]["outputVarName"]] = delays
            else:
                print('random variable unimplemented: ' + action["actionData"]["distType"])
                exit(0)
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