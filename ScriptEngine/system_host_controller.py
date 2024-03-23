from PIL import Image
import tesserocr
import re
import requests
import cv2
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
from script_execution_state import ScriptExecutionState
from script_engine_constants import *
from script_engine_utils import generate_context_switch_action, state_eval
from messaging_helper import MessagingHelper
from script_logger import ScriptLogger
script_logger = ScriptLogger()



class SystemHostController:
    def __init__(self, base_script_name, props):
        self.base_script_name = base_script_name
        self.props = props
        self.messaging_helper = MessagingHelper()

    def handle_action(self, action, state, context, run_queue, log_level, log_folder):
        log_file_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'
        def sanitize_input(statement_input, state):
            statement_input = statement_input.strip()
            statement_input = statement_input.replace('\n', ' ')
            operator_pattern = r'[\[\]()+-/*%=<>!^|&~]'
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
                    except (TypeError,KeyError) as p_err:
                        script_logger.log(p_err)
                        term_eval = None
                    term_str = str(term) + ': ' + str(term_eval) + ': ' + str(type(term_eval))
                statement_strip[term_index] = term_str
            return statement_strip
        if action["actionName"] == "conditionalStatement":
            condition = action["actionData"]["condition"].replace("\n", " ").strip()
            statement_strip = sanitize_input(condition, state)
            script_logger.log('condition : ', condition, statement_strip)
            if state_eval('(' + condition + ')',{}, state):
                script_logger.log('conditionalStatement-' + str(action["actionGroup"]), 'condition success!')
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.log('conditionalStatement-' + str(action["actionGroup"]), 'condition failure!')
                status = ScriptExecutionState.FAILURE
            with open(log_file_path + ('-SUCCESS.txt' if status == ScriptExecutionState.SUCCESS else '-FAILURE.txt'), 'w') as log_file:
                log_file.write(str(condition) + '\n' + str(statement_strip))
            # script_logger.log(' state (7) : ', state)
        elif action["actionName"] == "variableAssignment":
            # script_logger.log('input Parser : ', action["actionData"]["inputParser"])
            outputVarName = action["actionData"]["outputVarName"].strip()
            outputVarNameInState =  outputVarName in state
            if (action["actionData"]["setIfNull"] == "true" or action["actionData"]["setIfNull"])\
                    and outputVarNameInState and state[outputVarName] is not None:
                script_logger.log('output variable ', outputVarName, ' was not null')
                status = ScriptExecutionState.SUCCESS
                with open(log_file_path + '-val.txt', 'w') as log_file:
                    log_file.write('[setIfNull was not null] ' + str(action["actionData"]["inputExpression"]) + ':' + str(state[action["actionData"]["outputVarName"]]))
                return action, status, state, context, run_queue, []

            script_logger.log('variableAssignment-' + str(action["actionGroup"]),' inputExpression : ', action["actionData"]["inputExpression"], end = '')
            # script_logger.log(' state (4) ', state)
            expression = action["actionData"]["inputExpression"].replace("\n", " ")
            if action["actionData"]["inputParser"] == 'eval':
                expression = state_eval(expression, {}, state)
            elif action["actionData"]["inputParser"] == "jsonload":
                expression = json.loads(expression)
            script_logger.log('variableAssignment-' + str(action["actionGroup"]),' : result : ', expression)
            # script_logger.log(' state (5) ', state)
            # script_logger.log(' expression : ', expression, ', ', type(expression))


            script_logger.log('variableAssignment-' + str(action["actionGroup"]), 'state :', list(state))

            if '[' in outputVarName and ']' in outputVarName:
                keys = outputVarName.split('[')  # Split the key string by '][' to get individual keys
                # Evaluate variable names within the state dictionary
                script_logger.log('variableAssignment' + str(action["actionGroup"]) + ' keys', keys)
                for i, k in enumerate(keys[1:]):
                    k = k.rstrip(']')
                    keys[i + 1] = state_eval(k, {}, state)

                # Assign the value to the corresponding key within the state dictionary
                current = state
                script_logger.log('variableAssignment-' + str(action["actionGroup"]) + ' keys', keys)
                for i in range(len(keys) - 1):
                    if keys[i] in current:
                        current = current[keys[i]]
                current[keys[-1]] = expression
                script_logger.log('variableAssignment-' + str(action["actionGroup"]), ' setting ', outputVarName, keys, ' to ', expression)
            else:
                state[outputVarName] = expression
            status = ScriptExecutionState.SUCCESS
            with open(log_file_path + '-val.txt', 'w') as log_file:
                log_file.write(str(outputVarName) + ':' + str(expression))
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                sleep_length = float(state_eval(str(action["actionData"]["inputExpression"]), {}, state))
                script_logger.log('sleepStatement evaluated expression', action["actionData"]["inputExpression"], ' and sleeping for ', sleep_length, 's')
                time.sleep(sleep_length)
            status = ScriptExecutionState.SUCCESS
            with open(log_file_path + '-sleep-{}.txt'.format(sleep_length), 'w') as log_file:
                log_file.write(str(sleep_length))
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "randomVariable":
            delays = RandomVariableHelper.get_rv_val(action)
            state[action["actionData"]["outputVarName"]] = delays
            status = ScriptExecutionState.SUCCESS
            with open(log_file_path + '-output.txt', 'w') as log_file:
                log_file.write(str(delays))
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
                exit(1)

            transform_im = state[action['actionData']['inputExpression']]['matched_area']
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


            cv2.imwrite(log_file_path + '-transformed_image.png', transform_im)
            if len(action['actionData']['outputVarName']) > 0:
                state[action['actionData']['outputVarName']] = state[action['actionData']['inputExpression']].copy()
                state[action['actionData']['outputVarName']]['matched_area'] = transform_im
                state[action['actionData']['outputVarName']]['height'] = transform_im.shape[0]
                state[action['actionData']['outputVarName']]['height'] = transform_im.shape[1]
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "imageToTextAction":
            if action["actionData"]["conversionEngine"] == "tesseractOCR":
                TARGET_TYPE_TO_PSM = {
                    'word': '8',
                    'sentence': '7',
                    'page': '3',
                    'character' : '10',
                    'rawLine' : '13'
                }

                search_im, match_pt = DetectObjectHelper.get_detect_area(action, state)
                image_to_text_input = cv2.cvtColor(search_im.copy(), cv2.COLOR_BGR2GRAY)
                if action["actionData"]["increaseContrast"]:
                    image_to_text_input = cv2.equalizeHist(image_to_text_input)
                if action["actionData"]["invertColors"]:
                    image_to_text_input = cv2.bitwise_not(image_to_text_input)

                im_height = image_to_text_input.shape[0]
                if im_height < 50:
                    image_to_text_input = cv2.resize(image_to_text_input, None, fx=int(100 / im_height), fy=int(100 / im_height), interpolation=cv2.INTER_CUBIC)
                if 'blur' in action['actionData']:
                    if action["actionData"]["blur"] == 'bilateralFilter':
                        image_to_text_input = cv2.bilateralFilter(image_to_text_input, 5, 75, 75)
                    elif action["actionData"]["blur"] == 'medianBlur':
                        image_to_text_input = cv2.medianBlur(image_to_text_input, 3)
                    elif action["actionData"]["blur"] == 'gaussianBlur':
                        image_to_text_input = cv2.GaussianBlur(image_to_text_input, (5, 5), 0)
                if 'binarize' in action['actionData']:
                    if action["actionData"]["binarize"] == 'regular':
                        image_to_text_input = cv2.threshold(
                            image_to_text_input,
                            0,
                            255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU
                        )[1]
                    elif action["actionData"]["binarize"] == 'adaptive':
                        image_to_text_input = cv2.adaptiveThreshold(
                            image_to_text_input,
                            255,
                            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                            cv2.THRESH_BINARY,
                            31,
                            2
                        )
                if 'makeBorder' in action['actionData'] and (
                        action['actionData']['makeBorder'] == True or
                        action['actionData']['makeBorder'] == 'true'
                    ):
                    if len(image_to_text_input.shape) == 2:
                        border_color = int(image_to_text_input[0, 0])
                    else:
                        border_color = list(map(int, image_to_text_input[0,0][::-1]))
                    script_logger.log('imageToText border_color', border_color, type(border_color))
                    # Add a 2-pixel border to the image
                    image_to_text_input = cv2.copyMakeBorder(
                        image_to_text_input, 2, 2, 2, 2,
                        cv2.BORDER_CONSTANT, value=border_color
                    )

                cv2.imwrite(log_file_path + '-image_to_text.png', image_to_text_input)
                tesseract_params = [
                    [
                        TARGET_TYPE_TO_PSM[action['actionData']['targetType']],
                        str(action["actionData"]["characterWhiteList"])
                    ]
                ]
                is_image_to_text_debug_mode = "runMode" in action["actionData"] and action["actionData"]["runMode"] == "debug"
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
                for [psm_value, character_white_list] in tesseract_params:
                    with tesserocr.PyTessBaseAPI() as api:
                        api.SetImage(Image.fromarray(image_to_text_input))
                        api.SetVariable("psm", psm_value)
                        if len(character_white_list) > 0:
                            api.SetVariable("tessedit_char_whitelist", character_white_list)
                        # may want to consider bgr to rgb conversion
                        output_text = api.GetUTF8Text().strip()
                        outputs.append(output_text)
                        script_logger.log('running with options --psm ',
                              psm_value,
                              '--characterWhiteList ',
                              character_white_list if len(character_white_list) > 0 else 'none', 'output : ', output_text)
                with open(log_file_path + '-output.txt', 'w') as log_file:
                    log_file.write(outputs[0])
                if is_image_to_text_debug_mode:
                    for output_index,output in enumerate(outputs[1:]):
                        with open(log_file_path + '-output-debug-psm-' + tesseract_params[output_index + 1][0] + '.txt', 'w') as log_file:
                            log_file.write(output)
                script_logger.log('main output_text : ', outputs[0])
                state[action["actionData"]["outputVarName"]] = outputs[0]
                status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "contextSwitchAction":
            success_states = context["success_states"] if "success_states" in context else None
            script_counter = context["script_counter"]
            script_timer = context["script_timer"]
            if action["actionData"]["state"] is not None:
                state = action["actionData"]["state"].copy()
            if action["actionData"]["context"] is not None:
                context = action["actionData"]["context"].copy()
            if 'state' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["state"].items():
                    state[key] = value
            if 'context' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["context"].items():
                    context[key] = value
            if success_states is not None:
                context["success_states"] = success_states
            context["script_counter"] = script_counter
            context["script_timer"] = script_timer
            status = ScriptExecutionState.SUCCESS
            with open(log_file_path + '-vars.txt', 'w') as log_file:
                log_file.write(str(context["script_counter"]) + '-' + str(context["script_timer"]))
        elif action["actionName"] == "sendMessageAction":
            if action["actionData"]["messagingProvider"] == "viber":
                message = state_eval(action["actionData"]["inputExpression"], {}, state)
                self.messaging_helper.send_viber_message(message)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "returnStatement":
            script_logger.log('returnStatement with params ' + action["actionData"]["returnStatementType"] + ' ' + action["actionData"]["returnStatus"])
            with open(log_file_path + '-return-statement-{}-{}.txt'.format(action["actionData"]["returnStatementType"], action["actionData"]["returnStatus"]), 'w') as log_file:
                log_file.write('returningStatement ran with params: ' + action["actionData"]["returnStatementType"] + ' ' + action["actionData"]["returnStatus"])
            if action["actionData"]["returnStatementType"] == 'exitBranch':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE_BRANCH
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED_BRANCH
            elif action["actionData"]["returnStatementType"] == 'exitScript':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED
            elif action["actionData"]["returnStatementType"] == 'exitProgram':
                script_logger.log('encountered exit program return statement')
                exit(0)
            else:
                script_logger.log('return statement type not implemented', action["actionData"]["returnStatementType"])
                exit(1)
        elif action["actionName"] == "exceptionAction":
            script_logger.log('exceptionAction-' + str(action["actionGroup"]), ' message: ', action["actionData"]["exceptionMessage"])
            if action["actionData"]["takeScreenshot"]:
                pass
            if action["actionData"]["exitProgram"]:
                script_logger.log('exiting program')
                exit(0)
            status = ScriptExecutionState.FINISHED_FAILURE
            with open(log_file_path + '-return-failure.txt', 'w') as log_file:
                log_file.write('returning failure state')
        elif action["actionName"] == "forLoopAction":
            script_logger.log('CONTROL FLOW: initiating forLoopAction-' + str(action["actionGroup"]))

            first_loop = True
            in_variable = state_eval(action["actionData"]["inVariables"], {}, state)

            script_logger.log('forLoopAction-' + str(action["actionGroup"]), 'input inVariable : ', action["actionData"]["inVariables"], ' value: ', in_variable)
            for_variable_list = action["actionData"]["forVariables"].split(',')
            for for_variables in in_variable:
                state_update_dict = {
                    var_name:for_variables[var_index] for var_index,var_name in enumerate(for_variable_list)
                } if len(for_variable_list) > 1 else {
                    for_variable_list[0]:for_variables
                }
                script_logger.log('forLoopAction-' + str(action["actionGroup"]), 'defining forVariables : ', for_variable_list, ' values: ', for_variables)
                if first_loop:
                    state.update(state_update_dict)
                    first_loop = False
                    continue
                switch_action = generate_context_switch_action(action["childGroups"], None, None, {
                    "state": state_update_dict
                })
                run_queue.append(switch_action)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "codeBlock":
            globals = {
                'glob': glob,
                'datetime': datetime,
                'os' : os,
                'shutil' : shutil,
                'numpy' : np
            }
            # statement_strip = sanitize_input(action["actionData"]["codeBlock"], state_copy)
            script_logger.log('codeBlock-' + str(action["actionGroup"]) + ' : ', action["actionData"]["codeBlock"])
            with open(log_file_path + '-codeblock.txt', 'w') as log_file:
                log_file.write(action["actionData"]["codeBlock"])
            exec(action["actionData"]["codeBlock"],globals,state)
            status = ScriptExecutionState.SUCCESS
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
                exit(1)
        else:
            status = ScriptExecutionState.ERROR
            script_logger.log("action unimplemented ")
            script_logger.log(action)
            exit(1)
        return action, status, state, context, run_queue, []


if __name__ == '__main__':
    pass
