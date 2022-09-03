import copy
import json
import shlex
import sys
import datetime
from dateutil import tz

import cv2

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from python_host_controller import python_host
from adb_host_controller import adb_host
from detect_object_helper import DetectObjectHelper
from script_engine_utils import generate_context_switch_action
import time
import os
import datetime
import pytesseract


class ScriptExecutor:
    def __init__(self, script_obj, timeout, log_level='INFO', log_folder=None, context=None, state=None):
        self.timeout = timeout
        self.log_level = log_level
        self.props = script_obj['props']
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.python_host = python_host(self.props.copy())
        self.adb_host = adb_host(self.props.copy(), self.python_host, '127.0.0.1:5555')
        # TODO IP shouldn't be hard coded
        self.include_scripts = script_obj['include']
        self.log_folder = ('./logs/' + self.props['script_name'] + '-' + self.props['start_time'] if log_folder is None else log_folder)
        self.run_queue = []
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
            'run_depth' : 0,
            'branching_behavior' : 'firstMatch',
            'run_type' : 'run',
            'search_patterns': {},
            'action_attempts' : [0] * len(script_obj["actionRows"][0]["actions"]),
            'out_of_attempts' : False,
            'out_of_attempts_action' : None,
            'object_handler_encountered' : False,
            'run_queue' : None
        }
        # print('update context : ', context["action_attempts"] if (context is not None and "action_attempts" in context) else 'none')
        if context is not None:
            self.context.update(context)
        # print('context (1) : ', self.context["action_attempts"])
        self.status = ScriptExecutionState.FINISHED

    def rewind(self, input_vars):
        # print('rewind context : ', self.context["action_attempts"])
        # print('input_vars : ', input_vars)
        # print('state (1.5) ', self.state)
        self.actions = self.action_rows[0]["actions"]
        self.status = ScriptExecutionState.FINISHED
        self.context["action_attempts"] = [0] * len(self.actions)
        if input_vars is not None:
            self.state.update(input_vars)
        # print('state (2) : ', self.state)

    def set_branch(self, action, state, context):
        self.state.update(state)
        self.context.update(context)
        self.actions = [action]


    def handle_action(self, action):
        print(self.props["script_name"], action["actionName"])
        print(self.props["script_name"], ' ', action["actionData"]["targetSystem"],
              ' action : ', action["actionName"] + '-' + str(action["actionGroup"]),
              ' children: ', list(map(lambda action: action["actionGroup"], self.get_children(action))),
              ' attempts: ', self.context["action_attempts"],
              ' outOfAttempts: ', self.context["out_of_attempts"])
        self.context["script_counter"] += 1
        # print(' context (2) : ', self.context["action_attempts"])

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
                            "script_attributes" : self.context["script_attributes"].copy(),
                            "run_type" : action["actionData"]["runMode"],
                            "branching_behavior" : action["actionData"]["branchingBehavior"]
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
                                self.timeout,
                                self.log_level,
                                log_folder=script_ref_log_folder,
                                context=child_context,
                                state=input_vars
                            )
                        else:
                            ref_script_executor = ScriptExecutor(
                                ref_script,
                                self.timeout,
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
                            print('launching error handler')
                            pass
                        else:
                            print('returning without error')
                            self.status = ScriptExecutionState.RETURN
                            return

                    # print('runMode: ', action["actionData"]["runMode"])
                    if action["actionData"]["runMode"] == "run":
                        ref_script_executor.run()
                    elif action["actionData"]["runMode"] == "runOne":
                        ref_script_executor.run_one()
                    elif action["actionData"]["runMode"] == "runToFailure":
                        ref_script_executor.run_to_failure()

                    parsed_output_vars = list(filter(lambda input_vars: input_vars != '', action["actionData"]["outputVars"].split(",")))
                    for output_var in parsed_output_vars:
                        self.state[output_var] = ref_script_executor.state[output_var]

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
                    if '[' in action["actionData"]["outputVarName"] and ']' in action["actionData"]["outputVarName"]:
                        target_obj_split = action["actionData"]["outputVarName"].split('[')
                        target_obj = target_obj_split[0]
                        target_obj_attr = target_obj_split[1].split(']')[0]
                        self.state[target_obj][eval(target_obj_attr, self.state.copy())] = expression
                    else:
                        self.state[action["actionData"]["outputVarName"]] = expression
                    # print(' state (6) : ', self.state)
                    self.status = ScriptExecutionState.SUCCESS
                elif action["actionName"] == "jsonFileAction":
                    if action["actionData"]["mode"] == "read":
                        with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"], "r") as read_file:
                            self.state[action["actionData"]["varName"]] = json.load(read_file)
                        self.status = ScriptExecutionState.SUCCESS
                    elif action["actionData"]["mode"] == "write":
                        print('writing file: ', self.state[action["actionData"]["varName"]])
                        with open(self.props['dir_path'] + '/scriptAssets/' + action["actionData"]["fileName"], 'w') as write_file:
                            json.dump(self.state[action["actionData"]["varName"]], write_file)
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        print('invalid mode: ', action)
                        self.status = ScriptExecutionState.ERROR
                elif action["actionName"] == "imageToTextAction":
                    if action["actionData"]["conversionEngine"] == "tesseractOCR":
                        search_im, match_pt = DetectObjectHelper.get_detect_area(action, self.state)


                        output_text = pytesseract.image_to_string(
                            search_im,
                            config=('-c tessedit_char_whitelist={}'.format(shlex.quote(action["actionData"]["characterWhiteList"]))) if len(action["actionData"]["characterWhiteList"]) > 0 else ''

                        )
                        print(output_text)
                        self.state[action["actionData"]["outputVarName"]] = output_text
                        self.status = ScriptExecutionState.SUCCESS
                elif action["actionName"] == "contextSwitchAction":
                    self.state = action["actionData"]["state"].copy()
                    self.context = action["actionData"]["context"].copy()
                    if 'state' in action["actionData"]["update_dict"]:
                        for key,value in action["actionData"]["update_dict"]["state"].items():
                            self.state[key] = value
                    if 'context' in action["actionData"]["update_dict"]:
                        for key,value in action["actionData"]["update_dict"]["context"].items():
                            self.context[key] = value
                    self.status = ScriptExecutionState.SUCCESS
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
        # print(' context (3) : ', self.context["action_attempts"])

        self.post_handle_action()
        return action

    def post_handle_action(self):
        if self.context['run_queue'] is not None:
            self.run_queue += self.context['run_queue']
            self.context['run_queue'] = None

    def get_out_of_attempts_handler(self, action):
        if action is None:
            return None,None
        # print(action["childGroups"])
        # print(list(filter(lambda childGroupLink: childGroupLink["type"] == "outOfAttemptsHandler", action["childGroups"])))
        out_of_attempts_link = list(filter(lambda childGroupLink: childGroupLink["type"] == "outOfAttemptsHandler", action["childGroups"]))
        # print('link : ', out_of_attempts_link)
        if len(out_of_attempts_link) > 0:
            out_of_attempts_link = out_of_attempts_link[0]
            return self.action_rows[out_of_attempts_link["destRowIndex"]]["actions"][out_of_attempts_link["destActionIndex"]],out_of_attempts_link
        else:
            return None,None


    def get_children(self, action):
        # print('get_children ', action)
        child_actions = []

        for childGroupLink in action["childGroups"]:
            if not childGroupLink["type"] == "outOfAttemptsHandler":
                child_actions.append(self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]])
        return child_actions

    def handle_post_execution(self, action):
        pass

    #if it is handle all branches then you take the first branch and for the rest you create a context switch action
    def execute_actions(self):
        self.handle_out_of_attempts_check()
        n_actions = len(self.actions)
        is_return = False
        # print('execute_actions : ', self.actions)

        if self.context["branching_behavior"] == "firstMatch":
            pass
        elif self.context["branching_behavior"] == "attemptAllBranches" and len(self.actions) > 1:
            state_copy = self.state.copy()
            context_copy = self.context.copy()
            for action in self.actions[1:]:
                self.run_queue.append(
                    generate_context_switch_action(action["childGroups"], state_copy, context_copy, {})
                )
            self.actions = [self.actions[0]]
            n_actions = 1

        for action_index in range(0, n_actions):
            self.context["action_index"] = action_index
            action = self.actions[action_index]

            child_actions = self.get_children(action)
            self.context['child_actions'] = child_actions

            if "searchAreaObjectHandler" in self.context["script_attributes"] and \
                    action["actionName"] == 'detectObject' and \
                    "searchAreaObjectHandler" in action["actionData"]["detectorAttributes"]:
                self.context["object_handler_encountered"] = True

            # print('pre handle: ', action)
            self.actions[action_index] = self.handle_action(action)
            # print('post handle : ', action)
            print(self.context['action_attempts'], action_index)
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
                print('settings action_attempts : ', self.context["action_attempts"])
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

    def check_if_done(self):
        if datetime.datetime.now().astimezone(tz.tzlocal()) > self.timeout:
            print('script timeout')
            exit(0)
        if len(self.actions) == 0 and len(self.run_queue) == 0:
            self.status = ScriptExecutionState.FINISHED
            return
        if len(self.run_queue) > 0:
            self.actions.append(self.run_queue.pop())

    def handle_out_of_attempts_check(self):
        out_of_attempts_handler,out_of_attempts_link = self.get_out_of_attempts_handler(self.context['parent_action'])
        # print('handler : ', out_of_attempts_handler)
        if out_of_attempts_handler is not None:
            self.context["out_of_attempts_action"] = {
                "action" : out_of_attempts_handler,
                "link" : out_of_attempts_link
            }
        else:
            self.context["out_of_attempts"] = False
            return
        if self.context["action_attempts"][0] > self.context["out_of_attempts_action"]["link"]["typePayload"]:
            self.actions = [self.context["out_of_attempts_action"]["action"]]
            self.context["action_attempts"] = [0]
            self.context["action_index"] = 0
            self.context["out_of_attempts"] = True
        else:
            self.context["out_of_attempts"] = False

    def should_continue_on_failure(self):
        if self.context["run_type"] == "runOne" and self.context["run_depth"] == 1:
            return False
        elif self.context["run_type"] == "runToFailure":
            return False
        else:
            return True

    def handle_branch(self):
        self.handle_out_of_attempts_check()

        child_actions = self.get_children(self.actions[0])
        self.context['child_actions'] = child_actions

        self.actions[0] = self.handle_action(self.actions[0])
        self.context["action_attempts"][0] += 1
        self.context['parent_action'] = self.actions[0]

        if self.status == ScriptExecutionState.FINISHED:
            self.actions = []
            return
        elif self.status == ScriptExecutionState.SUCCESS:
            # print('acton: ', action, ' childGroups: ', action['childGroups'])
            self.actions = child_actions
            self.run_all_branches()
            self.status = ScriptExecutionState.STARTING
            return
        elif self.status == ScriptExecutionState.FAILURE:
            # if self.context["object_handler_encountered"]:
            #     self.status = ScriptExecutionState.FINISHED_FAILURE
            if self.should_continue_on_failure():
                self.handle_branch()
            else:
                return
        elif self.status == ScriptExecutionState.RETURN:
            self.status = ScriptExecutionState.RETURN
            return
        else:
            print('encountered error in script and returning ', self.status)
            self.context['child_actions'] = None
            self.status = ScriptExecutionState.ERROR
            return




    def run_all_branches(self, log_level=None):
        # self.context["run_type"] = run_type
        # if 'attemptAllBranches' in self.context["script_attributes"]:
        branches = [[action, self.state.copy(), self.context.copy()] for action in self.actions]
        # self.context['run']
        self.context["run_depth"] += 1
        for branch in branches:
            new_context = branch[2]
            new_context["action_attempts"] = [0]
            new_context["action_index"] = 0
            branch[2] = new_context
            self.set_branch(*branch)
            self.handle_branch()
        # pseudo code:
        # for each child, rewind back to child and run script
        # if status is finished, parse the run queue and mark as not finished
        # rewind should include detect object index, for click action to hone in on,
        # detect object will add the necessary args to the run queue
        # run queue will be a list of actions and the associated params that should persist

    def run_to_failure(self, log_level=None):
        print("runMode: runToFailure ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR and self.status != ScriptExecutionState.FAILURE:
            self.execute_actions()
            # print(self.status, ' status ')
            self.check_if_done()



    def run_one(self, log_level=None):
        print("runMode: runOne ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        self.execute_actions()
        if self.status == ScriptExecutionState.STARTING:
            self.run(log_level)



    # we need a props variable and corresponding json
    # json will be manually editable

    def run(self, log_level=None):
        print("runMode: run ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR:
            self.execute_actions()
            self.check_if_done()







if __name__ == '__main__':
    # TODO DONT LEAVE PASSCODE IN ANY SOURCE CONTORL
    '''
        
        ./adb shell wm size
        ./adb devices | grep "\<device\>"
        
    '''
