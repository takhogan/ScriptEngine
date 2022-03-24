import subprocess
import sys

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

import matplotlib.pyplot as plt
import time
from script_execution_state import ScriptExecutionState

from scipy.stats import truncnorm


class python_host:
    def __init__(self, props):
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height
        self.props = props
        self.image_matcher = ImageMatcher()

    def run_script(self, action, state):
        print('run_script: ', action)
        if action["actionData"]["awaitScript"]:
            outputs = subprocess.run(action["actionData"]["shellScript"], cwd="/", shell=True, capture_output=True)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            # print('output : ', outputs, 'state : ', state)
            return state
        else:
            proc = subprocess.Popen(action["actionData"]["shellScript"], cwd="/", shell=True)
            return state

    def handle_action(self, action, state, log_level, log_folder):
        # print(action["actionName"])
        time.sleep(1)
        # print('inside host', self.width, self.height)
        logs_path = log_folder + str(state['script_counter']) + '-' + action["actionName"] + '-'
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state)
        elif action["actionName"] == "sleepStatement":
            time.sleep(int(eval(action["actionData"]["sleepTime"], state)))
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "clickAction":
            point_choice = random.choice(action["actionData"]["pointList"]) if action["actionData"]["pointList"] else (None,None)
            if action["actionData"]["inputExpression"] is not None and len(action["actionData"]["inputExpression"]) > 0:
                input_points = eval(action["actionData"]["inputExpression"], state)
                if len(input_points) > 0:
                    # potentially for loop here
                    input_points = input_points[0]
                    if input_points["input_type"] == "rectangle":
                        width_coord = random.random() * input_points["width"]
                        height_coord = random.random() * input_points['height']
                        point_choice = (input_points["point"][0] + width_coord, input_points["point"][1] + height_coord)
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


            with open(logs_path + 'click_coordinate.txt', 'w') as log_file:
                log_file.write(str(point_choice) + '\n')
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "keyboardAction":
            is_escaped_char = False
            escaped_char = ''
            for char_index,expression_char in enumerate(action["actionName"]["actionData"]["keyboardExpression"]):
                if is_escaped_char:
                    if expression_char == '}':
                        is_escaped_char = False
                        pyautogui.press(escaped_char)
                        escaped_char = ''
                    else:
                        escaped_char += expression_char
                elif expression_char == '{':
                    escaped_char = True
                else:
                    pyautogui.press(expression_char)
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "detectScene":
            print('taking screenshot')
            screencap_im = pyautogui.screenshot()
            screencap_im = cv2.cvtColor(np.array(screencap_im), cv2.COLOR_RGB2BGR)
            screencap_mask = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(action['actionData']['img'])
            print(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            print(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            print(screencap_im.shape)
            print(screencap_mask.shape)
            screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)
            screencap_compare = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])

            ssim_coeff = ssim(screencap_masked, screencap_compare, multichannel=True)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-masked.png', screencap_masked)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-compare.png', screencap_compare)
            if ssim_coeff > 0.7:
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state
        elif action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/
            screencap_im_rgb = pyautogui.screenshot()
            # print('imshape: ', np.array(screencap_im_rgb).shape, ' width: ', self.props['width'], ' height: ', self.props['height'])
            if self.props['width'] is None or self.props['height'] is None:
                screencap_im = screencap_im_rgb
            else:
                screencap_im = cv2.resize(np.array(screencap_im_rgb), (self.props['width'], self.props['height']), interpolation=cv2.INTER_LINEAR)
            screencap_mask = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)

            screencap_search = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            screencap_search_bgr = cv2.cvtColor(screencap_search.copy(), cv2.COLOR_RGB2BGR)
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search)
            matches = self.image_matcher.template_match(screencap_im, screencap_mask, screencap_search_bgr, action['actionData']['detectorName'], logs_path, self.props["scriptMode"])
            if len(matches) > 0:
                print(matches)
                state[action['actionData']['outputVarName']] = matches
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state

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
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                log_image = pyautogui.screenshot()
                cv2.imwrite(logs_path + '-logImage.png', log_image)
                return ScriptExecutionState.SUCCESS, state
            else:
                print('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)