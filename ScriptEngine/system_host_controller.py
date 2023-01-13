from PIL import Image
import tesserocr
import re
import requests
import cv2
import json
import time

from detect_object_helper import DetectObjectHelper
from rv_helper import RandomVariableHelper
from script_execution_state import ScriptExecutionState
from script_engine_constants import *



class SystemHostController:
    def __init__(self, props):
        self.props = props

    def handle_action(self, action, state, context, log_level, log_folder):
        log_file_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'
        def sanitize_input(statement_input):
            operator_pattern = r'[()+-/*%=<>!^|&~]'
            word_operator_pattern = r'( is )|( in )|( not )|( and )|( or )'
            statement_strip = re.sub(operator_pattern, ' ', statement_input)
            statement_strip = re.sub(word_operator_pattern, ' ', statement_strip)
            statement_strip = re.sub(word_operator_pattern, ' ', statement_strip)
            statement_strip = list(map(lambda term: str(term) + ': ' + str(eval(term, state_copy)),
                                       filter(lambda term: (len(term) > 0) and "'" not in term and "\"" not in term,
                                              statement_strip.split(' '))))
            return statement_strip
        if action["actionName"] == "conditionalStatement":
            state_copy = state.copy()
            statement_strip = sanitize_input(action["actionData"]["condition"])
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

            print('inputExpression : ', action["actionData"]["inputExpression"], end = '')
            # print(' state (4) ', state)
            expression = None
            if action["actionData"]["inputParser"] == 'eval':
                expression = eval(action["actionData"]["inputExpression"], state.copy())
            elif action["actionData"]["inputParser"] == "jsonload":
                expression = json.loads(action["actionData"]["inputExpression"])
            print(' : result : ', expression)
            # print(' state (5) ', state)
            # print(' expression : ', expression, ', ', type(expression))
            if '[' in action["actionData"]["outputVarName"] and ']' in action["actionData"]["outputVarName"]:
                target_obj_split = action["actionData"]["outputVarName"].split('[')
                target_obj = target_obj_split[0]
                target_obj_attr = target_obj_split[1].split(']')[0]
                state[target_obj][eval(target_obj_attr, state.copy())] = expression
            else:
                state[action["actionData"]["outputVarName"]] = expression
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() != '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state.copy())))
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
            state = action["actionData"]["state"].copy()
            context = action["actionData"]["context"].copy()
            if 'state' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["state"].items():
                    state[key] = value
            if 'context' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["context"].items():
                    context[key] = value
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "sendMessageAction":
            if action["actionData"]["messagingProvider"] == "viber":
                with open(VIBER_CREDENTIALS_FILEPATH, 'r') as creds_file:
                    creds = json.load(creds_file)
                print(requests.post(url=VIBER_CONTROLLER_ENDPOINT_URL, json={
                    'action': 'sendMessage',
                    'payload': eval(action["actionData"]["inputExpression"], state.copy())
                }, headers={
                    'SECRET': creds['SECRET']
                    # 'Authorization' : 'Bearer ' + creds['AUTHORIZATION']
                }).text)
                del creds
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "exceptionAction":
            print(action["actionData"]["exceptionMessage"])
            if action["actionData"]["takeScreenshot"]:
                pass
            if action["actionData"]["exitProgram"]:
                print('exiting program')
                exit(0)
            status = ScriptExecutionState.FINISHED
        else:
            status = ScriptExecutionState.ERROR
            print("action unimplemented ")
            print(action)
            exit(0)
        return status,state,context