from PIL import Image
import tesserocr
import re
import requests
import cv2
import json
import time
import glob
import datetime
import os
import shutil

from pymongo import MongoClient

from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_execution_state import ScriptExecutionState
from script_engine_constants import *
from script_engine_utils import generate_context_switch_action
from messaging_helper import MessagingHelper



class SystemHostController:
    def __init__(self, base_script_name, props):
        self.base_script_name = base_script_name
        self.props = props
        self.messaging_helper = MessagingHelper()

    def handle_action(self, action, state, context, log_level, log_folder):
        log_file_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'
        def sanitize_input(statement_input, state):
            operator_pattern = r'[()+-/*%=<>!^|&~]'
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
                        term_eval = eval(term, state)
                    except (TypeError,KeyError) as p_err:
                        print(p_err)
                        term_eval = None
                    term_str = str(term) + ': ' + str(term_eval) + ': ' + str(type(term_eval))
                statement_strip[term_index] = term_str
            return statement_strip
        if action["actionName"] == "conditionalStatement":
            state_copy = state.copy()
            statement_strip = sanitize_input(action["actionData"]["condition"], state_copy)
            print('condition : ', action["actionData"]["condition"], statement_strip)
            if eval('(' + action["actionData"]["condition"] + ')', state_copy):
                print('condition success!')
                status = ScriptExecutionState.SUCCESS
            else:
                print('condition failure!')
                status = ScriptExecutionState.FAILURE
            # print(' state (7) : ', state)
        elif action["actionName"] == "variableAssignment":
            # print('input Parser : ', action["actionData"]["inputParser"])
            if (action["actionData"]["setIfNull"] == "true" or action["actionData"]["setIfNull"]) and \
                    (action["actionData"]["outputVarName"] in state and \
                     state[action["actionData"]["outputVarName"]] is not None):
                print('output variable ', action["actionData"]["outputVarName"], ' was not null')
                status = ScriptExecutionState.SUCCESS
                return status, state, context

            print('variableAssignment' + str(action["actionGroup"]),'inputExpression : ', action["actionData"]["inputExpression"], end = '')
            # print(' state (4) ', state)
            expression = None
            if action["actionData"]["inputParser"] == 'eval':
                expression = eval(action["actionData"]["inputExpression"], state.copy())
            elif action["actionData"]["inputParser"] == "jsonload":
                expression = json.loads(action["actionData"]["inputExpression"])
            print('variableAssignment' + str(action["actionGroup"]),' : result : ', expression)
            # print(' state (5) ', state)
            # print(' expression : ', expression, ', ', type(expression))


            print('state :', state)
            if '[' in action["actionData"]["outputVarName"] and ']' in action["actionData"]["outputVarName"]:
                keys = action["actionData"]["outputVarName"].split('[')  # Split the key string by '][' to get individual keys
                # Evaluate variable names within the state dictionary
                for i, k in enumerate(keys[1:]):
                    k = k.rstrip(']')
                    if k.isnumeric():
                        keys[i + 1] = int(k)
                    elif k in state:
                        keys[i + 1] = eval(k, state.copy())
                    else:
                        keys[i + 1] = k

                # Assign the value to the corresponding key within the state dictionary
                current = state
                for i in range(len(keys) - 1):
                    current = current[keys[i]]
                current[keys[-1]] = expression
                print('variableAssignment' + str(action["actionGroup"]), ' setting ', action["actionData"]["outputVarName"], keys, ' to ', expression)
            else:
                state[action["actionData"]["outputVarName"]] = expression
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                sleep_length = float(eval(str(action["actionData"]["inputExpression"]), state.copy()))
                print('sleepStatement evaluated expression', action["actionData"]["inputExpression"], ' and sleeping for ', sleep_length, 's')
                time.sleep(sleep_length)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "randomVariable":
            delays = RandomVariableHelper.get_rv_val(action)
            state[action["actionData"]["outputVarName"]] = delays
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "jsonFileAction":
            if action["actionData"]["mode"] == "read":
                with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"],
                          "r") as read_file:
                    state[action["actionData"]["varName"]] = json.load(read_file)
                status = ScriptExecutionState.SUCCESS
            elif action["actionData"]["mode"] == "write":
                print('writing file: ', state[action["actionData"]["varName"]])
                with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"],
                          'w') as write_file:
                    json.dump(state[action["actionData"]["varName"]], write_file)
                status = ScriptExecutionState.SUCCESS
            else:
                print('invalid mode: ', action)
                status = ScriptExecutionState.ERROR
        elif action["actionName"] == "imageToTextAction":
            if action["actionData"]["conversionEngine"] == "tesseractOCR":
                TARGET_TYPE_TO_PSM = {
                    'word': '8',
                    'sentence': '7',
                    'page': '3'
                }

                search_im, match_pt = DetectObjectHelper.get_detect_area(action, state)
                image_to_text_input = cv2.cvtColor(search_im.copy(), cv2.COLOR_BGR2GRAY)
                if action["actionData"]["increaseContrast"]:
                    image_to_text_input = cv2.equalizeHist(image_to_text_input)
                if action["actionData"]["invertColors"]:
                    image_to_text_input = cv2.bitwise_not(image_to_text_input)

                im_height = image_to_text_input.shape[0]
                if im_height < 40:
                    image_to_text_input = cv2.resize(image_to_text_input, None, fx=int(70 / im_height), fy=int(70 / im_height), interpolation=cv2.INTER_CUBIC)
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
                        print('running with options --psm ',
                              psm_value,
                              '--characterWhiteList ',
                              character_white_list if len(character_white_list) > 0 else 'none', 'output : ', output_text)
                with open(log_file_path + '-output.txt', 'w') as log_file:
                    log_file.write(outputs[0])
                if is_image_to_text_debug_mode:
                    for output_index,output in enumerate(outputs[1:]):
                        with open(log_file_path + '-output-debug-psm-' + tesseract_params[output_index + 1][0] + '.txt', 'w') as log_file:
                            log_file.write(output)
                print('main output_text : ', outputs[0])
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
        elif action["actionName"] == "sendMessageAction":
            if action["actionData"]["messagingProvider"] == "viber":
                message = eval(action["actionData"]["inputExpression"], state.copy())
                self.messaging_helper.send_viber_message(message)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "exceptionAction":
            print('exceptionAction-' + str(action["actionGroup"]), ' message: ', action["actionData"]["exceptionMessage"])
            if action["actionData"]["takeScreenshot"]:
                pass
            if action["actionData"]["exitProgram"]:
                print('exiting program')
                exit(0)
            status = ScriptExecutionState.FINISHED_FAILURE
        elif action["actionName"] == "forLoopAction":
            print('CONTROL FLOW: initiating forLoopAction-' + str(action["actionGroup"]))
            if context["run_queue"] is None:
                context["run_queue"] = []
            first_loop = True
            state_copy = state.copy()
            in_variable = eval(action["actionData"]["inVariables"], state_copy)

            print('forLoopAction-' + str(action["actionGroup"]), ' inVariable : ', action["actionData"]["inVariables"], ' value: ', in_variable)
            for_variable_list = action["actionData"]["forVariables"].split(',')
            for for_variables in in_variable:
                state_update_dict = {
                    var_name:for_variables[var_index] for var_index,var_name in enumerate(for_variable_list)
                } if len(for_variable_list) > 1 else {
                    for_variable_list[0]:for_variables
                }
                print('forLoopAction-' + str(action["actionGroup"]), ' forVariables : ', for_variable_list, ' values: ', for_variables)
                if first_loop:
                    state.update(state_update_dict)
                    first_loop = False
                    continue
                switch_action = generate_context_switch_action(action["childGroups"], None, None, {
                    "state": state_update_dict
                })
                context["run_queue"] = [
                    switch_action
                ] + context["run_queue"]
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "codeBlock":
            state_copy = state.copy()
            state_copy.update({
                'glob': glob,
                'datetime': datetime,
                'os' : os,
                'shutil' : shutil
            })
            # statement_strip = sanitize_input(action["actionData"]["codeBlock"], state_copy)
            print('codeBlock-' + str(action["actionGroup"]) + ' : ', action["actionData"]["codeBlock"])
            eval(action["actionData"]["codeBlock"], state_copy)
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
                print(client)
                if len(action["actionData"]["collectionName"]) > 0:
                    collection_name = action["actionData"]["collectionName"]
                else:
                    collection_name = self.base_script_name
                collection = getattr(client, collection_name)

                if action["actionData"]["actionType"] == "insert":
                    if len(action["actionData"]["key"]) > 0:
                        new_item = {"key": action["actionData"]["key"],
                                    "value": eval(action["actionData"]["value"], state.copy())}
                    else:
                        new_item = eval(action["actionData"]["value"], state.copy())
                    result = collection.insert_one(new_item)
                elif action["actionData"]["actionType"] == "update" or\
                        action["actionData"]["actionType"] == "upsert":
                    query = {"key": action["actionData"]["key"]}
                    update_item = {"$set": {"value": eval(action["actionData"]["value"], state.copy())}}
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
                print('db action result: ', result)
            elif action["actionData"]["databaseType"] == "oracle" or\
                action["actionData"]["databaseType"] == "mysql":
                pass
                # just need DB name
                # have the user input a SQL string to execute
                # to insert variables user SQL variable substitution
            else:
                print("DB provider unimplemented")
                exit(1)
        else:
            status = ScriptExecutionState.ERROR
            print("action unimplemented ")
            print(action)
            exit(1)
        return status,state,context


if __name__ == '__main__':
    pass
