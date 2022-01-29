import subprocess
import sys

sys.path.append(".")

import numpy as np
import pyautogui
import random
import cv2
from skimage.metrics import structural_similarity as ssim
import matplotlib.pyplot as plt
import time
from script_execution_state import ScriptExecutionState
from script_engine_utils import dist

def produce_matches(screencap_im, screencap_search, screencap_mask, threshold=0.8):
    h, w = screencap_search.shape[0:2]
    match_result = cv2.matchTemplate(screencap_im, screencap_search, cv2.TM_CCOEFF_NORMED, screencap_mask)
    dist_threshold = (w + h) * 0.1
    # print(dist_threshold)
    loc = np.where(match_result >= threshold)
    matches = []
    match_scores = []
    for pt in zip(*loc[::-1]):
        redundant = False
        for match in matches:
            match_dist = dist(match[0], match[1], pt[0], pt[1])
            # print('dist ', match_dist)
            if match_dist < dist_threshold:
                redundant = True
        if redundant:
            continue
        else:
            # print(pt)
            matches.append(pt)
            match_scores.append(match_result[pt[1], pt[0]])
            cv2.rectangle(screencap_im, pt, (pt[0] + w, pt[1] + h), (0, 0, 255), 2)
    return matches,match_result,screencap_im


class python_host:
    def __init__(self):
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height

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

    def handle_action(self, action, state, props, log_level, log_folder):
        print(action["actionName"])
        state["script_counter"] += 1
        time.sleep(1)
        logs_path = log_folder + str(state['script_counter']) + '-' + action["actionName"] + '-'
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state)
        elif action["actionName"] == "sleepStatement":
            time.sleep(int(action["actionData"]["sleepTime"]))
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "clickAction":
            point_choice = random.choice(action["actionData"]["pointList"])
            input_points = eval(action["actionData"]["inputExpression"], state)
            if len(input_points) > 0:
                # potentially for loop here
                if input_points["inputType"] == "rectangle":
                    width_coord = random.random() * input_points["width"]
                    height_coord = random.random() * input_points['height']
                    point_choice = (input_points["point"][0] + width_coord, input_points["point"][1] + height_coord)
            point_choice = (point_choice[0] * self.width / props['width'],point_choice[1] * self.height / props['height'])
            print(point_choice)
            pyautogui.click(point_choice)
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
            screencap_mask = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(action['actionData']['img'])
            print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            print(screencap_im.shape)
            print(screencap_mask.shape)
            screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)
            screencap_compare = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])

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
            screencap_im_rgb = cv2.resize(np.array(screencap_im_rgb), (props['width'], props['height']), interpolation=cv2.INTER_LINEAR)
            screencap_im = cv2.cvtColor(screencap_im_rgb, cv2.COLOR_RGB2BGR)
            screencap_mask = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)

            screencap_search = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_search.shape)
            matches,match_result,result_im = produce_matches(screencap_im.copy(), screencap_search, screencap_mask)
            # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_result)
            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            # if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
            # print(screencap_search.shape)

            h, w = screencap_search.shape[0:2]
            # plt.imshow(match_result, cmap='gray')
            # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
            cv2.imwrite(logs_path + 'matching_overlay.png', cv2.cvtColor(result_im, cv2.COLOR_BGR2RGB))
            cv2.imwrite(logs_path + 'match_result.png', match_result*255)

            if len(matches) > 0:
                matches = [{
                    'inputType': 'rectangle',
                    'point': match,
                    'height': h,
                    'width': w
                } for match in matches]
                state[action['actionData']['outputVarName']] = matches
                return ScriptExecutionState.SUCCESS, state
            else:
                if props["scriptMode"] == "train":
                    threshold = 0.8
                    while not len(matches) > 0 and threshold > 0.3:
                        threshold -= 0.1
                        matches,match_result,result_im = produce_matches(screencap_im.copy(),screencap_search, screencap_mask,threshold=threshold)
                    print(matches[0])
                    print('train_threshold: ', threshold)
                    cv2.imwrite(logs_path + 'matching_overlay_train.png', cv2.cvtColor(result_im, cv2.COLOR_BGR2RGB))
                    cv2.imwrite(logs_path + 'match_result_train.png', match_result * 255)

                return ScriptExecutionState.FAILURE, state
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)