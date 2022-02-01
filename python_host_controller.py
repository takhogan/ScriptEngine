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
from sklearn.linear_model import LogisticRegression
import matplotlib.pyplot as plt
import time
from script_execution_state import ScriptExecutionState
from script_engine_utils import dist


class python_host:
    def __init__(self, props):
        host_dimensions = pyautogui.size()
        self.width = host_dimensions.width
        self.height = host_dimensions.height
        self.props = props

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

    def produce_matches(self, screencap_im, screencap_search, screencap_mask, logs_path, threshold=0.90):
        # https://docs.opencv.org/3.4/de/da9/tutorial_template_matching.html
        h, w = screencap_search.shape[0:2]
        # print(screencap_search.shape)
        # print(screencap_mask.shape)
        # exit(0)
        # print(.shape)
        # exit(0)
        screencap_mask = np.uint8(cv2.cvtColor(screencap_mask.copy(),cv2.COLOR_BGR2GRAY))
        # exit(0)
        match_result = cv2.matchTemplate(cv2.cvtColor(screencap_im.copy(), cv2.COLOR_BGR2GRAY), cv2.cvtColor(screencap_search.copy(), cv2.COLOR_BGR2GRAY), cv2.TM_CCORR_NORMED,result=None,mask=screencap_mask)
        cv2.normalize(match_result, match_result, 0, 1, cv2.NORM_MINMAX, -1)
        # minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(match_result, None)
        # match_result = cv2.matchTemplate(screencap_im, screencap_search, cv2.TM_CCOEFF_NORMED)
        dist_threshold = (w + h) * 0.1
        # print(dist_threshold)
        # print(match_result)
        # exit(0)
        loc = np.where(match_result >= threshold)
        matches = []
        match_scores = []
        match_imgs = []
        match_img_index = 1
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
                match_img = screencap_im[pt[1]:pt[1] + h, pt[0]:pt[0] + w].copy()
                match_imgs.append(match_img)
                if self.props["scriptMode"] == "train":
                    # change name to fit image format
                    cv2.imwrite(logs_path + '-matched-' + str(match_img_index) + '-{:f}'.format(match_result[pt[1], pt[0]]) + '-img.png', cv2.cvtColor(match_img, cv2.COLOR_BGR2RGB))
                match_img_index += 1

        for pt in zip(*loc[::-1]):
            cv2.rectangle(screencap_im, pt, (pt[0] + w, pt[1] + h), (0, 0, 255), 2)
        return matches, match_scores, match_result, screencap_im

    def produce_logistic_matches(self, screencap_im, screencap_search, screencap_mask, logs_path, assets_folder, threshold=0.7):
        # https://towardsdatascience.com/logistic-regression-using-python-sklearn-numpy-mnist-handwriting-recognition-matplotlib-a6b31e2b166a
        # https://stackoverflow.com/questions/5953373/how-to-split-image-into-multiple-pieces-in-python#:~:text=Copy%20the%20image%20you%20want%20to%20slice%20into,an%20image%20split%20with%20two%20lines%20of%20code

        logistic_model = LogisticRegression()
        grayscale_screencap = cv2.cvtColor(screencap_im.copy(), cv2.COLOR_RGB2GRAY)
        # print(grayscale_screencap.shape)
        h,w = screencap_search.shape[:-1]
        imgs = []
        labels = []
        positive_examples = glob.glob(assets_folder + '/positiveExamples/*-img.png')
        negative_examples = glob.glob(assets_folder + '/negativeExamples/*-img.png')
        for positive_example in positive_examples:
            imgs.append(np.asarray(cv2.cvtColor(np.asarray(Image.open(positive_example)), cv2.COLOR_RGB2GRAY)).flatten())
            labels.append(1)
        for negative_example in negative_examples:
            imgs.append(np.asarray(cv2.cvtColor(np.asarray(Image.open(negative_example)), cv2.COLOR_RGB2GRAY)).flatten())
            labels.append(0)
        logistic_model.fit(imgs, labels)
        print(screencap_im.shape)
        print(h)
        print(w)
        # print(screencap_im[0:h, 0:w].shape)
        img_tiles = np.array([grayscale_screencap[y:y + h, x:x + w].flatten() for y in range(0, (grayscale_screencap.shape[0] - h)) for x in range(0, (grayscale_screencap.shape[1] - w))])
        print(img_tiles.shape)
        # logistic_model.predict(img_tiles).reshape(screencap_im.shape[0] - h, screencap_im.shape[1] - w)

        print(screencap_search.shape)
        # print(screen_tiles)
        # for tile in enumerate(tiles):
        exit(0)
        return None,None,None

    def handle_action(self, action, state, log_level, log_folder):
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
            point_choice = (point_choice[0] * self.width / self.props['width'],point_choice[1] * self.height / self.props['height'])
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
            screencap_im = cv2.resize(np.array(screencap_im_rgb), (self.props['width'], self.props['height']), interpolation=cv2.INTER_LINEAR)
            screencap_mask = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)

            screencap_search = cv2.imread(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search)
            # print(screencap_search.shape)
            if action["actionData"]["detectorName"] == "pixelDifference":
                matches,match_scores,match_result,result_im = self.produce_matches(screencap_im.copy(), screencap_search, screencap_mask, logs_path)
            elif action["actionData"]["detectorName"] == "logisticClassifier":
                assets_folder = '/'.join((self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"]).split('/')[:-2])
                matches,match_result,result_im = self.produce_logistic_matches(screencap_im.copy(), screencap_search, screencap_mask, logs_path, assets_folder)
            else:
                print("detector unimplemented! " + action)
                exit(0)
            # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_result)
            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            # if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
            # print(screencap_search.shape)

            h, w = screencap_search.shape[0:2]
            # plt.imshow(match_result, cmap='gray')
            # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
            cv2.imwrite(logs_path + 'matching_overlay.png', cv2.cvtColor(result_im, cv2.COLOR_BGR2RGB))
            cv2.imwrite(logs_path + 'match_result.png', match_result*255)
            # if self.props["scriptMode"] == "train":
            #     threshold = 0.5
            #     train_matches = []
            #     while not len(train_matches) > 0 and threshold > 0.1:
            #         threshold -= 0.1
            #         train_matches, train_scores, train_match_result, train_result_im = self.produce_matches(screencap_im.copy(), screencap_search,
            #                                                                 screencap_mask, logs_path,
            #                                                                 threshold=threshold)
                # print(train_matches[0])
                # print('train_threshold: ', threshold)
                # cv2.imwrite(logs_path + 'matching_overlay_train.png', cv2.cvtColor(train_result_im, cv2.COLOR_BGR2RGB))
                # cv2.imwrite(logs_path + 'match_result_train.png', train_match_result * 255)
            if len(matches) > 0:
                print(matches)
                matches = [{
                    'inputType': 'rectangle',
                    'point': match,
                    'height': h,
                    'width': w,
                    'score' : score
                } for match,score in zip(matches, match_scores)]
                matches = [value for key,value in pd.DataFrame.from_dict(matches).sort_values('score').T.to_dict().items()]
                state[action['actionData']['outputVarName']] = matches
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state
        else:
            print('unimplemented method! ' + action["actionName"])
            exit(0)