from PIL import Image
import tesserocr
import re
import requests
import cv2
import easyocr
import json
import time
import numpy as np
import glob
import datetime
import os
import shutil

from pymongo import MongoClient

from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_action_log import ScriptActionLog
from script_execution_state import ScriptExecutionState
from script_engine_constants import *
from script_engine_utils import generate_context_switch_action, state_eval
from messaging_helper import MessagingHelper
from script_logger import ScriptLogger
from typing import Callable, Dict, List, Tuple
script_logger = ScriptLogger()



class SystemHostController:
    def __init__(self, python_host, base_script_name, props, io_executor):
        self.python_host = python_host
        self.base_script_name = base_script_name
        self.props = props
        self.io_executor = io_executor
        self.messaging_helper = MessagingHelper()
        self.easy_ocr_reader = None

    def handle_action(self, action, state, context, run_queue) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List] | Tuple[Callable, Tuple]:
        def sanitize_input(statement_input, state):
            statement_input = statement_input.strip()
            statement_input = statement_input.replace('\n', ' ')
            operator_pattern = r'[\[\]\(\)+-/*%=<>!^|&~]'
            word_operator_pattern = r'( is )|( in )|( not )|( and )|( or )'
            statement_strip = re.sub(operator_pattern, ' ', statement_input)
            statement_strip = re.sub(word_operator_pattern, ' ', statement_strip)
            statement_strip = re.sub(word_operator_pattern, ' ', statement_strip)
            statement_strip = list(filter(lambda term: (len(term) > 0) and "'" not in term and "\"" not in term, statement_strip.split(' ')))
            for term_index,term in enumerate(statement_strip):
                if term.isidentifier() and term not in state:
                    term_str = str(term) + ': N/A'
                else:
                    try:
                        term_eval = state_eval(term, {}, state)
                    except (TypeError,KeyError,SyntaxError) as p_err:
                        script_logger.log(p_err)
                        term_eval = None
                    term_str = str(term) + ': ' + str(term_eval) + ': ' + str(type(term_eval))
                statement_strip[term_index] = term_str
            return statement_strip
        if action["actionName"] == "conditionalStatement":
            condition = action["actionData"]["condition"].replace("\n", " ").strip()
            statement_strip = sanitize_input(condition, state)
            pre_log = 'condition: {} {}'.format(condition, statement_strip)
            script_logger.log(pre_log)
            if state_eval('(' + condition + ')',{}, state):
                post_log = 'condition successful'
                script_logger.log(post_log)
                status = ScriptExecutionState.SUCCESS
            else:
                post_log = 'condition failure'
                script_logger.log(post_log)
                status = ScriptExecutionState.FAILURE

            script_logger.get_action_log().add_post_file(
                'text',
                ('condition-success.txt' if status == ScriptExecutionState.SUCCESS else 'condition-failure.txt'),
                pre_log + '\n' + post_log
            )
        elif action["actionName"] == "variableAssignment":
            outputVarName = action["actionData"]["outputVarName"].strip()
            outputVarNameInState = outputVarName in state
            isSetIfNull = action["actionData"]["setIfNull"] == "true" or action["actionData"]["setIfNull"]
            post_file_name = 'variableAssignment-log.txt'
            pre_log = ('assignment configuration is set if null' if isSetIfNull else '')
            script_logger.get_action_log().add_post_file(
                'text',
                post_file_name,
                (pre_log + '\n' if pre_log != '' else '')
            )
            if isSetIfNull and outputVarNameInState and state[outputVarName] is not None:
                pre_log += ' and output variable {} was not null'.format(outputVarName)
                script_logger.log(pre_log)
                status = ScriptExecutionState.SUCCESS
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    (pre_log + '\n' if pre_log != '' else '')
                )
            else:
                pre_log += ('and output variable {} was null'.format(outputVarName) if isSetIfNull else '')
                statement_strip = sanitize_input(action["actionData"]["inputExpression"], state)

                mid_log = ('inputExpression : ' + action["actionData"]["inputExpression"])
                mid_log_2 = ('inputs: ' + str(statement_strip))
                script_logger.log(mid_log)
                script_logger.log(mid_log_2)
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    mid_log + '\n' + \
                    mid_log_2 + '\n'
                )


                expression = action["actionData"]["inputExpression"].replace("\n", " ")
                if action["actionData"]["inputParser"] == 'eval':
                    expression = state_eval(expression, {}, state)
                elif action["actionData"]["inputParser"] == "jsonload":
                    expression = json.loads(expression)
                late_mid_log = 'parse result: ' + str(expression)
                script_logger.log('parse result: ', expression)

                late_mid_log_2 = 'state variables :' + str(list(state))
                script_logger.log(late_mid_log_2)

                if '[' in outputVarName and ']' in outputVarName:
                    keys = outputVarName.split('[')  # Split the key string by '][' to get individual keys
                    # Evaluate variable names within the state dictionary
                    for i, k in enumerate(keys[1:]):
                        k = k.rstrip(']')
                        keys[i + 1] = state_eval(k, {}, state)

                    # Assign the value to the corresponding key within the state dictionary
                    current = state
                    for i in range(len(keys) - 1):
                        if keys[i] in current:
                            current = current[keys[i]]
                    current[keys[-1]] = expression
                else:
                    state[outputVarName] = expression
                post_log = 'setting ' + outputVarName + ' to ' + str(expression)
                script_logger.log(
                    ' setting ',
                    outputVarName,
                    ' to ',
                    expression
                )
                status = ScriptExecutionState.SUCCESS
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    late_mid_log + '\n' + \
                    late_mid_log_2 + '\n' + \
                    post_log
                )

        elif action["actionName"] == "countToThresholdAction":
            counterVarName = action["actionData"]["counterVarName"].strip()
            counterThreshold = action["actionData"]["counterThreshold"].strip()
            incrementBy = action["actionData"]["incrementBy"].strip()

            threhold_stripped = sanitize_input(counterThreshold, state)
            incrementby_stripped = sanitize_input(incrementBy, state)
            pre_log = 'with counter name {}'.format(counterVarName) +\
                'threshold params {}'.format(threhold_stripped) +\
                'and incrementBy params {}'.format(incrementby_stripped)
            script_logger.log(pre_log)
            if not counterVarName in state:
                initialValue = '0'
                if "initialValue" in action["actionData"]:
                    initialValue = action["actionData"]["initialValue"].strip()
                initial_value_stripped = sanitize_input(initialValue, state)

                initial_value_logs = 'Setting initial value with initialValue params {}'.format(initial_value_stripped)
                script_logger.log(initial_value_logs)
                initial_value = state_eval(initialValue, {}, state)
                state[counterVarName] = initial_value

                initial_value_post_logs = 'Evaluated initial value to {}'.format(initial_value)
                script_logger.log(initial_value_post_logs)
                pre_log += '\n' + initial_value_logs + '\n' + initial_value_post_logs

            counter_value = state_eval(counterVarName, {}, state)
            threshold_value = state_eval(counterThreshold, {}, state)
            if counter_value < threshold_value:
                incrementby_value = state_eval(incrementBy, {}, state)
                post_log = 'For counter {}'.format(counterVarName) +\
                    'counter value of {}'.format(counter_value) +\
                    'was less than threshold of {}'.format(threshold_value) + '.'+\
                    'incrementing by {}'.format(incrementby_value) +\
                    'and returning failure'
                script_logger.log(
                    post_log
                )
                new_counter_value = counter_value + incrementby_value
                state[counterVarName] = new_counter_value
                status = ScriptExecutionState.FAILURE
                post_post_log = 'new counter value is {}'.format(new_counter_value)
                script_logger.log(
                    post_post_log
                )
            else:
                post_log = 'For counter {}'.format(counterVarName) + \
                           'counter value of {}'.format(counter_value) + \
                           'was greater than threshold of {}'.format(threshold_value) + '.' + \
                           'returning success.'
                script_logger.log(
                    'counter value of', counter_value, 'was greater than threshold of', threshold_value, '.',
                    'returning success'
                )
                post_post_log = ''

                status = ScriptExecutionState.SUCCESS
            script_logger.get_action_log().add_post_file(
                'text',
                'counterVarName-log.txt',
                pre_log + '\n' +\
                post_log + '\n' +\
                post_post_log
            )
        elif action["actionName"] == "sleepStatement":
            input_expression = str(action["actionData"]["inputExpression"]).strip()
            pre_log = 'inputExpression: ' + input_expression
            script_logger.log(pre_log)
            sleep_length = 0
            if input_expression != '':
                sleep_length = float(state_eval(input_expression, {}, state))
                mid_log = 'evaluated inputExpression and sleeping for ' + str(sleep_length) + 's'
                script_logger.log(mid_log)
                script_logger.get_action_log().add_pre_file(
                    'text',
                    'sleepStatement-begin-{:.2f}'.format(sleep_length).replace('.', '_') + '.txt',
                    pre_log + '\n' + mid_log
                )
                time.sleep(sleep_length)
            script_logger.get_action_log().add_post_file(
                'text',
                'sleepStatement-end-{:.2f}'.format(sleep_length).replace('.', '_') + '.txt',
                'slept for {}s'.format(sleep_length)
            )
            status = ScriptExecutionState.SUCCESS
        #TODO: will be removed, should use regular variable assignment and the datetime module
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "randomVariable":
            rv_vals = RandomVariableHelper.get_rv_val(action)
            state[action["actionData"]["outputVarName"]] = rv_vals[0]
            status = ScriptExecutionState.SUCCESS
            script_logger.log('created random values', rv_vals[0])
            script_logger.get_action_log().add_post_file(
                'text',
                'randomVariable-log.txt',
                'Created random values: ' + str(rv_vals[0])
            )
        #TODO: will be removed, need a new file io type action
        elif action["actionName"] == "jsonFileAction":
            if action["actionData"]["mode"] == "read":
                json_filepath = self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"]
                if os.path.exists(json_filepath):
                    with open(json_filepath, "r") as read_file:
                        state[action["actionData"]["varName"]] = json.load(read_file)
                else:
                    state[action["actionData"]["varName"]] = {}
                status = ScriptExecutionState.SUCCESS
            elif action["actionData"]["mode"] == "write":
                script_logger.log('writing file: ', state[action["actionData"]["varName"]])
                with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"],
                          'w') as write_file:
                    json.dump(state[action["actionData"]["varName"]], write_file)
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.log('invalid mode: ', action)
                status = ScriptExecutionState.ERROR
        elif action["actionName"] == "imageTransformationAction":
            # transformationType : 'blur' | 'binarize' | 'antialias' | 'resize' | 'erode' | 'dilate'
            if len(action['actionData']['inputExpression']) == 0:
                script_logger.log('Error: input expression was blank')
                raise Exception(action["actionName"] + ' input expression was blank')

            transform_im = state[action['actionData']['inputExpression']]['matched_area']
            pre_image_relative_path = 'imageTransformationAction-input.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + pre_image_relative_path, transform_im)
            script_logger.get_action_log().set_pre_file('image', pre_image_relative_path)

            if action["actionData"]["transformationType"] == "blur":
                if action["actionData"]["blurType"] == 'bilateralFilter':
                    transform_im = cv2.bilateralFilter(transform_im, int(action["actionData"]["blurKernelSize"]), 75, 75)
                elif action["actionData"]["blurType"] == 'medianBlur':
                    transform_im = cv2.medianBlur(transform_im, int(action["actionData"]["blurKernelSize"]))
                elif action["actionData"]["blurType"] == 'gaussianBlur':
                    transform_im = cv2.GaussianBlur(transform_im, (int(action["actionData"]["blurKernelSize"]), int(action["actionData"]["blurKernelSize"])), 0)
            elif action["actionData"]["transformationType"] == "binarize":
                is_color = len(transform_im.shape) != 2
                if is_color:
                    script_logger.log('converting to grayscale for binarize operation')
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                if action["actionData"]["binarizeType"] == 'regular':
                    script_logger.log('shape', transform_im.shape)
                    transform_im = cv2.threshold(
                        transform_im,
                        0,
                        255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )[1]
                elif action["actionData"]["binarizeType"] == 'adaptive':
                    transform_im = cv2.adaptiveThreshold(
                        transform_im,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        31,
                        2
                    )
                if is_color:
                    script_logger.log('converting grayscale back to color')
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)
            elif action["actionData"]["transformationType"] == "antialias":
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=1/float(action["actionData"]["antialiasScaleFactor"]),
                    fy=1/float(action["actionData"]["antialiasScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=float(action["actionData"]["antialiasScaleFactor"]),
                    fy=float(action["actionData"]["antialiasScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )

            elif action["actionData"]["transformationType"] == "resize":
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=float(action["actionData"]["resizeScaleFactor"]),
                    fy=float(action["actionData"]["resizeScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )
            elif action["actionData"]["transformationType"] == "erode":
                kernel = np.ones((
                    int(action["actionData"]["erodeKernelSize"]),
                    int(action["actionData"]["erodeKernelSize"])
                ), np.uint8)
                transform_im = cv2.erode(transform_im, kernel, iterations=int(action["actionData"]["erodeIterations"]))
            elif action["actionData"]["transformationType"] == "dilate":
                kernel = np.ones((
                    int(action["actionData"]["erodeKernelSize"]),
                    int(action["actionData"]["erodeKernelSize"])
                ), np.uint8)
                transform_im = cv2.dilate(transform_im, kernel, iterations=int(action["actionData"]["erodeIterations"]))
            elif action["actionData"]["transformationType"] == "convertColor":
                if action["actionData"]["convertColorType"] == "BGRtoGrayScale":
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)
                elif action["actionData"]["convertColorType"] == "invert":
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                    transform_im = cv2.bitwise_not(transform_im)
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)

            post_image_relative_path = 'imageTransformationAction-output.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + post_image_relative_path, transform_im)
            script_logger.get_action_log().set_post_file('image', post_image_relative_path)

            if len(action['actionData']['outputVarName']) > 0:
                state[action['actionData']['outputVarName']] = state[action['actionData']['inputExpression']].copy()
                state[action['actionData']['outputVarName']]['matched_area'] = transform_im
                state[action['actionData']['outputVarName']]['height'] = transform_im.shape[0]
                state[action['actionData']['outputVarName']]['height'] = transform_im.shape[1]
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "imageToTextAction":
            input_obj = DetectObjectHelper.get_detect_area(
                action, state
            )
            pre_log = 'Image Transformations:\n'

            search_im = input_obj['screencap_im_bgr']
            pre_image_relative_path = 'imageToTextAction-raw-input.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + pre_image_relative_path, search_im)
            script_logger.get_action_log().set_pre_file('image', pre_image_relative_path)

            image_to_text_input = cv2.cvtColor(search_im.copy(), cv2.COLOR_BGR2GRAY)
            conversion_log = 'converted to grayscale'
            script_logger.log(conversion_log)
            pre_log += conversion_log +'\n'

            if action["actionData"]["increaseContrast"]:
                image_to_text_input = cv2.equalizeHist(image_to_text_input)
                conversion_log = 'increased contrast'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'

            if action["actionData"]["invertColors"]:
                image_to_text_input = cv2.bitwise_not(image_to_text_input)
                conversion_log = 'inverted colors'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'

            im_height = image_to_text_input.shape[0]
            if im_height < 50:
                image_to_text_input = cv2.resize(image_to_text_input, None, fx=int(100 / im_height), fy=int(100 / im_height), interpolation=cv2.INTER_CUBIC)
                conversion_log = 'input too small, boosted size by factor of {}'.format(int(100 / im_height))
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
            if 'blur' in action['actionData']:
                if action["actionData"]["blur"] == 'bilateralFilter':
                    image_to_text_input = cv2.bilateralFilter(image_to_text_input, 5, 75, 75)
                    conversion_log = 'applied bilateral filter'
                    script_logger.log(conversion_log)
                    pre_log += conversion_log + '\n'
                elif action["actionData"]["blur"] == 'medianBlur':
                    image_to_text_input = cv2.medianBlur(image_to_text_input, 3)
                    conversion_log = 'applied median blur'
                    script_logger.log(conversion_log)
                    pre_log += conversion_log + '\n'
                elif action["actionData"]["blur"] == 'gaussianBlur':
                    image_to_text_input = cv2.GaussianBlur(image_to_text_input, (5, 5), 0)
                    conversion_log = 'applied gaussian blur'
                    script_logger.log(conversion_log)
                    pre_log += conversion_log + '\n'
            if 'binarize' in action['actionData']:
                if action["actionData"]["binarize"] == 'regular':
                    image_to_text_input = cv2.threshold(
                        image_to_text_input,
                        0,
                        255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )[1]
                    conversion_log = 'applied regular binarization'
                    script_logger.log(conversion_log)
                    pre_log += conversion_log + '\n'
                elif action["actionData"]["binarize"] == 'adaptive':
                    image_to_text_input = cv2.adaptiveThreshold(
                        image_to_text_input,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        31,
                        2
                    )
                    conversion_log = 'applied adaptive binarization'
                    script_logger.log(conversion_log)
                    pre_log += conversion_log + '\n'
            if 'makeBorder' in action['actionData'] and (
                    action['actionData']['makeBorder'] == True or
                    action['actionData']['makeBorder'] == 'true'
                ):
                if len(image_to_text_input.shape) == 2:
                    border_color = int(image_to_text_input[0, 0])
                else:
                    border_color = list(map(int, image_to_text_input[0,0][::-1]))
                # Add a 2-pixel border to the image
                image_to_text_input = cv2.copyMakeBorder(
                    image_to_text_input, 2, 2, 2, 2,
                    cv2.BORDER_CONSTANT, value=border_color
                )
                conversion_log = 'added border'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'

            mid_image_relative_path = 'imageToTextAction-parsed-input.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + mid_image_relative_path, image_to_text_input)
            script_logger.get_action_log().add_supporting_file_reference('image', mid_image_relative_path)

            is_image_to_text_debug_mode = "runMode" in action["actionData"] and action["actionData"][
                "runMode"] == "debug"

            if action["actionData"]["conversionEngine"] == "tesseractOCR":

                TARGET_TYPE_TO_PSM = {
                    'word': '8',
                    'sentence': '7',
                    'page': '3',
                    'character': '10',
                    'rawLine': '13'
                }
                PSM_TO_TARGET_TYPE = {
                    value: key for key, value in TARGET_TYPE_TO_PSM.items()
                }

                tesseract_params = [
                    [
                        TARGET_TYPE_TO_PSM[action['actionData']['targetType']],
                        str(action["actionData"]["characterWhiteList"])
                    ]
                ]
                if is_image_to_text_debug_mode:
                    psm_values = list(TARGET_TYPE_TO_PSM.values())
                    psm_values.remove(TARGET_TYPE_TO_PSM[action['actionData']['targetType']])
                    tesseract_params = tesseract_params + [
                        [
                            psm_val,
                            str(action["actionData"]["characterWhiteList"])
                        ] for psm_val in psm_values
                    ]

                outputs = []
                inputs_log = ''
                for [psm_value, character_white_list] in tesseract_params:
                    with tesserocr.PyTessBaseAPI() as api:
                        api.SetImage(Image.fromarray(image_to_text_input))
                        api.SetPageSegMode(int(psm_value))
                        if len(character_white_list) > 0:
                            api.SetVariable("tessedit_char_whitelist", character_white_list)
                        # may want to consider bgr to rgb conversion
                        output_text = api.GetUTF8Text().strip()
                        outputs.append(output_text)
                        input_result_log = 'Running with psm {} ({}) characterWhiteList {}'.format(
                            psm_value,
                            PSM_TO_TARGET_TYPE[psm_value],
                            character_white_list if len(character_white_list) > 0 else 'none'
                        ) + ' and output was: {}'.format(output_text)
                        script_logger.log(input_result_log)
                        inputs_log += input_result_log +'\n'

                post_log = ''

                if is_image_to_text_debug_mode:
                    for output_index, debug_output in enumerate(outputs[1:]):
                        post_log += '\n' + 'final debug output for psm {} was:{}'.format(
                            tesseract_params[output_index + 1][0],
                            debug_output
                        )
            elif action["actionData"]["conversionEngine"] == "easyOCR":
                post_log = ''
                inputs_log = ''

                if self.easy_ocr_reader is None:
                    script_logger.log('initializing easyOCR model...')
                    self.easy_ocr_reader = easyocr.Reader(['en'])

                results = self.easy_ocr_reader.readtext(image_to_text_input)


                outputs = [[]]

                for bbox, text, confidence in results:
                    if confidence < 0.75:
                        continue
                    script_logger.log(f"Detected word: {text}")
                    script_logger.log(f"Bounding box: {bbox}")
                    script_logger.log(f"Confidence: {confidence}\n")
                    outputs[0].append(text)
                outputs[0] = ' '.join(outputs[0])
                input_results_log = 'Running easyOCR model with default params and output was ' + outputs[0]
                inputs_log += input_results_log + '\n'

            else:
                raise Exception('Unsupported OCR engine' + action["actionData"]["conversionEngine"])
            post_log += '\n final primary output was:{}'.format(
                outputs[0]
            )


            script_logger.log(post_log)
            script_logger.get_action_log().add_post_file(
                'text',
                'imageToText-results.txt',
                pre_log + '\n' + inputs_log + '\n' + post_log
            )
            state[action["actionData"]["outputVarName"]] = outputs[0].strip()
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "contextSwitchAction":
            success_states = context["success_states"] if "success_states" in context else None
            script_counter = context["script_counter"]
            script_timer = context["script_timer"]
            post_log = ''
            if action["actionData"]["state"] is not None:
                state = action["actionData"]["state"].copy()
            if action["actionData"]["context"] is not None:
                context = action["actionData"]["context"].copy()
            if 'state' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["state"].items():
                    state[key] = value
                input_state_log = 'Keys in input state: {}'.format(
                    str(list(action["actionData"]["update_dict"]["state"]))
                )
                post_log += input_state_log + '\n'
                script_logger.log(input_state_log)

            if 'context' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["context"].items():
                    context[key] = value
                input_context_log = 'Keys in input context: {}'.format(
                    str(list(action["actionData"]["update_dict"]["context"]))
                )
                post_log += input_context_log + '\n'
                script_logger.log(input_context_log)
            if success_states is not None:
                context["success_states"] = success_states
            context["script_counter"] = script_counter
            context["script_timer"] = script_timer
            status = ScriptExecutionState.SUCCESS
            iteration_log = 'Script Counter: {}'.format(
                str(context["script_counter"])
            ) + '\n' + 'Script Timer: {}'.format(
                str(context["script_timer"])
            )
            script_logger.log(iteration_log)
            post_log += iteration_log + '\n'
            script_logger.get_action_log().add_post_file(
                'text',
                'contextSwitchAction-log.txt',
                'System Created Action - Context Switch Action\n' + post_log
            )

        elif action["actionName"] == "sendMessageAction":
            message = state_eval(action["actionData"]["inputExpression"], {}, state)

            pre_log = 'Sending message through ' + str(action["actionData"]["messagingProvider"]) +\
                      ' of type ' + str(action["actionData"]["messageType"])
            script_logger.log(pre_log)

            mid_log = 'Message Contents: ' + str(message)
            script_logger.log(mid_log)

            messaging_successful = self.messaging_helper.send_message({
                "action" : "sendMessage",
                "messagingChannelName" : action["actionData"]["messagingChannelName"],
                "messagingProvider" : action["actionData"]["messagingProvider"],
                "messageType" : action["actionData"]["messageType"],
                "message" : message
            })

            if messaging_successful:
                status = ScriptExecutionState.SUCCESS
                post_log = 'Message Send Successful'
            else:
                status = ScriptExecutionState.FAILURE
                post_log = 'Message Send Failed'
            script_logger.log(post_log)
            script_logger.get_action_log().add_post_file(
                'text',
                'sendMessage-log.txt',
                pre_log + '\n' + mid_log + '\n' + post_log
            )
        elif action["actionName"] == "returnStatement":
            pre_log = 'Return Statement Type: {}'.format(action["actionData"]["returnStatementType"])
            script_logger.log(pre_log)

            mid_log = 'Desired Return Status: {}'.format(action["actionData"]["returnStatus"])
            script_logger.log(mid_log)
            status_name = 'undefined'
            if action["actionData"]["returnStatementType"] == 'exitBranch':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE_BRANCH
                    status_name = 'FINISHED_FAILURE_BRANCH'
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED_BRANCH
                    status_name = 'FINISHED_BRANCH'
                else:
                    raise Exception('invalid return status' + action["actionData"]["returnStatus"])
            elif action["actionData"]["returnStatementType"] == 'exitScript':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE
                    status_name = 'FINISHED_FAILURE'
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED
                    status_name = 'FINISHED'
                else:
                    raise Exception('invalid return status' + action["actionData"]["returnStatus"])
            elif action["actionData"]["returnStatementType"] == 'exitProgram':
                post_log = 'Exiting Program'
                script_logger.log(post_log)
                script_logger.get_action_log().add_post_file(
                    'text',
                    'returnStatement-{}.txt'.format('exit-0'),
                    pre_log + '\n' + mid_log + '\n' + post_log
                )
                status = ScriptExecutionState.ERROR
                exit(0)
            else:
                script_logger.log('return statement type not implemented', action["actionData"]["returnStatementType"])
                raise Exception('return statement type not implemented')
            post_log = 'Setting Status: {}'.format(status_name)
            script_logger.log(post_log)
            script_logger.get_action_log().add_post_file(
                'text',
                'returnStatement-{}.txt'.format(status_name),
                pre_log + '\n' + mid_log + '\n' + post_log
            )
        #TODO: will be removed, use returnStatement instead
        elif action["actionName"] == "exceptionAction":
            script_logger.log('exceptionAction-' + str(action["actionGroup"]), ' message: ', action["actionData"]["exceptionMessage"])
            if action["actionData"]["takeScreenshot"]:
                pass
            if action["actionData"]["exitProgram"]:
                script_logger.log('exiting program')
                exit(0)
            status = ScriptExecutionState.FINISHED_FAILURE
            with open(script_logger.get_log_path_prefix() + '-return-failure.txt', 'w') as log_file:
                log_file.write('returning failure state')
        elif action["actionName"] == "forLoopAction":
            pre_log = 'Initializing Context Switch Actions for For Loop Action'
            first_loop = True
            script_logger.log(pre_log)
            in_variable = state_eval(action["actionData"]["inVariables"], {}, state)

            mid_log_1 = 'inVariable: {} evaluated to: {}'.format(
                str(action["actionData"]["inVariables"]),
                str(in_variable)
            )

            script_logger.log(
                'inVariable:',
                action["actionData"]["inVariables"],
                'evaluated to:',
                in_variable
            )
            for_variable_list = action["actionData"]["forVariables"].split(',')

            mid_log_2 = 'forVariables: {} evaluated to: {}'.format(
                str(action["actionData"]["forVariables"]),
                str(for_variable_list)
            )

            script_logger.log(
                'forVariables:',
                action["actionData"]["forVariables"],
                'evaluated to:',
                for_variable_list
            )
            post_log = ''
            for_iteration = 0
            for for_variables in in_variable:
                state_update_dict = {
                    var_name:for_variables[var_index] for var_index,var_name in enumerate(for_variable_list)
                } if len(for_variable_list) > 1 else {
                    for_variable_list[0]: for_variables
                }
                script_logger.log(
                    'for variables for iteration {}'.format(for_iteration),
                    for_variables
                )
                post_log += 'for variables for iteration {}: {}'.format(
                    for_iteration,
                    str(for_variables)
                )

                for_iteration += 1
                if first_loop:
                    state.update(state_update_dict)
                    first_loop = False
                    post_log += '\n' + 'copying for variables to current state for first loop'
                    continue
                post_log += '\n' + 'creating context switch action for iteration {}'.format(for_iteration)
                switch_action = generate_context_switch_action(action["childGroups"], None, None, {
                    "state": state_update_dict
                })
                run_queue.append(switch_action)
            script_logger.get_action_log().add_post_file(
                'text',
                'forLoopAction-log.txt',
                pre_log + '\n' + mid_log_1 + '\n' + mid_log_2 + '\n' + post_log
            )
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "codeBlock":
            globals = {
                'glob': glob,
                'datetime': datetime,
                'os' : os,
                'shutil' : shutil,
                'numpy' : np
            }
            pre_log = 'Running Code Block: \n{}'.format(action["actionData"]["codeBlock"])
            # statement_strip = sanitize_input(action["actionData"]["codeBlock"], state_copy)
            script_logger.log(pre_log)

            exec(action["actionData"]["codeBlock"],globals,state)
            script_logger.get_action_log().add_post_file(
                'text',
                'codeBlock-log.txt',
                pre_log + '\n' + 'Code Block completed successfully'
            )
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "fileIOAction":
            pre_log = 'FileIOAction\n' + \
                (
                    'Writing to' if
                    action["actionData"]["fileActionType"] in ["w", "wb", "a"]
                    else 'Reading from'
                ) + ' file: ' + action["actionData"]["filePath"] + '\n'
            pre_log += 'Contents of type: ' + action["actionData"]["fileType"] +\
                       ' with mode ' + action["actionData"]["fileActionType"] + '\n'
            pre_log += 'Input expression: ' + action["actionData"]["inputExpression"] + '\n'
            pre_log += 'Writing inputs to variable: ' + action["actionData"]["outputVarName"]
            script_logger.get_action_log().add_pre_file('text', 'inputs.txt', pre_log)
            script_logger.log(pre_log)
            file_path = state_eval(action["actionData"]["filePath"], {}, state)
            output_var_name = action["actionData"]["outputVarName"]
            file_properties = ''
            if action["actionData"]["fileActionType"] in ["w", "wb", "a"]:
                input_value = state_eval(action["actionData"]["inputExpression"], {}, state)
                if action["actionData"]["fileType"] == "image":
                    file_properties = 'shape: ' + str(input_value["matched_area"].shape)
                    cv2.imwrite(file_path, input_value["matched_area"])
                elif action["actionData"]["fileType"] == "json":
                    file_properties = 'key: ' + str(list(input_value))
                    with open(file_path, action["actionData"]["fileActionType"]) as json_file:
                        json.dump(input_value, json_file)
                elif action["actionData"]["fileType"] == "text":
                    file_properties = 'n characters:  ' + str(len(input_value))
                    with open(file_path, action["actionData"]["fileActionType"]) as text_file:
                        text_file.write(input_value)
                state[output_var_name] = input_value
            elif action["actionData"]["fileActionType"] in ["r", "rb"]:
                if action["actionData"]["fileType"] == "image":
                    image = cv2.imread(file_path)
                    state[output_var_name] = {
                        'input_type': 'shape',
                        'point': (0, 0),
                        'shape': np.full((image.shape[0], image.shape[1]), 255, dtype=np.uint8),
                        'matched_area': image,
                        'height': image.shape[0],
                        'width': image.shape[1],
                        'score': 0.99999,
                        'n_matches': 1
                    }
                    file_properties = 'shape: ' + str(state[output_var_name].shape)

                elif action["actionData"]["fileType"] == "json":
                    with open(file_path, action["actionData"]["fileActionType"]) as json_file:
                        state[output_var_name] = json.load(json_file)
                    file_properties = 'keys: ' + str(list(state[output_var_name]))
                elif action["actionData"]["fileType"] == "text":
                    with open(file_path, action["actionData"]["fileActionType"]) as text_file:
                        state[output_var_name] = text_file.read()
                    file_properties = 'n characters:  ' + str(len(state[output_var_name]))
            post_log = (
                'Wrote to' if
                action["actionData"]["fileActionType"] in ["w", "wb", "a"]
                else 'Read from'
            ) + file_path + '\n'
            post_log += 'Contents of type: ' + action["actionData"]["fileType"] +\
                       ' with mode ' + action["actionData"]["fileActionType"] + '\n'
            post_log += 'File properties: ' + file_properties + '\n'
            post_log += 'Input expression: ' + action["actionData"]["inputExpression"] + '\n'
            post_log += 'Wrote inputs to variable: ' + action["actionData"]["outputVarName"]
            script_logger.get_action_log().add_post_file('text', 'post.txt', post_log)
            status = ScriptExecutionState.SUCCESS
        #TODO : unsupported for now
        elif action["actionName"] == "databaseCRUD":
            if action["actionData"]["databaseType"] == "mongoDB":
                with open(SERVICE_CREDENTIALS_FILE_PATH, 'r') as service_credentials_file:
                    mongo_credentials = json.load(service_credentials_file)["mongoDB"]
                connection_string = "mongodb+srv://{}:{}@scriptenginecluster.44rpgo2.mongodb.net/?retryWrites=true&w=majority".format(
                    mongo_credentials["username"],
                    mongo_credentials["password"]
                )
                client = MongoClient(connection_string)
                script_logger.log(client)
                if len(action["actionData"]["collectionName"]) > 0:
                    collection_name = action["actionData"]["collectionName"]
                else:
                    collection_name = self.base_script_name
                collection = getattr(client, collection_name)

                if action["actionData"]["actionType"] == "insert":
                    if len(action["actionData"]["key"]) > 0:
                        new_item = {"key": action["actionData"]["key"],
                                    "value": state_eval(action["actionData"]["value"], {}, state)
                                    }
                    else:
                        new_item = state_eval(action["actionData"]["value"], state.copy())
                    result = collection.insert_one(new_item)
                elif action["actionData"]["actionType"] == "update" or\
                        action["actionData"]["actionType"] == "upsert":
                    query = {"key": action["actionData"]["key"]}
                    update_item = {"$set": {"value": state_eval(action["actionData"]["value"], {}, state)}}
                    result = collection.update_one(
                        query,
                        update_item,
                        upsert=(action["actionData"]["actionType"] == "upsert")
                    )
                elif action["actionData"]["actionType"] == "delete":
                    query = {"key": action["actionData"]["key"]}
                    result = collection.delete_one(query)
                else:
                    result = 'action type not implemented'
                script_logger.log('db action result: ', result)
            elif action["actionData"]["databaseType"] == "oracle" or\
                action["actionData"]["databaseType"] == "mysql":
                pass
                # just need DB name
                # have the user input a SQL string to execute
                # to insert variables user SQL variable substitution
            else:
                script_logger.log("DB provider unimplemented")
                raise Exception(action["actionName"] + ' DB provider unimplemented')
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "maskMergeAction":
            # // leftInputExpression: string,
            # // rightInputExpression: string,
            # // joinLeftAt: 'angle' | 'topLeft' | 'top' | 'topRight' | 'right' | 'bottomRight' | 'bottom' | 'bottomLeft' | 'left',
            # // joinRightAt: 'angle' | 'topLeft' | 'top' | 'topRight' | 'right' | 'bottomRight' | 'bottom' | 'bottomLeft' | 'left',
            # // leftMaskType: 'floating' | 'fixed',
            # // rightMaskType: 'floating' | 'fixed',
            # // includeLeftMask: boolean,
            # // includeRightMask: boolean,
            # // includeSpaceBetween: boolean,
            # // fillWith: 'horizontalOverlap' | 'verticalOverlap' | 'linear'
            # // useFillBoundaries: 'left' | 'right' | 'both',
            # // outputVarName: string
            pass
        else:
            return self.python_host.handle_action(action, state, context, run_queue)
        return action, status, state, context, run_queue, []


if __name__ == '__main__':
    pass
