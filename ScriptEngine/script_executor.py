
import sys
import datetime
from dateutil import tz

import random
import re
import glob

sys.path.append("..")
from device_manager import DeviceManager
from detect_object_helper import DetectObjectHelper
from parallelized_script_executor import ParallelizedScriptExecutor
from script_engine_constants import *
from script_execution_state import ScriptExecutionState
from script_execution_status_detail import ScriptExecutionStatusDetail
from script_engine_utils import generate_context_switch_action,get_running_scripts, is_parallelizeable, datetime_to_local_str, state_eval
from script_loader import parse_zip
from system_script_handler import SystemScriptHandler
from script_logger import ScriptLogger
from script_action_log import ScriptActionLog
from rv_helper import RandomVariableHelper
from typing import Callable, Dict, List, Tuple
script_logger = ScriptLogger()




import time
import os
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
    def __init__(self,
                 script_obj,
                 timeout,
                 base_script_name,
                 base_start_time_str,
                 script_id,
                 device_manager : DeviceManager,
                 process_executor,
                 parent_folder='',
                 script_start_time=None,
                 context=None,
                 state=None,
                 create_log_folders=True):
        self.script_id = script_id
        self.base_script_name = base_script_name
        self.base_start_time_str = base_start_time_str
        self.device_manager = device_manager
        self.process_executor = process_executor
        self.parallelized_executor = ParallelizedScriptExecutor(self.process_executor)
        self.props = script_obj['props']
        if script_start_time is None:
            self.refresh_start_time()
        else:
            self.props['script_start_time'] = script_start_time
        self.timeout = timeout
        self.props["timeout"] = timeout
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.inputs = script_obj["inputs"]
        self.outputs = script_obj["outputs"]

        # TODO IP shouldn't be hard coded
        self.include_scripts = script_obj['include']
        self.run_queue = []

        self.state = {

        }
        # script_logger.log('state (1) : ', state, self.state)
        if state is not None:
            self.state.update(state)

        self.context = {
            'parent_actions': None,
            'parent_action': None,
            'child_actions': None,
            'script_attributes': set(),
            'script_counter': 0,
            'script_timer' : datetime.datetime.now(),
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
            'success_states': None,
            'mouse_down' : False
        }
        self.parent_action_log = None
        self.script_action_log = None
        # script_logger.log('update context : ', context["action_attempts"] if (context is not None and "action_attempts" in context) else 'none')
        if context is not None:
            self.context.update(context)
        # script_logger.log('context (1) : ', self.context["action_attempts"])
        self.status = ScriptExecutionState.FINISHED
        self.status_detail = None
        if create_log_folders:
            self.create_log_folders(parent_folder)
            self.set_log_paths()

    def refresh_start_time(self):
        self.props["script_start_time"] = datetime.datetime.now().astimezone(tz=tz.tzutc())

    def create_log_folders(self, parent_folder='', refresh_start_time=False):
        if refresh_start_time:
            self.refresh_start_time()
        self.log_folder = ('./logs/' if parent_folder == '' else parent_folder) +\
              str(self.context['script_counter']).zfill(5) + '-' +\
              self.props['script_name'] + '-' + datetime_to_local_str(self.props['script_start_time'], delim='-')

        os.makedirs(self.log_folder + '/search_patterns', exist_ok=True)
        self.log_folder += '/'
        if self.parent_action_log is not None:
            script_logger.log('adding supporting file reference for', self.props['script_name'], script_logger.get_action_log().get_action_log_path())
            self.parent_action_log.add_supporting_absolute_file_reference('text', self.log_folder + 'stdout.txt')
        return self.log_folder

    def set_log_paths(self):
        script_logger.set_log_file_path(self.log_folder + 'stdout.txt')
        script_logger.set_log_folder(self.log_folder)

    def set_parent_action_log(self, script_action_log : ScriptActionLog):
        self.parent_action_log = script_action_log

    def rewind(self, input_vars):
        # script_logger.log('rewind context : ', self.context["action_attempts"])
        # script_logger.log('input_vars : ', input_vars)
        # script_logger.log('state (1.5) ', self.state)
        self.actions = self.action_rows[0]["actions"]
        self.status = ScriptExecutionState.FINISHED
        self.status_detail = None
        self.context["action_attempts"] = [0] * len(self.actions)
        self.context["success_states"] = None
        self.context["run_queue"] = None
        self.run_queue = []
        if input_vars is not None:
            self.state.update(input_vars)
        # script_logger.log('state (2) : ', self.state)

    def parse_inputs(self, input_state):
        with open(self.log_folder + 'inputs.txt', 'w') as input_log_file:
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: parsing_inputs ', self.inputs)
            for [var_name, input_expression, default_value] in self.inputs:
                var_name = var_name.strip()
                if len(input_expression.strip()) == 0:
                    input_expression = 'None'
                if (default_value or default_value == "true") and (var_name in input_state and input_state[var_name] is not None):
                    script_logger.log(self.props['script_name'],' CONTROL FLOW: Parsing Input: ', var_name,
                          " Default Parameter? ", default_value,
                          " Overwriting Default? True" if default_value else "Reading from input state")
                    try:
                        self.state[var_name] = input_state[var_name]
                    except KeyError as k:
                        script_logger.log('ERROR: key error while parsing output, keys present in input state: ' + ', '.join(list(input_state)))
                        raise
                    script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsed Input: ', var_name,
                                      " Value: ", input_state[var_name] if var_name in input_state else 'None'
                    )
                    input_log_file.write(str(type(self.state[var_name])) + ' ' + str(var_name) + ': ' + str(self.state[var_name]) + '\n')
                    continue
                globs = {
                    'glob' : glob,
                    'datetime' : datetime,
                    're' : re
                }
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsing Input: ', var_name,
                                  " Default Parameter? ", default_value,
                                  " Overwriting Default? False" if default_value else "")
                state_copy = self.state.copy()
                state_copy.update(input_state)
                eval_result = state_eval(input_expression, globs, state_copy)
                self.state[var_name] = eval_result
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsed Input: ', var_name,
                                    " Value: ", eval_result)
                input_log_file.write(str(type(self.state[var_name])) + ' ' + str(var_name) + ': ' + str(self.state[var_name]) + '\n')
        script_logger.get_action_log().set_pre_file(
            'text',
            self.log_folder + 'inputs.txt',
            log_header=False,
            absolute_path = True
        )

    def parse_outputs(self, outputState, outputs_log_file_path):
        with open(outputs_log_file_path, 'w') as outputs_log_file:
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: parsing outputs ', self.outputs)
            for [var_name, input_expression, default_value] in self.outputs:
                var_name = var_name.strip()
                if len(input_expression.strip()) == 0:
                    input_expression = 'None'
                if ((default_value or default_value == "true") and (
                                var_name in self.state and self.state[var_name] is not None)):
                    script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsing Output: ', var_name,
                                      " Default Parameter? ", default_value,
                                      " Overwriting Default? True" if default_value else "reading from child state")
                    try:
                        outputState[var_name] = self.state[var_name]
                    except KeyError as k:
                        script_logger.log('ERROR: key error while parsing output, keys present in input state: ' + ', '.join(list(self.state)))
                        if self.status == ScriptExecutionState.FINISHED_FAILURE:
                            script_logger.log(self.props['script_name'], 'script finished with failure, ignoring key error')
                            continue
                        raise
                    script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsed Output: ', var_name,
                                      " Value: ", outputState[var_name] if var_name in outputState else 'None'
                    )
                    outputs_log_file.write(str(type(outputState[var_name])) + ' ' + str(var_name) + ': ' + str(outputState[var_name]) + '\n')
                    continue
                globs = {
                    'glob': glob,
                    'datetime': datetime,
                    're': re
                }
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsing Output: ', var_name,
                                  " Default Parameter? ", default_value,
                                  " Overwriting Default? False" if default_value else "")
                state_copy = self.state.copy()
                eval_result = state_eval(input_expression, globs, state_copy, crashonerror=self.status !=ScriptExecutionState.FINISHED_FAILURE)
                outputState[var_name] = eval_result
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsed Output: ', var_name,
                                  " Value: ", eval_result)
                outputs_log_file.write(
                    str(type(outputState[var_name])) + ' ' + str(var_name) + ': ' + str(outputState[var_name]) + '\n'
                )
        script_logger.get_action_log().set_post_file(
            'text',
            outputs_log_file_path,
            log_header=False,
            absolute_path=True
        )
    def log_action_details(self, action):
        now = datetime.datetime.now()
        elapsed = now - self.context['script_timer']
        self.context['script_timer'] = now

        script_logger.log(
            'LOG,' +\
            str(self.context['script_counter']).zfill(5) + ',' + \
            self.props["script_name"] + ' ' + action["actionData"]["targetSystem"] + \
            ', action : ,' + action["actionName"] + '-' + str(action["actionGroup"]) + \
            ', children: ,' + str(list(map(lambda action: action["actionGroup"], self.get_children(action)))) + \
            ', attempts: ,' + str(self.context["action_attempts"]) + \
            ', outOfAttempts: ,' + str(self.context["out_of_attempts"]) +\
            ', elapsed: ,' + str(elapsed)
        )

    def handle_action(self, action, lazy_eval=False) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List] | Tuple[Callable, Tuple]:
        if lazy_eval:
            script_logger.log('returning parallel handle action handler')
        else:
            script_logger.log('sequential handle action')
        if "targetSystem" in action["actionData"]:
            if action["actionData"]["targetSystem"] == "adb":
                handle_action_result = self.device_manager.adb_host.handle_action(action, self.state, self.context, self.run_queue, lazy_eval=lazy_eval)
            elif action["actionData"]["targetSystem"] == "python":
                handle_action_result = self.device_manager.python_host.handle_action(action, self.state, self.context, self.run_queue, lazy_eval=lazy_eval)
            elif action["actionData"]["targetSystem"] == "none":
                if action["actionName"] == "scriptReference":
                    handle_action_result = self.handle_script_reference(action, self.state, self.context, self.run_queue)
                else:
                    handle_action_result = self.device_manager.system_host.handle_action(action, self.state, self.context, self.run_queue)
            else:
                exception_text = "target system " + action["actionData"]["targetSystem"] + " unimplemented!"
                script_logger.log(exception_text)
                raise Exception(exception_text)
        else:
            exception_text = "script formatting error, targetSystem not present!"
            raise Exception(exception_text)

        if not lazy_eval:
            _, status, _, context, _, _ = handle_action_result

            if "status_detail" in context:
                status_detail = context["status_detail"]
                del context["status_detail"]
            else:
                status_detail = None
            if status_detail is not None:
                script_logger.get_action_log().set_status(status_detail)
            else:
                script_logger.get_action_log().set_status(status.name)

        return handle_action_result

    def handle_handle_action_result(self, handle_action_result, status, state, context, run_queue) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List]:
        action = handle_action_result[0]
        script_logger.configure_action_logger_from_strs(*action["script_logger"])
        script_logger.log(
            'Handling handle action result for action ' + action["actionName"] + '-' + str(action["actionGroup"])
        )
        update_queue = []
        if action["actionName"] == "detectObject":
            action, status, state, context, run_queue, update_queue = DetectObjectHelper.handle_detect_action_result(
                self.device_manager.io_executor, handle_action_result, state, context, run_queue
            )
        else:
            pass

        if "status_detail" in context:
            status_detail = context["status_detail"]
            del context["status_detail"]
        else:
            status_detail = None
        if status_detail is not None:
            script_logger.get_action_log().set_status(status_detail)
        else:
            script_logger.get_action_log().set_status(status.name)

        return action, status, state, context, run_queue, update_queue

    def handle_script_reference(self, action, state, context, run_queue) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List]:
        if action["actionName"] == 'scriptReference':

            if 'paused_script' in self.context:

                del self.context['paused_script']
                pass

            is_new_script = "initializedScript" not in action["actionData"] or action["actionData"][
                "initializedScript"] is None
            if is_new_script:
                # script_logger.log('context: ', context)
                child_context = {
                    "script_attributes": context["script_attributes"].copy(),
                    "run_type": action["actionData"]["runMode"],
                    "branching_behavior": action["actionData"]["branchingBehavior"]
                }
                # script_logger.log("source: ", action["actionData"]["scriptAttributes"], " target: ", child_context["script_attributes"])
                child_context["script_attributes"].update(action["actionData"]["scriptAttributes"])
                # script_logger.log("child_context: ", child_context, "self context: ", context, " actionData: ", action["actionData"]["scriptAttributes"])
            else:
                child_context = action["actionData"]["initializedScript"].context
            # script_logger.log("child_context: ", child_context, "self context: ", context)

            is_error_handler = 'searchAreaErrorHandler' in child_context["script_attributes"] and \
                               context["parent_action"] is not None and \
                               context["parent_action"]["actionName"] == "searchPatternContinueAction"
            is_object_handler = 'searchAreaObjectHandler' in child_context["script_attributes"] and \
                                context["parent_action"] is not None and \
                                context["parent_action"]["actionName"] == "searchPatternContinueAction"

            child_state = {}

            # creates script engine object
            if is_new_script:
                script_name = action["actionData"]["scriptName"].strip()
                if script_name[0] == '{' and script_name[-1] == '}':
                    script_name = state_eval(script_name[1:-1], {}, self.state)
                if script_name[0] == '[' and script_name[-1] == ']':
                    script_name = script_name[1:-1]
                    system_script = True
                    script_details = script_name.split(':')
                    handle_status = SystemScriptHandler.handle_system_script(self.device_manager, script_details[0], script_details[1])
                    if handle_status == 'return':
                        return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
                    ref_script = parse_zip(script_details[0], system_script)
                elif script_name in self.include_scripts:
                    ref_script = self.include_scripts[script_name]
                else:
                    ref_script = parse_zip(script_name, False)
                # script_logger.log(' state (3) : ', state)

                ref_script['include'] = self.include_scripts
                child_context["actionOrder"] = action["actionData"]["actionOrder"] if "actionOrder" in action["actionData"] else "sequential"
                child_context["scriptMaxActionAttempts"] = action["actionData"]["scriptMaxActionAttempts"] if "scriptMaxActionAttempts" in action["actionData"] else ""
                child_context["onOutOfActionAttempts"] = action["actionData"]["onOutOfActionAttempts"] if "onOutOfActionAttempts" in action["actionData"] else "returnFailure"
                child_context["script_counter"] = self.context["script_counter"]
                child_context["script_timer"] = self.context["script_timer"]

                if is_error_handler or is_object_handler:
                    search_area_handler_state = {
                        "target_search_pattern": context["search_patterns"][
                            context["parent_action"]["actionData"]["searchPatternID"]
                        ]
                    }
                    if child_state is not None:
                        child_state.update(search_area_handler_state)
                    else:
                        child_state = search_area_handler_state
                    ref_script_executor = ScriptExecutor(
                        ref_script,
                        self.props["timeout"],
                        self.base_script_name,
                        self.base_start_time_str,
                        self.script_id,
                        self.device_manager,
                        self.process_executor,
                        parent_folder=self.log_folder,
                        context=child_context,
                        state=child_state,
                        create_log_folders=False
                    )
                else:
                    ref_script_executor = ScriptExecutor(
                        ref_script,
                        self.props["timeout"],
                        self.base_script_name,
                        self.base_start_time_str,
                        self.script_id,
                        self.device_manager,
                        self.process_executor,
                        parent_folder=self.log_folder,
                        context=child_context,
                        state=child_state,
                        create_log_folders=False
                    )
            else:
                action["actionData"]["initializedScript"].rewind(child_state)
                ref_script_executor = action["actionData"]["initializedScript"]

                ref_script_executor.context["script_counter"] = self.context["script_counter"]
                ref_script_executor.context["script_timer"] = self.context["script_timer"]
            self.script_action_log = script_logger.get_action_log()
            ref_script_executor.set_parent_action_log(self.script_action_log)
            child_log_folder = ref_script_executor.create_log_folders(
                parent_folder=self.log_folder,
                refresh_start_time=True
            )
            self.script_action_log.set_script_log_folder(child_log_folder)
            ref_script_executor.parse_inputs(state)

            # I don't know what this does anymore
            if 'searchAreaObjectHandler' in child_context["script_attributes"]:
                ref_script_executor.context["object_handler_encountered"] = False
            if is_error_handler:
                if context["search_patterns"][
                    context["parent_action"]["actionData"]["searchPatternID"]
                ]["stitcher_status"] != "STITCHER_OK":
                    script_logger.log('launching error handler')
                    pass
                else:
                    script_logger.log('returning without error')
                    status = ScriptExecutionState.RETURN
                    return action, status, state, context, run_queue, []

            ref_script_executor.set_log_paths()

            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: parsing child script', action['actionData']['scriptName'])

            if action["actionData"]["runMode"] == "run":
                ref_script_executor.run()
            elif action["actionData"]["runMode"] == "runOne":
                ref_script_executor.run_one()
            elif action["actionData"]["runMode"] == "runToFailure":
                ref_script_executor.run_to_failure()

            if 'paused_script' in ref_script_executor.context:
                self.context['paused_script'] = ''#paused script file name
                #probably set status to something special

            self.set_log_paths()
            script_logger.set_log_header(
                str(self.context['script_counter']).zfill(5) + '-' + \
                action["actionName"] + '-' + str(action["actionGroup"])
            )
            script_logger.set_log_path_prefix(script_logger.get_log_folder() + script_logger.get_log_header() + '-')
            script_logger.set_action_log(self.script_action_log)

            ref_script_executor.parse_outputs(state, child_log_folder + 'outputs.txt')

            # context is a reference to self.context so setting context is the same as setting self.context
            self.context["script_counter"] = ref_script_executor.context["script_counter"]
            context["script_counter"] = ref_script_executor.context["script_counter"]
            self.context["script_timer"] = ref_script_executor.context["script_timer"]
            context["script_timer"] = ref_script_executor.context["script_timer"]

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
            context["status_detail"] = self.status_detail
            script_logger.log(action["actionData"][
                      "scriptName"] + " returning with status " + ref_script_executor.status.name + "/" + status.name)
            return action, status, state, context, run_queue, []

    def get_out_of_attempts_handler(self, action):
        if action is None:
            return None,None
        # script_logger.log(action["childGroups"])
        # script_logger.log(list(filter(lambda childGroupLink: childGroupLink["type"] == "outOfAttemptsHandler", action["childGroups"])))
        out_of_attempts_link = list(filter(lambda childGroupLink: childGroupLink["type"] == "outOfAttemptsHandler", action["childGroups"]))
        # script_logger.log('link : ', out_of_attempts_link)
        if len(out_of_attempts_link) > 0:
            out_of_attempts_link = out_of_attempts_link[0]
            return self.action_rows[out_of_attempts_link["destRowIndex"]]["actions"][out_of_attempts_link["destActionIndex"]],out_of_attempts_link
        else:
            return None,None


    def get_children(self, action):
        # script_logger.log('get_children ', action)
        child_actions = []

        for childGroupLink in action["childGroups"]:
            if not childGroupLink["type"] == "outOfAttemptsHandler":
                child_actions.append(self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]])

        return child_actions

    def handle_out_of_attempts_check(self):
        out_of_attempts_handler,out_of_attempts_link = self.get_out_of_attempts_handler(self.context['parent_action'])
        # script_logger.log('handler : ', out_of_attempts_handler)
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
        end_branch = False
        script_logger.log('-----' + self.props['script_name'] + ' CONTROL FLOW: Checking if done.', len(self.actions), " remaining action in branch. ", len(self.run_queue), " remaining branches" + '-----')
        if datetime.datetime.now().astimezone(tz=tz.tzutc()) > self.timeout:
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: script timeout - ', datetime.datetime.now())
            self.status_detail = ScriptExecutionStatusDetail.TIMED_OUT
            return end_branch,True
        running_scripts = get_running_scripts()

        if len(running_scripts) == 0:
            script_logger.log('CONTROL FLOW: running scripts file empty')
            terminate_request = True
        else:
            current_running_script = running_scripts[0]
            script_id_mismatch = current_running_script["script_id"] != self.script_id
            start_time_mismatch = current_running_script['start_time_str'] != self.base_start_time_str
            script_name_mismatch = current_running_script['script_name'] != self.base_script_name
            terminate_request = (
                script_id_mismatch or
                start_time_mismatch or
                script_name_mismatch
            )
            if terminate_request:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: script_id_mismatch?', script_id_mismatch,
                      'start_time_mismatch?', start_time_mismatch,
                      'script_name_mismatch?', script_name_mismatch)
            if terminate_request and current_running_script['parallel']:
                for running_script in running_scripts:
                    if running_script['parallel']:
                        terminate_request = (terminate_request and (
                            running_script['script_id'] != self.script_id) or
                            running_script['start_time_str'] != self.base_start_time_str or
                            running_script['script_name'] != self.base_script_name
                        )
                        if not terminate_request:
                            break
                    else:
                        break

        if terminate_request:
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: received terminate request')
            self.status_detail = ScriptExecutionStatusDetail.CANCELLED
            return end_branch,True

        if "scriptMaxActionAttempts" in self.context and\
                len(str(self.context["scriptMaxActionAttempts"])) > 0 and\
                len(self.context["action_attempts"]) > 0 and\
                max(self.context["action_attempts"]) > int(self.context["scriptMaxActionAttempts"]):
            self.status = ScriptExecutionState.FAILURE
            script_logger.log(self.props['script_name'] + " CONTROL FLOW: Action attempts", self.context["action_attempts"], "exceeded scriptMaxActionAttempts of", self.context["scriptMaxActionAttempts"])
            self.status_detail = ScriptExecutionStatusDetail.MAX_ATTEMPTS
            return end_branch,True
        if len(self.actions) == 0 and len(self.run_queue) == 0:
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Reached end of script with status', self.status)
            if self.status == ScriptExecutionState.FINISHED_FAILURE or self.status == ScriptExecutionState.FINISHED_FAILURE_BRANCH:
                pass
            else:
                self.status = ScriptExecutionState.FINISHED
            return end_branch,True
        if len(self.actions) == 0 and len(self.run_queue) > 0:
            if self.status == ScriptExecutionState.FINISHED_FAILURE or self.status == ScriptExecutionState.FINISHED_FAILURE_BRANCH:
                pass
            else:
                self.status = ScriptExecutionState.FINISHED_BRANCH
            self.start_new_branch()
            return True,False
        return end_branch,False


    def should_continue_on_failure(self):
        if self.context["run_type"] == "runOne" and self.context["run_depth"] == 1:
            return False
        elif self.context["run_type"] == "runToFailure":
            return False
        else:
            return True

    def parse_update_queue(self, update_queue):
        for [update_type, update_target, update_key, update_payload] in update_queue:
            if update_target == 'context':
                if update_type == 'update':
                    self.context[update_key] = update_payload
                elif update_type == 'append':
                    self.context[update_key].append(update_payload)
            elif update_target == 'state':
                if update_type == 'update':
                    self.state[update_key] = update_payload
                elif update_type == 'append':
                    self.state[update_key].append(update_payload)
            elif update_target == 'run_queue':
                if update_type == 'update':
                    if update_key is not None:
                        self.run_queue[update_key] = update_payload
                    else:
                        self.run_queue = update_payload
                elif update_type == 'append':
                    self.run_queue.append(update_payload)
            elif update_target == 'status':
                if update_type == 'update':
                    self.status = update_payload


    #if it is handle all branches then you take the first branch and for the rest you create a context switch action
    # Unless you know for certain that the field is going to be overwritten, you shouldn't rely on writing to the action
    # Keep in mind that the action is not copied, so any writes you do will be there when you call the same script again
    # And maybe you call the same script in the same script
    def execute_actions(self):
        script_logger.log('CONTROL FLOW: ', self.props['script_name'], 'starting next batch of actions')
        self.handle_out_of_attempts_check()
        n_actions = len(self.actions)
        is_return = False
        action_indices = list(range(0, len(self.actions)))
        if self.context["actionOrder"] == "random":
            script_logger.log("shuffling")
            random.shuffle(action_indices)

        script_logger.log('All actions: ', list(map(lambda action: action["actionGroup"], self.actions)))
        parallel_groups = {}
        parallel_group = []

        # TODO need to put your thinking cap on for attemptAllBranches
        # when you go to the next branch it will clear the process
        if self.context["branching_behavior"] == "firstMatch":
            for action_index in range(0, n_actions):
                action = self.actions[action_indices[action_index]]
                parallellizeable = is_parallelizeable(action)
                if parallellizeable:
                    parallel_group.append(action)
                else:
                    if len(parallel_group) > 1:
                        for parallel_action in parallel_group:
                            script_logger.log('adding parallel group to ' + str(parallel_action['actionGroup']))
                            parallel_groups[parallel_action["actionGroup"]] = parallel_group
                    parallel_group = []
            if len(parallel_group) > 1:
                for parallel_action in parallel_group:
                    script_logger.log('adding parallel group to ' + str(parallel_action['actionGroup']))
                    parallel_groups[parallel_action["actionGroup"]] = parallel_group
        elif self.context["branching_behavior"] == "attemptAllBranches" and n_actions > 1:
            state_copy = self.state.copy()
            context_copy = self.context.copy()
            for action_index in action_indices[1:]:
                action = self.actions[action_index]
                self.run_queue.append(
                    generate_context_switch_action([{
                        'srcGroup': None,
                        'srcRowIndex': None,
                        'srcActionIndex': None,
                        'destGroup': action['actionGroup'],
                        'destRowIndex': action['actionRowRowIndex'],
                        'destActionIndex': action['actionRowActionIndex'],
                        'coords': None,
                        'long': None,
                        'isPipeLink': None,
                        'type': 'firstMatch',
                        'typePayload': None
                    }], state_copy, context_copy, {})
                )
            self.actions = [self.actions[action_indices[0]]]
            action_indices = [0]
            n_actions = 1

        self.parallelized_executor.clear_processes()
        for action_index in range(0, n_actions):
            self.context["action_index"] = action_index
            action = self.actions[action_indices[action_index]]
            child_actions = self.get_children(action)
            self.context['child_actions'] = child_actions

            if "searchAreaObjectHandler" in self.context["script_attributes"] and \
                    action["actionName"] == 'detectObject' and \
                    "searchAreaObjectHandler" in action["actionData"]["detectorAttributes"]:
                self.context["object_handler_encountered"] = True

            if action["actionGroup"] in parallel_groups:
                script_logger.log('parallel group found in ' + str(action['actionGroup']))
                parallel_group = parallel_groups[action['actionGroup']]
                for parallel_action in parallel_group:
                    del parallel_groups[parallel_action["actionGroup"]]
                self.parallelized_executor.start_processes(self, parallel_group)

            self.log_action_details(action)
            parallel_process = self.parallelized_executor.get_process(action["actionGroup"])
            if parallel_process is not None:
                handle_action_result = parallel_process.result()
                _, self.status, self.state, self.context, self.run_queue, update_queue = self.handle_handle_action_result(
                    handle_action_result, self.status, self.state, self.context, self.run_queue
                )
            else:
                self.context["script_counter"] += 1
                script_logger.configure_action_logger(action, self.context["script_counter"], self.parent_action_log)
                _, self.status, self.state, self.context, self.run_queue, update_queue = self.handle_action(action)
                # post_handle_action((self.action, self.status, self.state, self.context, self.run_queue, update_queue))
            # script_logger.log('debug state', self.state)
            if 'postActionDelay' in action['actionData'] and len(action['actionData']['postActionDelay']) > 0:
                RandomVariableHelper.parse_post_action_delay(action['actionData']['postActionDelay'], self.state)

            script_logger.set_log_header(self.props['script_name'] + '-CONTROL FLOW')
            self.parse_update_queue(update_queue)
            script_logger.log('CONTROL FLOW: ',
                  self.props['script_name'],
                  'completed action',
                  action['actionName'],
                  action["actionGroup"],
                  'and returned status ',
                  self.status
            )

            self.context["action_attempts"][action_index] += 1
            if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_FAILURE:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                self.actions = []
                return
            elif self.status == ScriptExecutionState.SUCCESS:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                # script_logger.log('acton: ', action, ' childGroups: ', action['childGroups'])
                self.actions = child_actions
                self.context["action_attempts"] = [0] * len(child_actions)
                # script_logger.log('next: ', self.actions)
                self.status = ScriptExecutionState.STARTING
                return
            elif self.status == ScriptExecutionState.FAILURE:
                self.context['child_actions'] = None
                if self.context["run_mode"] == "run_to_failure":
                    return
                else:
                    continue
            elif self.status == ScriptExecutionState.RETURN:
                self.context["child_actions"] = None
                is_return = True
                continue
            elif self.status == ScriptExecutionState.FINISHED_BRANCH or self.status == ScriptExecutionState.FINISHED_FAILURE_BRANCH:
                self.context['parent_action'] = action
                self.context["child_actions"] = None
                self.actions = []
                return
            else:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: encountered error in script and returning ', self.status)
                self.context['child_actions'] = None
                self.status = ScriptExecutionState.ERROR
                return
        if is_return:
            self.actions = [self.context["parent_action"]]
            self.context["action_attempts"] = [0]
            # TODO clearly need to keep track of parent of parent etc
            self.context["parent_action"] = None
            self.status = ScriptExecutionState.RETURN


    def run_to_failure(self):
        self.context["run_mode"] = "run_to_failure"
        script_logger.log(
            "{} CONTROL FLOW: Running script with runMode: runToFailure branchingBehavior: {} scriptMaxActionAttempts {}".format(
                self.props['script_name'],
                self.context["branching_behavior"],
                self.context["scriptMaxActionAttempts"]
            )
        )
        self.status = ScriptExecutionState.STARTING
        overall_status = ScriptExecutionState.FAILURE
        while self.status != ScriptExecutionState.FINISHED and\
                self.status != ScriptExecutionState.ERROR and\
                self.status != ScriptExecutionState.FAILURE and\
                self.status != ScriptExecutionState.FINISHED_FAILURE:
            self.execute_actions()
            end_branch,end_script = self.check_if_done()
            if end_script:
                if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                    overall_status = ScriptExecutionState.SUCCESS
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
            elif self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                overall_status = ScriptExecutionState.SUCCESS
                # if it was the end of the script the status would be FINISHED
                self.status = ScriptExecutionState.STARTING
            # if end_branch:
            #     self.status = ScriptExecutionState.FINISHED_BRANCH
        # if at least one branch reached the end the script is a success
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        elif overall_status == ScriptExecutionState.FAILURE:
            self.status = ScriptExecutionState.FINISHED_FAILURE
        self.on_script_completion()





    def run_one(self):
        self.context["run_mode"] = "run_one"
        script_logger.log(
            "{} CONTROL FLOW: Running script with runMode: runOne branchingBehavior: {} scriptMaxActionAttempts {}".format(
                self.props['script_name'],
                self.context["branching_behavior"],
                self.context["scriptMaxActionAttempts"]
            )
        )
        self.status = ScriptExecutionState.STARTING
        branches = []
        if self.context["actionOrder"] == "random":
            random.shuffle(self.actions)
        is_attempt_all_branches = self.context["branching_behavior"] == "attemptAllBranches"
        if is_attempt_all_branches:
            # this exists because otherwise the runOne would always run because the context switch is always successful
            state_copy = self.state.copy()
            context_copy = self.context.copy()
            for action in self.actions:
                branches.append(
                    [generate_context_switch_action([{
                        'srcGroup': None,
                        'srcRowIndex': None,
                        'srcActionIndex': None,
                        'destGroup': action['actionGroup'],
                        'destRowIndex': action['actionRowRowIndex'],
                        'destActionIndex': action['actionRowActionIndex'],
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
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, performing first pass')
            self.execute_actions()
            if self.status == ScriptExecutionState.STARTING and len(self.actions) > 0:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, first pass successful, switching to run mode run')
                self.run()
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: returned from run in runOne with status', self.status)

                if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                    # remember the final state is FINISHED/FINISHED_FAILURE
                    overall_status = ScriptExecutionState.SUCCESS
                if not is_attempt_all_branches:
                    break
            elif self.status == ScriptExecutionState.STARTING:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, first pass successful, reached end of script')
                overall_status = ScriptExecutionState.SUCCESS
                self.status = ScriptExecutionState.FINISHED
                if not is_attempt_all_branches:
                    break
            else:
                self.actions = []
                if len(self.run_queue) > 1:
                    script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, branch of first pass unsuccessful, trying next branch')
                    end_branch, end_script = self.check_if_done()
                    if end_script:
                        if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                            overall_status = ScriptExecutionState.SUCCESS
                        break
                    # because the first action will be a context switch action
                    self.execute_actions()
                    self.run_one()
                    if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                        # remember the final state is FINISHED/FINISHED_FAILURE
                        overall_status = ScriptExecutionState.SUCCESS
                    if not is_attempt_all_branches:
                        break
                else:
                    script_logger.log(self.props['script_name'] + ' CONTROL FLOW: Running script with runOne, branch of first pass unsuccessful')

        # if you reached the end on one of the branches
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        elif overall_status == ScriptExecutionState.FAILURE:
            self.status = ScriptExecutionState.FINISHED_FAILURE
        script_logger.log(self.props['script_name'] + ' CONTROL FLOW: runOne overall status was ', overall_status)
        self.on_script_completion()
        #TODO In theory you should load in the state and context of the successful branch

    def run(self):
        self.context["run_mode"] = "run"
        script_logger.log("{} CONTROL FLOW: Running script with runMode: run branchingBehavior: {} scriptMaxActionAttempts {}".format(
                self.props['script_name'],
                self.context["branching_behavior"],
                self.context["scriptMaxActionAttempts"]
            )
        )
        self.status = ScriptExecutionState.STARTING
        overall_status = ScriptExecutionState.FAILURE
        while self.status != ScriptExecutionState.FINISHED and\
                self.status != ScriptExecutionState.FINISHED_FAILURE and\
                self.status != ScriptExecutionState.ERROR:
            self.execute_actions()
            end_branch,end_script = self.check_if_done()

            if end_script:
                if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_BRANCH:
                    overall_status = ScriptExecutionState.SUCCESS
                break

            if self.status == ScriptExecutionState.FINISHED_BRANCH:
                overall_status = ScriptExecutionState.SUCCESS
                # if it was the end of the script the status would be FINISHED
                self.status = ScriptExecutionState.STARTING
            elif self.status == ScriptExecutionState.FINISHED:
                overall_status = ScriptExecutionState.SUCCESS
            # if end_branch:
            #     self.status = ScriptExecutionState.FINISHED_BRANCH
        if overall_status == ScriptExecutionState.SUCCESS:
            self.status = ScriptExecutionState.FINISHED
        elif overall_status == ScriptExecutionState.FAILURE:
            self.status = ScriptExecutionState.FINISHED_FAILURE
        self.on_script_completion()

    def on_script_completion(self):
        if self.context["success_states"] is not None:
            self.state = self.context["success_states"][-1]

    def start_new_branch(self):
        script_logger.log(self.props['script_name'] + " CONTROL FLOW: finished branch with status ", self.status, " and starting new branch")
        if self.status == ScriptExecutionState.FINISHED_BRANCH:
            script_logger.log(self.props['script_name'] + " CONTROL FLOW: adding script state to success states")
            if self.context["success_states"] is None:
                self.context["success_states"] = [self.state.copy()]
            else:
                self.context["success_states"] += [self.state.copy()]
        self.actions.append(self.run_queue.pop())
        self.context["action_attempts"] = len(self.actions) * [0]







if __name__ == '__main__':
    # TODO DONT LEAVE PASSCODE IN ANY SOURCE CONTORL
    '''
        
        ./adb shell wm size
        ./adb devices | grep "\<device\>"
        
    '''
