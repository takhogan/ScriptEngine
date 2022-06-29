import copy
import json
import sys

import cv2

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from python_host_controller import python_host
from adb_host_controller import adb_host
from detect_object_helper import DetectObjectHelper
import time
import os
import datetime
import pytesseract


class ScriptExecutor:
    def __init__(self, script_obj, log_level='INFO', log_folder=None, context=None, state=None):
        self.log_level = log_level
        self.props = script_obj['props']
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.python_host = python_host(self.props.copy())
        self.adb_host = adb_host(self.props.copy(), self.python_host, '127.0.0.1:5555')
        # TODO IP shouldn't be hard coded
        self.include_scripts = script_obj['include']
        self.log_folder = ('./logs/' + self.props['script_name'] + '-' + self.props['start_time'] if log_folder is None else log_folder)
        os.mkdir(self.log_folder)
        os.mkdir(self.log_folder + '/search_patterns')
        self.log_folder += '/'

        self.state = {

        }
        # print('state (1) : ', state, self.state)
        if state is not None:
            self.state.update(state)

        self.context = {
            'parent_actions': None,
            'parent_action': None,
            'child_actions': None,
            'script_attributes': set(),
            'script_counter': 0,
            'search_patterns': {},
            'replay_stack' : [],
            'action_attempts' : [0] * len(script_obj["actionRows"][0]["actions"]),
            'out_of_attempts' : False,
            'object_handler_encountered' : False
        }
        print('update context : ', context["action_attempts"] if (context is not None and "action_attempts" in context) else 'none')
        if context is not None:
            self.context.update(context)
        print('context (1) : ', self.context["action_attempts"])
        self.status = ScriptExecutionState.FINISHED

    def rewind(self, input_vars):
        print('rewind context : ', self.context["action_attempts"])
        # print('input_vars : ', input_vars)
        # print('state (1.5) ', self.state)
        self.actions = self.action_rows[0]["actions"]
        self.status = ScriptExecutionState.FINISHED
        self.context["action_attempts"] = [0] * len(self.actions)
        if input_vars is not None:
            self.state.update(input_vars)
        # print('state (2) : ', self.state)


    def handle_action(self, action):
        print(self.props["script_name"], ' ', action["actionData"]["targetSystem"],
              ' action : ', action["actionName"],
              ' children: ', list(map(lambda action: action["actionGroup"], self.get_children(action))),
              ' attempts: ', self.context["action_attempts"],
              ' outOfAttempts: ', self.context["out_of_attempts"])
        self.context["script_counter"] += 1
        print(' context (2) : ', self.context["action_attempts"])

        if "targetSystem" in action["actionData"]:
            if action["actionData"]["targetSystem"] == "adb":
                self.adb_host.init_system()
                self.status, self.state, self.context = self.adb_host.handle_action(action, self.state, self.context, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "python":
                self.status, self.state, self.context = self.python_host.handle_action(action, self.state, self.context, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "none":
                if action["actionName"] == 'scriptReference':
                    is_new_script = "initializedScript" not in action["actionData"] or action["actionData"]["initializedScript"] is None
                    if is_new_script:
                        # print('self.context: ', self.context)
                        child_context = {
                            'script_attributes': self.context["script_attributes"].copy()
                        }
                        # print("source: ", action["actionData"]["scriptAttributes"], " target: ", child_context["script_attributes"])
                        child_context["script_attributes"].update(action["actionData"]["scriptAttributes"])
                        # print("child_context: ", child_context, "self context: ", self.context, " actionData: ", action["actionData"]["scriptAttributes"])
                    else:
                        child_context = action["actionData"]["initializedScript"].context
                    # print("child_context: ", child_context, "self context: ", self.context)

                    is_error_handler = 'searchAreaErrorHandler' in child_context["script_attributes"] and \
                                       self.context["parent_action"] is not None and \
                                       self.context["parent_action"]["actionName"] == "searchPatternContinueAction"
                    is_object_handler = 'searchAreaObjectHandler' in child_context["script_attributes"] and \
                                        self.context["parent_action"] is not None and \
                                        self.context["parent_action"]["actionName"] == "searchPatternContinueAction"
                    print('is_error_handler: ', is_error_handler, ', ',
                          'is_object_handler: ', is_object_handler, ', ',
                          'is_new_script: ', is_new_script)

                    parsed_input_vars = list(filter(lambda input_vars: input_vars != '', action["actionData"]["inputVars"].split(",")))
                    # print(' state (2.5) ', self.state)
                    # print(' parsed_input_vars : ', parsed_input_vars)
                    input_vars = {
                        input_var_key : self.state[input_var_key] for input_var_key in parsed_input_vars
                    }
                    # print(' state (3) : ', self.state)
                    input_vars = None if len(input_vars) == 0 else input_vars
                    # creates script engine object
                    if is_new_script:
                        ref_script = self.include_scripts[action["actionData"]["scriptName"]]
                        ref_script["props"]["start_time"] = self.props["start_time"]
                        ref_script["include"] = self.include_scripts
                        script_ref_start_time = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
                        script_ref_log_folder = self.log_folder + action["actionData"]["scriptName"] + '-' + script_ref_start_time

                        if is_error_handler or is_object_handler:
                            search_area_handler_state = {
                                "target_search_pattern" : self.context["search_patterns"][
                                    self.context["parent_action"]["actionData"]["searchPatternID"]
                                ]
                            }
                            if input_vars is not None:
                                input_vars.update(search_area_handler_state)
                            else:
                                input_vars = search_area_handler_state
                            ref_script_executor = ScriptExecutor(
                                ref_script,
                                self.log_level,
                                log_folder=script_ref_log_folder,
                                context=child_context,
                                state=input_vars
                            )
                        else:
                            ref_script_executor = ScriptExecutor(
                                ref_script,
                                self.log_level,
                                log_folder=script_ref_log_folder,
                                context=child_context,
                                state=input_vars
                            )
                    else:
                        action["actionData"]["initializedScript"].rewind(input_vars)
                        ref_script_executor = action["actionData"]["initializedScript"]

                    if 'searchAreaObjectHandler' in child_context["script_attributes"]:
                        ref_script_executor.context["object_handler_encountered"] = False

                    if is_error_handler:
                        if self.context["search_patterns"][
                            self.context["parent_action"]["actionData"]["searchPatternID"]
                        ]["stitcher_status"] != "STITCHER_OK":
                            print('stiching failed, calling error handler ', self.context["search_patterns"][
                                self.context["parent_action"]["actionData"]["searchPatternID"]
                            ]["stitcher_status"])
                            ref_script_executor.run_one()
                        else:
                            ref_script_executor.status = ScriptExecutionState.FINISHED
                    else:
                        if self.context["run_type"] == "run":
                            ref_script_executor.run_one()
                        elif self.context["run_type"] == "run_one":
                            ref_script_executor.run_to_failure()

                    if is_object_handler:
                        self.status = ScriptExecutionState.RETURN
                    elif is_error_handler:
                        if ref_script_executor.status == ScriptExecutionState.FINISHED:
                            self.status = ScriptExecutionState.RETURN
                        else:
                            self.status = ScriptExecutionState.ERROR
                    else:
                        if ref_script_executor.status == ScriptExecutionState.FINISHED:
                            self.status = ScriptExecutionState.SUCCESS
                        elif ref_script_executor.status == ScriptExecutionState.FINISHED_FAILURE:
                            self.status = ScriptExecutionState.FAILURE
                        elif ref_script_executor.status == ScriptExecutionState.FAILURE:
                            self.status = ScriptExecutionState.FAILURE
                        else:
                            self.status = ScriptExecutionState.ERROR
                    action["actionData"]["initializedScript"] = ref_script_executor
                    print(action["actionData"]["scriptName"] + " returning with status " + ref_script_executor.status.name + "/" + self.status.name)
                elif action["actionName"] == "conditionalStatement":
                    print('condition : ', action["actionData"]["condition"])
                    if eval('(' + action["actionData"]["condition"] + ')', self.state.copy()):
                        print('condition success!')
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        print('condition failure!')
                        self.status = ScriptExecutionState.FAILURE
                    # print(' state (7) : ', self.state)
                elif action["actionName"] == "variableAssignment":
                    # print('input Parser : ', action["actionData"]["inputParser"])
                    print('inputExpression : ', action["actionData"]["inputExpression"])
                    # print(' state (4) ', self.state)
                    if action["actionData"]["inputParser"] == 'eval':
                        expression = eval(action["actionData"]["inputExpression"], self.state.copy())
                    elif action["actionData"]["inputParser"] == "jsonload":
                        expression = json.loads(action["actionData"]["inputExpression"])
                    # print(' state (5) ', self.state)
                    # print(' expression : ', expression, ', ', type(expression))
                    self.state[action["actionData"]["outputVarName"]] = expression
                    # print(' state (6) : ', self.state)
                    self.status = ScriptExecutionState.SUCCESS
                elif action["actionName"] == "jsonFileAction":
                    if action["actionData"]["mode"] == "read":
                        with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"], "r") as read_file:
                            self.state[action["actionData"]["varName"]] = json.load(read_file)
                        self.status = ScriptExecutionState.SUCCESS
                    elif action["actionData"]["mode"] == "write":
                        with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"], 'w') as write_file:
                            json.dump(self.state[action["actionData"]["varName"]], write_file)
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        print('invalid mode: ', action)
                        self.status = ScriptExecutionState.ERROR
                elif action["actionName"] == "imageToTextAction":
                    if action["actionData"]["conversionEngine"] == "tesseractOCR":
                        search_im, match_pt = DetectObjectHelper.get_detect_area(action, self.state)
                        cv2.imshow('search_im', search_im)
                        cv2.waitKey(0)

                        print(pytesseract.image_to_string(search_im))
                        exit(0)
                else:
                    self.status = ScriptExecutionState.ERROR
                    print("action unimplemented ")
                    print(action)
                    exit(0)
            else:
                self.status = ScriptExecutionState.ERROR
                print("target system " + action["actionData"]["targetSystem"] + " unimplemented!")
                exit(0)
        else:
            self.status = ScriptExecutionState.ERROR
            print("script formatting error, targetSystem not present!")
            exit(0)
        # print('state (6) : ', self.state)
        print(' context (3) : ', self.context["action_attempts"])
        return action

    def get_out_of_attempts_handlers(self, action):
        if action is None:
            return []
        out_of_attempts_actions = []
        self.context["out_of_attempts"] = False
        for childGroupLink in action["childGroups"]:
            if childGroupLink["type"] == "outOfAttemptsHandler":
                if self.context["action_attempts"][self.context["action_index"]] > childGroupLink["typePayload"]:
                    self.context["out_of_attempts"] = True
                    out_of_attempts_actions.append(
                        self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]
                    )
        return out_of_attempts_actions

    def get_children(self, action):
        # print('get_children ', action)
        child_actions = []

        for childGroupLink in action["childGroups"]:
            if not childGroupLink["type"] == "outOfAttemptsHandler":
                child_actions.append(self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]])
        return child_actions

    def execute_actions(self):
        n_actions = len(self.actions)
        is_return = False
        # print('execute_actions : ', self.actions)
        for action_index in range(0, n_actions):
            self.context["action_index"] = action_index
            action = self.actions[action_index]

            child_actions = self.get_children(action)
            self.context['child_actions'] = child_actions
            out_of_attempts_actions = self.get_out_of_attempts_handlers(self.context['parent_action'])

            # print('out_of_attempt_actions : ', out_of_attempts_actions)
            if len(out_of_attempts_actions) > 0:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                self.actions = out_of_attempts_actions
                self.status = ScriptExecutionState.OUT_OF_ATTEMPTS
                return

            if "searchAreaObjectHandler" in self.context["script_attributes"] and \
                    action["actionName"] == 'detectObject' and \
                    "searchAreaObjectHandler" in action["actionData"]["detectorAttributes"]:
                self.context["object_handler_encountered"] = True

            # print('pre handle: ', action)
            self.actions[action_index] = self.handle_action(action)
            # print('post handle : ', action)
            self.context["action_attempts"][action_index] += 1
            if self.status == ScriptExecutionState.FINISHED:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                self.actions = []
                return
            elif self.status == ScriptExecutionState.SUCCESS:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                # print('acton: ', action, ' childGroups: ', action['childGroups'])
                self.actions = child_actions
                self.context["action_attempts"] = [0] * len(child_actions)
                # print('next: ', self.actions)
                self.status = ScriptExecutionState.STARTING
                return
            elif self.status == ScriptExecutionState.FAILURE:
                self.context['child_actions'] = None
                # if self.context["object_handler_encountered"]:
                #     self.status = ScriptExecutionState.FINISHED_FAILURE
                continue
            elif self.status == ScriptExecutionState.RETURN:
                self.context["child_actions"] = None
                is_return = True
                continue
            else:
                print('encountered error in script and returning ', self.status)
                self.context['child_actions'] = None
                self.status = ScriptExecutionState.ERROR
                return
        if is_return:
            self.actions = [self.context["parent_action"]]
            self.context["action_attempts"] = [0]
            # TODO clearly need to keep track of parent of parent etc
            self.context["parent_action"] = None
            self.status = ScriptExecutionState.RETURN

    def run_to_failure(self, log_level=None):
        self.context["run_type"] = "run_to_failure"
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR and self.status != ScriptExecutionState.FAILURE:
            self.execute_actions()
            # print(self.status, ' status ')
            if len(self.actions) == 0:
                self.status = ScriptExecutionState.FINISHED
                break

    def run_one(self, log_level=None):
        self.context["run_type"] = "run_one"
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        self.execute_actions()
        if self.status == ScriptExecutionState.STARTING:
            self.context["run_type"] = "run"
            while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR and self.status != ScriptExecutionState.FINISHED_FAILURE:
                self.execute_actions()
                # print(self.status, ' status ')
                if len(self.actions) == 0:
                    if len(self.context["replay_stack"]) > 0:
                        replay_stack_item = self.context["replay_stack"].pop()
                        self.actions = [replay_stack_item]
                        self.context["action_attempts"] = [0]
                    else:
                        self.status = ScriptExecutionState.FINISHED
                    break

    # we need a props variable and corresponding json
    # json will be manually editable

    def run(self, log_level=None):
        self.context["run_type"] = "run"
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR:
            self.execute_actions()
            # print(self.status, ' status ')
            if len(self.actions) == 0:
                self.status = ScriptExecutionState.FINISHED
                break



if __name__ == '__main__':
    # TODO DONT LEAVE PASSCODE IN ANY SOURCE CONTORL
    '''
        
        ./adb shell wm size
        ./adb devices | grep "\<device\>"
        
    '''
