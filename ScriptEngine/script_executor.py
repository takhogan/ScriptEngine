import copy
import json
import shlex
import sys
import datetime
from dateutil import tz
from PIL import Image
import tesserocr
import random
import re

import cv2

sys.path.append("..")
from script_engine_constants import *
from script_execution_state import ScriptExecutionState
from python_host_controller import python_host
from adb_host_controller import adb_host
from script_engine_utils import generate_context_switch_action
from script_logger import ScriptLogger
from system_host_controller import SystemHostController


import time
import os
import datetime
import pytesseract
import requests

DETECT_TYPES_SET = {
    'detectObject',
    'declareScene'
}

FORWARD_PEEK_EXEMPT_ACTIONS = {
    'contextSwitchAction'
}

DELAY_EXEMPT_ACTIONS = {
    'declareObject',
    'sleepStatement',
    'scriptReference',
    'conditionalStatement',
    'variableAssignment',
    'jsonFileAction',
    'imageToTextAction',
    'contextSwitchAction'
}



class ScriptExecutor:
    def __init__(self, script_obj, timeout, log_level='INFO', parent_folder='', start_time=None, context=None, state=None, create_log_folders=True):
        self.props = script_obj['props']
        if start_time is None:
            self.refresh_start_time()
        else:
            self.props['start_time'] = start_time
        self.timeout = timeout
        self.props["timeout"] = timeout
        self.log_level = log_level
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.inputs = script_obj["inputs"]
        self.python_host = python_host(self.props.copy())
        self.system_host = SystemHostController(self.props.copy())
        self.adb_host = adb_host(self.props.copy(), self.python_host, '127.0.0.1:5555')
        # TODO IP shouldn't be hard coded
        self.include_scripts = script_obj['include']
        self.run_queue = []

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
            'run_queue': None,
            'actionOrder': 'sequential',
            'success_states': None
        }
        # print('update context : ', context["action_attempts"] if (context is not None and "action_attempts" in context) else 'none')
        if context is not None:
            self.context.update(context)
        # print('context (1) : ', self.context["action_attempts"])
        self.status = ScriptExecutionState.FINISHED
        if create_log_folders:
            self.create_log_folders(parent_folder)

    def refresh_start_time(self):
        self.props["start_time"] = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')

    def create_log_folders(self, parent_folder='', refresh_start_time=False):
        if refresh_start_time:
            self.refresh_start_time()
        self.log_folder = ('./logs/' if parent_folder == '' else parent_folder) +\
              str(self.context['script_counter']).zfill(5) + '-' +\
              self.props['script_name'] + '-' + self.props['start_time']

        os.makedirs(self.log_folder + '/search_patterns', exist_ok=True)
        self.log_folder += '/'
        self.logger = ScriptLogger(self.log_folder)

    def rewind(self, input_vars):
        # print('rewind context : ', self.context["action_attempts"])
        # print('input_vars : ', input_vars)
        # print('state (1.5) ', self.state)
        self.actions = self.action_rows[0]["actions"]
        self.status = ScriptExecutionState.FINISHED
        self.context["action_attempts"] = [0] * len(self.actions)
        self.context["success_states"] = None
        if input_vars is not None:
            self.state.update(input_vars)
        # print('state (2) : ', self.state)

    def parse_inputs(self):
        print(self.props['script_name'] + ' CONTROL FLOW: parsing_inputs ', self.inputs)
        for [var_name, input_expression, default_value] in self.inputs:
            if (len(input_expression) == 0) or \
               ((default_value or default_value == "true") and (var_name in self.state and self.state[var_name] is not None)):
                continue
            eval_result = eval(input_expression, self.state.copy())
            self.state[var_name] = eval_result
            print(self.props['script_name'] + ' CONTROL FLOW:   Parsing Input: ', var_name, " Value: ", eval_result)

    def log_action_details(self, action):
        print(
            str(self.context['script_counter']).zfill(5) + ' ' + \
            self.props["script_name"] + ' ' + action["actionData"]["targetSystem"] + \
            ' action : ' + action["actionName"] + '-' + str(action["actionGroup"]) + \
            ' children: ' + str(list(map(lambda action: action["actionGroup"], self.get_children(action)))) + \
            ' attempts: ' + str(self.context["action_attempts"]) + \
            ' outOfAttempts: ' + str(self.context["out_of_attempts"])
        )


    def forward_detect_peek(self):
        detect_types_by_target_system = {}
        for action_index,action in enumerate(self.actions):
            if action['actionName'] in DETECT_TYPES_SET:
                # if len(action['actionData']['inputExpression']) > 0:
                #     pass
                # else:
                target_system = action['actionData']['targetSystem']
                if target_system in detect_types_by_target_system:
                    detect_types_by_target_system[target_system].append([action_index,action])
                else:
                    detect_types_by_target_system[target_system] = [[action_index,action]]
        print(self.props['script_name'] + ' CONTROL FLOW: performing forward peek')
        for target_system,actions in detect_types_by_target_system.items():
            if target_system == 'adb':
                self.adb_host.init_system()
                screenshot = self.adb_host.screenshot()
                for [action_index,action] in actions:
                    self.log_action_details(action)
                    action['actionData']['screencap_im_bgr'] = screenshot
                    action['actionData']['detect_run_type'] = 'result_precalculation'
                    action['actionData']['results_precalculated'] = False
                    self.status, self.state, self.context = self.adb_host.handle_action(
                        action, self.state, self.context, self.log_level, self.log_folder
                    )
                    self.actions[action_index] = self.context['action']
            elif target_system == 'python':
                screenshot = self.python_host.screenshot()
                for [action_index,action] in actions:
                    self.log_action_details(action)
                    action['actionData']['screencap_im_bgr'] = screenshot
                    action['actionData']['detect_run_type'] = 'result_precalculation'
                    action['actionData']['results_precalculated'] = False
                    self.status, self.state, self.context = self.python_host.handle_action(
                        action, self.state, self.context, self.log_level, self.log_folder
                    )
                    self.actions[action_index] = self.context['action']
        print(self.props['script_name'] + ' CONTROL FLOW: Finished forward peek')


    def handle_action(self, action):
        self.log_action_details(action)
        self.context["script_counter"] += 1
        # print(' context (2) : ', self.context["action_attempts"])
        # if action["actionName"] not in DELAY_EXEMPT_ACTIONS:
            # time.sleep(0.25)

        if "targetSystem" in action["actionData"]:
            if action["actionData"]["targetSystem"] == "adb":
                self.adb_host.init_system()
                self.status, self.state, self.context = self.adb_host.handle_action(action, self.state, self.context, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "python":
                self.status, self.state, self.context = self.python_host.handle_action(action, self.state, self.context, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "none":
                if action["actionName"] == "scriptReference":
                    self.status, self.state, self.context = self.handle_script_reference(action, self.state, self.context)
                else:
                    self.status, self.state, self.context = self.system_host.handle_action(action, self.state, self.context, self.log_level, self.log_folder)
            else:
                self.status = ScriptExecutionState.ERROR
                print("target system " + action["actionData"]["targetSystem"] + " unimplemented!")
                exit(0)
        else:
            self.status = ScriptExecutionState.ERROR
            print("script formatting error, targetSystem not present!")
            exit(0)

        self.post_handle_action()
        return action

    def handle_script_reference(self, action, state, context):
        if action["actionName"] == 'scriptReference':
            is_new_script = "initializedScript" not in action["actionData"] or action["actionData"][
                "initializedScript"] is None
            if is_new_script:
                # print('context: ', context)
                child_context = {
                    "script_attributes": context["script_attributes"].copy(),
                    "run_type": action["actionData"]["runMode"],
                    "branching_behavior": action["actionData"]["branchingBehavior"]
                }
                # print("source: ", action["actionData"]["scriptAttributes"], " target: ", child_context["script_attributes"])
                child_context["script_attributes"].update(action["actionData"]["scriptAttributes"])
                # print("child_context: ", child_context, "self context: ", context, " actionData: ", action["actionData"]["scriptAttributes"])
            else:
                child_context = action["actionData"]["initializedScript"].context
            # print("child_context: ", child_context, "self context: ", context)

            is_error_handler = 'searchAreaErrorHandler' in child_context["script_attributes"] and \
                               context["parent_action"] is not None and \
                               context["parent_action"]["actionName"] == "searchPatternContinueAction"
            is_object_handler = 'searchAreaObjectHandler' in child_context["script_attributes"] and \
                                context["parent_action"] is not None and \
                                context["parent_action"]["actionName"] == "searchPatternContinueAction"

            parsed_input_vars = list(
                filter(lambda input_vars: input_vars != '', action["actionData"]["inputVars"].split(",")))
            # print(' state (2.5) ', state)
            # print(' parsed_input_vars : ', parsed_input_vars)
            input_vars = {
                input_var_key: state[input_var_key]
                if input_var_key in state else None
                for input_var_key in parsed_input_vars
            }
            # print(' state (3) : ', state)
            input_vars = None if len(input_vars) == 0 else input_vars
            # creates script engine object
            if is_new_script:
                script_name = action["actionData"]["scriptName"].strip()
                if script_name[0] == '{' and script_name[-1] == '}':
                    script_name = eval(script_name[1:-1], self.state.copy())
                ref_script = self.include_scripts[script_name]
                ref_script['include'] = self.include_scripts
                child_context["actionOrder"] = action["actionData"]["actionOrder"] if "actionOrder" in action["actionData"] else "sequential"
                child_context["scriptMaxActionAttempts"] = action["actionData"]["scriptMaxActionAttempts"] if "scriptMaxActionAttempts" in action["actionData"] else ""
                child_context["onOutOfActionAttempts"] = action["actionData"]["onOutOfActionAttempts"] if "onOutOfActionAttempts" in action["actionData"] else "returnFailure"
                child_context["script_counter"] = self.context["script_counter"]

                if is_error_handler or is_object_handler:
                    search_area_handler_state = {
                        "target_search_pattern": context["search_patterns"][
                            context["parent_action"]["actionData"]["searchPatternID"]
                        ]
                    }
                    if input_vars is not None:
                        input_vars.update(search_area_handler_state)
                    else:
                        input_vars = search_area_handler_state
                    ref_script_executor = ScriptExecutor(
                        ref_script,
                        self.props["timeout"],
                        self.log_level,
                        parent_folder=self.log_folder,
                        context=child_context,
                        state=input_vars,
                        create_log_folders=False
                    )
                else:
                    ref_script_executor = ScriptExecutor(
                        ref_script,
                        self.props["timeout"],
                        self.log_level,
                        parent_folder=self.log_folder,
                        context=child_context,
                        state=input_vars,
                        create_log_folders=False
                    )
            else:
                action["actionData"]["initializedScript"].rewind(input_vars)
                ref_script_executor = action["actionData"]["initializedScript"]
                print(self.props['script_name'], 'with script counter', self.context["script_counter"],
                      'sending script_counter')

                ref_script_executor.context["script_counter"] = self.context["script_counter"]

            if 'searchAreaObjectHandler' in child_context["script_attributes"]:
                ref_script_executor.context["object_handler_encountered"] = False

            if is_error_handler:
                if context["search_patterns"][
                    context["parent_action"]["actionData"]["searchPatternID"]
                ]["stitcher_status"] != "STITCHER_OK":
                    print('launching error handler')
                    pass
                else:
                    print('returning without error')
                    status = ScriptExecutionState.RETURN
                    return status, state, context

            # print('runMode: ', action["actionData"]["runMode"])
            ref_script_executor.create_log_folders(
                parent_folder=self.log_folder,
                refresh_start_time=True
            )
            if action["actionData"]["runMode"] == "run":
                ref_script_executor.run()
            elif action["actionData"]["runMode"] == "runOne":
                ref_script_executor.run_one()
            elif action["actionData"]["runMode"] == "runToFailure":
                ref_script_executor.run_to_failure()

            parsed_output_vars = list(
                filter(lambda output_vars: output_vars != '', action["actionData"]["outputVars"].split(","))
            )
            print(self.props['script_name'] + ' CONTROL FLOW: parsing output vars ', parsed_output_vars)
            for output_var in parsed_output_vars:
                output_var_val = ref_script_executor.state[
                    output_var] if output_var in ref_script_executor.state else None
                state[output_var] = output_var_val
                print(self.props['script_name'] + " CONTROL FLOW: output var ", output_var,':', output_var_val)
            self.context["script_counter"] = ref_script_executor.context["script_counter"]

            if is_object_handler:
                status = ScriptExecutionState.RETURN
            elif is_error_handler:
                if ref_script_executor.status == ScriptExecutionState.FINISHED:
                    status = ScriptExecutionState.RETURN
                else:
                    status = ScriptExecutionState.ERROR
            else:
                if ref_script_executor.status == ScriptExecutionState.FINISHED:
                    status = ScriptExecutionState.SUCCESS
                elif ref_script_executor.status == ScriptExecutionState.FINISHED_FAILURE:
                    status = ScriptExecutionState.FAILURE
                elif ref_script_executor.status == ScriptExecutionState.FAILURE:
                    status = ScriptExecutionState.FAILURE
                else:
                    status = ScriptExecutionState.ERROR
            action["actionData"]["initializedScript"] = ref_script_executor
            print(action["actionData"][
                      "scriptName"] + " returning with status " + ref_script_executor.status.name + "/" + status.name)
        return status, state, context

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

    def check_if_done(self):
        print(self.props['script_name'] + ' CONTROL FLOW: Checking if done.', len(self.actions), " remaining action in branch. ", len(self.run_queue), " remaining branches")
        if datetime.datetime.now().astimezone(tz.tzlocal()) > self.timeout:
            print(self.props['script_name'] + ' CONTROL FLOW: script timeout - ', datetime.datetime.now())
            return True
        terminate_request = False
        if os.path.exists(RUNNING_SCRIPTS_PATH):
            with open(RUNNING_SCRIPTS_PATH, 'r') as temp_file:
                if not len(temp_file.read()) > 0:
                    terminate_request = True
        else:
            terminate_request = True
        if terminate_request:
            print(self.props['script_name'] + ' CONTROL FLOW: received terminate request')
            return True

        if "scriptMaxActionAttempts" in self.context and\
                len(str(self.context["scriptMaxActionAttempts"])) > 0 and\
                len(self.context["action_attempts"]) > 0 and\
                max(self.context["action_attempts"]) > int(self.context["scriptMaxActionAttempts"]):
            self.status = ScriptExecutionState.FAILURE
            print(self.props['script_name'] + " CONTROL FLOW: Action attempts", self.context["action_attempts"], "exceeded scriptMaxActionAttempts of", self.context["scriptMaxActionAttempts"])
            return True
        if len(self.actions) == 0 and len(self.run_queue) == 0:
            print(self.props['script_name'] + ' CONTROL FLOW: Reached end of script')
            if self.status == ScriptExecutionState.FINISHED_FAILURE:
                pass
            else:
                self.status = ScriptExecutionState.FINISHED
            return True
        if len(self.actions) == 0 and len(self.run_queue) > 0:
            print(self.props['script_name'] + ' CONTROL FLOW: Finished branch, moving to next')
            self.status = ScriptExecutionState.FINISHED_BRANCH
            self.start_new_branch()
        return False


    def should_continue_on_failure(self):
        if self.context["run_type"] == "runOne" and self.context["run_depth"] == 1:
            return False
        elif self.context["run_type"] == "runToFailure":
            return False
        else:
            return True


    #if it is handle all branches then you take the first branch and for the rest you create a context switch action
    def execute_actions(self, forward_peek=True):
        self.handle_out_of_attempts_check()
        if forward_peek:
            self.forward_detect_peek()
        n_actions = len(self.actions)
        is_return = False
        if self.context["branching_behavior"] == "firstMatch":
            pass
        elif self.context["branching_behavior"] == "attemptAllBranches" and len(self.actions) > 1:
            state_copy = self.state.copy()
            context_copy = self.context.copy()
            for action in self.actions[1:]:
                self.run_queue.append(
                    generate_context_switch_action([{
                        'srcGroup': None,
                        'srcRowIndex': None,
                        'srcActionIndex': None,
                        'destGroup': action['actionGroup'],
                        'destRowIndex': action['rowIndex'],
                        'destActionIndex': action['actionIndex'],
                        'coords': None,
                        'long': None,
                        'isPipeLink': None,
                        'type': 'firstMatch',
                        'typePayload': None
                    }], state_copy, context_copy, {})
                )
            self.actions = [self.actions[0]]
            n_actions = 1

        if self.context["actionOrder"] == "random":
            print("shuffling")
            random.shuffle(self.actions)

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
            self.context["action_attempts"][action_index] += 1
            if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_FAILURE:
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
                print(self.props['script_name'] + ' CONTROL FLOW: encountered error in script and returning ', self.status)
                self.context['child_actions'] = None
                self.status = ScriptExecutionState.ERROR
                return
        if is_return:
            self.actions = [self.context["parent_action"]]
            self.context["action_attempts"] = [0]
            # TODO clearly need to keep track of parent of parent etc
            self.context["parent_action"] = None
            self.status = ScriptExecutionState.RETURN


    def run_to_failure(self, log_level=None, parse_inputs=True):
        if parse_inputs:
            self.parse_inputs()
        print(self.props['script_name'] + " CONTROL FLOW: Running script with runMode: runToFailure ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        overall_status = ScriptExecutionState.FAILURE
        while self.status != ScriptExecutionState.FINISHED and\
                self.status != ScriptExecutionState.ERROR and\
                self.status != ScriptExecutionState.FAILURE and\
                self.status != ScriptExecutionState.FINISHED_FAILURE:
            self.execute_actions()
            if self.check_if_done():
                break
            if self.status == ScriptExecutionState.FAILURE:
                self.actions = []
                # if there are actions in the run queue, there are additional actions to check for failure
                if len(self.run_queue) > 0:
                    self.start_new_branch()
                    self.status = ScriptExecutionState.STARTING
                    continue
                else:
                    # otherwise return with failure state
                    break
            elif self.status == ScriptExecutionState.FINISHED_BRANCH:
                overall_status = ScriptExecutionState.SUCCESS
        # if at least one branch reached the end the script is a success
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        self.on_script_completion()





    def run_one(self, log_level=None, parse_inputs=True):
        if parse_inputs:
            self.parse_inputs()
        print(self.props['script_name'] + " CONTROL FLOW: Running script with runMode: runOne ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        branches = []
        is_attempt_all_branches = self.context["branching_behavior"] == "attemptAllBranches"
        if is_attempt_all_branches:
            # this exists because otherwise the runOne would always run because the context switch is always successful
            state_copy = self.state.copy()
            context_copy = self.context.copy()
            if self.context["actionOrder"] == "random":
                random.shuffle(self.actions)
            for action in self.actions:
                branches.append(
                    [generate_context_switch_action([{
                        'srcGroup': None,
                        'srcRowIndex': None,
                        'srcActionIndex': None,
                        'destGroup': action['actionGroup'],
                        'destRowIndex': action['rowIndex'],
                        'destActionIndex': action['actionIndex'],
                        'coords': None,
                        'long': None,
                        'isPipeLink': None,
                        'type': 'firstMatch',
                        'typePayload': None
                    }], state_copy, context_copy, {})]
                )
        else:
            branches = [self.actions]

        overall_status = ScriptExecutionState.FAILURE
        for branch in branches:
            self.actions = branch
            if is_attempt_all_branches:
                self.execute_actions()
            print(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, performing first pass')
            self.execute_actions()
            if self.status == ScriptExecutionState.STARTING:
                print(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, first pass successful, switching to run mode run')
                self.run(log_level, parse_inputs=False)
                if not is_attempt_all_branches:
                    break
                elif self.status == ScriptExecutionState.FINISHED:
                    overall_status = ScriptExecutionState.SUCCESS
            else:
                self.actions = []
                if len(self.run_queue) > 1:
                    if self.check_if_done():
                        break
                    # because the first action will be a context switch action
                    self.execute_actions()
                    self.run_one(parse_inputs=False)
                    if not is_attempt_all_branches:
                        break
                    elif self.status == ScriptExecutionState.FINISHED:
                        overall_status = ScriptExecutionState.SUCCESS
        # if you reached the end on one of the branches
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        self.on_script_completion()
        #TODO In theory you should load in the state and context of the successful branch

    def run(self, log_level=None, parse_inputs=True):
        self.parse_inputs()
        print(self.props['script_name'] + " CONTROL FLOW: Running script with runMode: run ", "branchingBehavior: ", self.context["branching_behavior"])
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        overall_status = ScriptExecutionState.FAILURE
        while self.status != ScriptExecutionState.FINISHED and\
                self.status != ScriptExecutionState.FINISHED_FAILURE and\
                self.status != ScriptExecutionState.ERROR:
            self.execute_actions()
            if self.check_if_done():
                break
            if self.status == ScriptExecutionState.FINISHED_BRANCH:
                overall_status = ScriptExecutionState.SUCCESS
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        self.on_script_completion()

    def on_script_completion(self):
        if self.context["success_states"] is not None:
            self.state = self.context["success_states"][-1]

    def start_new_branch(self):
        if self.status == ScriptExecutionState.FINISHED_BRANCH:
            if self.context["success_states"] is None:
                self.context["success_states"] = [self.state.copy()]
            else:
                self.context["success_states"] += [self.state.copy()]
        self.actions.append(self.run_queue.pop())







if __name__ == '__main__':
    # TODO DONT LEAVE PASSCODE IN ANY SOURCE CONTORL
    '''
        
        ./adb shell wm size
        ./adb devices | grep "\<device\>"
        
    '''
