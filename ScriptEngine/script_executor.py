# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import copy
import datetime
from dateutil import tz

import random
import re
import glob

from ScriptEngine.device_controller import DeviceController
from .engine_manager import EngineManager
from .helpers.detect_object_helper import DetectObjectHelper
from .parallelized_script_executor import ParallelizedScriptExecutor
from .script_action_executor import ScriptActionExecutor
from ScriptEngine.common.constants.script_engine_constants import *
from ScriptEngine.common.enums import ScriptExecutionState, ScriptExecutionStatusDetail
from ScriptEngine.common.script_engine_utils import generate_context_switch_action,get_running_scripts, is_parallelizeable, datetime_to_local_str, state_eval
from .script_loader import parse_zip
from .system_script_handler import SystemScriptHandler
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from .helpers.random_variable_helper import RandomVariableHelper
from .custom_thread_pool import CustomThreadPool
from .custom_process_pool import CustomProcessPool
from typing import Callable, Dict, List, Tuple
script_logger = ScriptLogger()




import os

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
                 include_scripts,
                 timeout,
                 base_script_name,
                 base_start_time_str,
                 script_id,
                 device_controller : DeviceController,
                 engine_manager : EngineManager,
                 io_executor : CustomThreadPool,
                 script_action_executor : ScriptActionExecutor,
                 process_executor : CustomProcessPool,
                 call_stack=None,
                 parent_folder='',
                 script_start_time : datetime.datetime=None,
                 context=None,
                 state=None,
                 create_log_folders=True,
                 screen_plan_server_attached=False):
        self.include_scripts = include_scripts
        self.script_id = script_id
        self.base_script_name = base_script_name
        self.base_start_time_str = base_start_time_str
        self.device_controller = device_controller
        self.engine_manager = engine_manager
        self.io_executor = io_executor
        self.process_executor = process_executor
        self.screen_plan_server_attached = screen_plan_server_attached
        self.script_action_executor = script_action_executor
        self.parallelized_executor = ParallelizedScriptExecutor(device_controller, process_executor)
        self.state = {
            'SCRIPT_CONTEXT': {
                'script_id': script_id,
                'timeout': timeout,
                'base_script_name': base_script_name, 
                'base_start_time_str': base_start_time_str
            }
        }
        if state is not None:
            self.state.update(state)
        self.context = {
            'action_path' : None,
            'parent_action': None,
            'child_actions': None,
            'script_attributes': set(),
            'script_counter': 0,
            'script_timer': datetime.datetime.now(),
            'run_depth': 0,
            'branching_behavior': 'firstMatch',
            'run_type': 'run',
            'search_patterns': {},
            'out_of_attempts': False,
            'out_of_attempts_action': None,
            'run_queue': None,
            'actionOrder': 'sequential',
            'success_states': None,
            'mouse_down': False,
            'run_actions_complete' : None,
            'skip_input_parsing' : None,
            'script_memory_mode' : 'normal'
        }
        if context is not None:
            self.context.update(context)
        
        # Parse script object
        self.parse_script_obj(script_obj)
        
        
        # Set call stack
        self.call_stack = [] if call_stack is None else call_stack.copy()
        self.call_stack.append(self.props["script_name"])
        
        # Initialize run queue
        self.run_queue = []
        
        # Set script start time
        if script_start_time is None:
            self.refresh_start_time()
        else:
            self.props['script_start_time'] = script_start_time
        
        # Set timeout
        self.timeout = timeout
        self.props["timeout"] = timeout
        
        # Initialize status
        self.status = ScriptExecutionState.FINISHED
        self.status_detail = None
        
        # Setup logging
        self.parent_action_log = None
        self.script_action_log = None
        if create_log_folders:
            self.create_log_folders(parent_folder)
            self.set_log_paths()
        
        # Set hot swap version
        self.hot_swap_version = self.engine_manager.get_script_version(self.props['script_name'])

    def parse_script_obj(self, script_obj):
        """Parse script object and initialize executor properties"""
        self.props = script_obj['props']
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.inputs = script_obj["inputs"]
        self.outputs = script_obj["outputs"]
        
        # Initialize context with action attempts array
        if 'action_attempts' not in self.context:
            self.context['action_attempts'] = [0] * len(self.actions)


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
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsing Input: ', var_name,
                                  " Default Parameter? ", default_value,
                                  " Overwriting Default? False" if default_value else "")
                state_copy = self.state.copy()
                state_copy.update(input_state)
                eval_result = state_eval(input_expression, {}, state_copy)
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
                script_logger.log(self.props['script_name'], ' CONTROL FLOW: Parsing Output: ', var_name,
                                  " Default Parameter? ", default_value,
                                  " Overwriting Default? False" if default_value else "")
                state_copy = self.state.copy()
                eval_result = state_eval(input_expression, {}, state_copy, crashonerror=self.status !=ScriptExecutionState.FINISHED_FAILURE)
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
        
        if action["actionData"]["targetSystem"] == "none" and action["actionName"] == "scriptReference":
            handle_action_result = self.handle_script_reference(action, self.state, self.context, self.run_queue)
        else:
            handle_action_result = self.script_action_executor.execute_action(action, self.state, self.context, self.run_queue, lazy_eval=lazy_eval)

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
        if action["actionName"] == "detectObject":
            action, status, state, context, run_queue = DetectObjectHelper.handle_detect_action_result(
                self.io_executor, handle_action_result, state, context, run_queue
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

        return action, status, state, context, run_queue, []

    def handle_script_reference(self, action, state, context, run_queue) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List]:
        if action["actionName"] == 'scriptReference':
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: initializing script reference object', action['actionData']['scriptName'])
             
            # script_logger.log('context: ', context)
            child_context = {
                "script_attributes": context["script_attributes"].copy(),
                "run_type": action["actionData"]["runMode"],
                "branching_behavior": action["actionData"]["branchingBehavior"]
            }
            # script_logger.log("source: ", action["actionData"]["scriptAttributes"], " target: ", child_context["script_attributes"])
            child_context["script_attributes"].update(action["actionData"]["scriptAttributes"])
            # script_logger.log("child_context: ", child_context, "self context: ", context, " actionData: ", action["actionData"]["scriptAttributes"])
            # creates script engine object
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: creating new script object', action['actionData']['scriptName'])
            script_name = action["actionData"]["scriptName"].strip()
            if script_name[0] == '{' and script_name[-1] == '}':
                script_name = state_eval(script_name[1:-1], {}, self.state)
            if script_name[0] == '[' and script_name[-1] == ']':
                script_name = script_name[1:-1]
                system_script = True
                script_details = script_name.split(':')
                handle_status = SystemScriptHandler.handle_system_script(self.device_controller, script_details[0], script_details[1])
                if handle_status == 'return':
                    return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
                ref_script = parse_zip(script_details[0], system_script)
            elif script_name in self.include_scripts:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: loading script from memory', script_name)
                ref_script = self.include_scripts[script_name]
            else:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: loading script from disk', script_name, ' include_scripts: ', ','.join(list(self.include_scripts.keys())))
                ref_script = parse_zip(script_name, False)
                if self.context['script_memory_mode'] != 'low':
                    self.include_scripts[script_name] = ref_script
            # script_logger.log(' state (3) : ', state)

            child_context["actionOrder"] = action["actionData"]["actionOrder"] if "actionOrder" in action["actionData"] else "sequential"
            child_context["scriptMaxActionAttempts"] = action["actionData"]["scriptMaxActionAttempts"] if "scriptMaxActionAttempts" in action["actionData"] else ""
            child_context["onOutOfActionAttempts"] = action["actionData"]["onOutOfActionAttempts"] if "onOutOfActionAttempts" in action["actionData"] else "returnFailure"
            child_context["script_counter"] = self.context["script_counter"]
            child_context["script_timer"] = self.context["script_timer"]
            ref_script_executor = ScriptExecutor(
                ref_script,
                self.include_scripts,
                self.props["timeout"],
                self.base_script_name,
                self.base_start_time_str,
                self.script_id,
                self.device_controller,
                self.engine_manager,
                self.io_executor,
                self.script_action_executor,
                self.process_executor,
                call_stack=self.call_stack + ['[{}-scriptReference-{}]'.format(self.context["script_counter"], action["actionGroup"])],
                parent_folder=self.log_folder,
                context=child_context,
                state={},
                create_log_folders=False,
                screen_plan_server_attached=self.screen_plan_server_attached
            )
            
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: configuring script action log', action['actionData']['scriptName'])

            self.script_action_log = script_logger.get_action_log()
            ref_script_executor.set_parent_action_log(self.script_action_log)
            child_log_folder = ref_script_executor.create_log_folders(
                parent_folder=self.log_folder,
                refresh_start_time=True
            )
            self.script_action_log.set_script_log_folder(child_log_folder)
            if self.context['skip_input_parsing'] is not None:
                self.context['skip_input_parsing'] = None
            else:
                ref_script_executor.parse_inputs(state)
            
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: parsing child script', action['actionData']['scriptName'])
            ref_script_executor.set_log_paths()


            if action["actionData"]["runMode"] == "run":
                ref_script_executor.run()
            elif action["actionData"]["runMode"] == "runOne":
                ref_script_executor.run_one()
            elif action["actionData"]["runMode"] == "runToFailure":
                ref_script_executor.run_to_failure()


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

            if ref_script_executor.status == ScriptExecutionState.FINISHED:
                status = ScriptExecutionState.SUCCESS
            elif ref_script_executor.status == ScriptExecutionState.FINISHED_FAILURE:
                status = ScriptExecutionState.FAILURE
            elif ref_script_executor.status == ScriptExecutionState.FAILURE:
                status = ScriptExecutionState.FAILURE
            else:
                status = ScriptExecutionState.ERROR
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
            script_logger.log(self.props['script_name'] + ' CONTROL FLOW: script has timed out - script timeout - ', datetime.datetime.now())
            self.status_detail = ScriptExecutionStatusDetail.TIMED_OUT
            return end_branch,True

        terminate_request = False
        if self.screen_plan_server_attached:
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
    
    def get_all_children(self, action):
        return list(map(lambda childGroupLink: self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]], action["childGroups"]))

    def find_action_paths(self, parent_action_group: int, current_action_group: int) -> List[int]:
        """Find a path through the action graph that goes through parent_action_group to current_action_group
        
        Args:
            parent_action_group: The first required action group in the path
            current_action_group: The second required action group in the path
            
        Returns:
            The path as a list of action group IDs, or None if no such path exists
        """
        start_actions = self.action_rows[0]["actions"]
        if parent_action_group is None:
            found_parent = True
        
        for start_action in start_actions:
            # Add visited set to track nodes we've already seen
            visited = {start_action["actionGroup"]}
            queue = [(start_action, [start_action["actionGroup"]], False)]
            
            while queue:
                current_action, current_path, found_parent = queue.pop(0)
                
                if current_action["actionGroup"] == parent_action_group:
                    found_parent = True
                
                if found_parent and current_action["actionGroup"] == current_action_group:
                    return current_path
                
                children = self.get_all_children(current_action)
                
                for child in children:
                    # Only add child to queue if we haven't visited it yet
                    if child["actionGroup"] not in visited:
                        visited.add(child["actionGroup"])
                        queue.append((
                            child,
                            current_path + [child["actionGroup"]],
                            found_parent
                        ))
        
        return None
    
    def find_action_by_group(self, action_group: int) -> Dict:
        for row in self.action_rows:
            for action in row["actions"]:
                if action["actionGroup"] == action_group:
                    return action
        return None

    def process_engine_interrupts(self, reload=False):
        # you should move clear scripts to an interrupt
        if self.engine_manager.debug_mode or reload:
            self.engine_manager.get_interrupts(synchronous=True)
        
        if self.engine_manager.debug_mode:
            full_action_name = '[{}-{}-{}]'.format(
                self.context["script_counter"],
                self.context["action"]["actionName"],
                self.context["action"]["actionGroup"]
            )
            call_stack_key = '/'.join(self.call_stack) + '/' + str('[{}]'.format(full_action_name))
            self.engine_manager.saved_states[call_stack_key] = copy.deepcopy(self.state)
            self.engine_manager.saved_contexts[call_stack_key] = copy.deepcopy(self.context)            
        
        return_status = "none"

        # if the script being swapped is in the call stack: 
        #       the current script should be assigned a new name
        #       throw an error
        # elif the script being swapped is the current script:
        #       if the current running action was removed:
        #           a new instance of the current script will start
        #       else:
        #           continue from the last action
        if "hot_swap" in self.engine_manager.interrupt_actions:
            hot_swap_action = self.engine_manager.interrupt_actions["hot_swap"]
            if not hot_swap_action["completed"]:
                swap_script_name = hot_swap_action["script_name"]

                if swap_script_name in self.call_stack:
                    raise Exception('ScriptName {} is in call stack, please rename the script before swapping'.format(swap_script_name))
                del self.include_scripts[swap_script_name]
                if self.props["script_name"] == swap_script_name:
                    hot_swap_script = parse_zip(swap_script_name, False)
                    self.parse_script_obj(hot_swap_script)
                    self.context['action_path'] = self.find_action_paths(
                        self.context['parent_action']['actionGroup'] if self.context['parent_action'] is not None else None,
                        self.context['action_group']
                    )
                    return_status = "pending"
                hot_swap_action["completed"] = True
        
        if "clear_saves" in self.engine_manager.interrupt_actions:
            if not self.engine_manager.interrupt_actions["clear_saves"]["completed"]:
                self.engine_manager.saved_states = {}
                self.engine_manager.saved_contexts = {}
                self.engine_manager.interrupt_actions["clear_saves"]["completed"] = True
        
        if "engine_context_switch" in self.engine_manager.interrupt_actions:
            engine_context_switch = self.engine_manager.interrupt_actions["engine_context_switch"]
            if not engine_context_switch["completed"]:
                target_call_stack = engine_context_switch["call_stack"]
                if not self.call_stack[-1] == target_call_stack[-1]:
                    return "return"
                target_call_stack_len = len(target_call_stack)
                call_stack_len = len(self.call_stack)
                
                if target_call_stack_len > call_stack_len:
                    target_action_name = target_call_stack[len(self.call_stack)]
                    if '[' not in target_action_name:
                        target_action_name = target_call_stack[len(self.call_stack) + 1]
                    target_action_name = target_action_name[1:-1]
                    target_action_type = target_action_name.split('-')[1]
                    target_action_group = target_action_name.split('-')[-1]
                    if target_action_type == 'scriptReference' and \
                        (target_call_stack_len - call_stack_len > 1):
                        self.context['skip_input_parsing'] = True
                    self.context['action_path'] = self.find_action_paths(
                        None,
                        target_action_group
                    )
                    if self.engine_manager.debug_mode:
                        call_stack_key = '/'.join(self.call_stack) + '/' + str('[{}]'.format(target_action_name))
                        previous_script_counter = self.context["script_counter"]
                        self.state.update(self.engine_manager.saved_states[call_stack_key])
                        self.context.update(self.engine_manager.saved_contexts[call_stack_key])
                        self.context["script_counter"] = previous_script_counter
                        self.context['skip_input_parsing'] = None
                    return_status = "pending"
                elif len(target_call_stack) == len(self.call_stack):
                    engine_context_switch['completed'] = True

        
        if "run_actions" in self.engine_manager.interrupt_actions:
            run_actions = self.engine_manager.interrupt_actions["run_actions"]
            if not run_actions['completed']:
                if run_actions['run_actions_type'] == 'iteration':
                    return_status = "pending"
                elif run_actions['run_actions_type'] == 'action':
                    if run_actions['run_actions_status'] == 'waiting':
                        run_actions['run_actions_status'] = 'running'
                        return_status = "pending"
                    else:
                        run_actions['run_actions_status'] = 'finished'
                        run_actions['completed'] = True
 
        
        
        if "pause" in self.engine_manager.interrupt_actions:
            self.engine_manager.pause()

            if "run_actions_complete" in self.context:
                del self.context['run_actions_complete']

            self.engine_manager.get_interrupts(synchronous=True)
            if "pause" in self.engine_manager.interrupt_actions:
                return_status = self.process_engine_interrupts()
        
        return return_status
        
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

    def execute_action(self, action, parallel_groups):
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
            action, self.status, self.state, self.context, self.run_queue, update_queue = self.handle_handle_action_result(
                handle_action_result, self.status, self.state, self.context, self.run_queue
            )
            # script_logger.log('CONTROL FLOW: ', 
            # self.props['script_name'], 
            # 'completed handling for action',
            # action['actionName'],
            # action['actionGroup'])
        else:
            self.context["script_counter"] += 1
            script_logger.log('Creating action log for action', action["actionGroup"])
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
            
            action = self.actions[action_indices[self.context["action_index"]]]
            self.context["action"] = action
            self.context["action_group"] = action["actionGroup"]
            child_actions = self.get_children(action)
            interrupt_command = "none"#self.process_engine_interrupts()
            if interrupt_command == "return":
                self.status = ScriptExecutionState.FINISHED
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                self.actions = []
                return
            self.context['child_actions'] = child_actions
            self.context["action_attempts"][self.context["action_index"]] += 1

            if self.context["action_path"] is not None:
                if self.context["action_path"][0] != self.context["action_group"]:
                    continue
                else:
                    self.context["action_path"].pop()
                    if len(self.context["action_path"]) == 0:
                        self.context["action_path"] = None
            
            if self.context["action_path"] is None:
                self.execute_action(action, parallel_groups)

            if self.status == ScriptExecutionState.FINISHED or self.status == ScriptExecutionState.FINISHED_FAILURE:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                self.actions = []
                break
            elif self.status == ScriptExecutionState.SUCCESS:
                self.context['parent_action'] = action
                self.context['child_actions'] = None
                # script_logger.log('acton: ', action, ' childGroups: ', action['childGroups'])
                self.actions = child_actions
                self.context["action_attempts"] = [0] * len(child_actions)
                # script_logger.log('next: ', self.actions)
                self.status = ScriptExecutionState.STARTING
                break
            elif self.status == ScriptExecutionState.FAILURE:
                self.context['child_actions'] = None
                if self.context["run_mode"] == "run_to_failure":
                    break
                else:
                    continue
            elif self.status == ScriptExecutionState.FINISHED_BRANCH or self.status == ScriptExecutionState.FINISHED_FAILURE_BRANCH:
                self.context['parent_action'] = action
                self.context["child_actions"] = None
                self.actions = []
                break
            else:
                script_logger.log(self.props['script_name'] + ' CONTROL FLOW: encountered error in script and returning ', self.status)
                self.context['child_actions'] = None
                self.status = ScriptExecutionState.ERROR
                break
        self.parallelized_executor.clear_processes()
        
        if "run_actions" in self.engine_manager.interrupt_actions:
            run_actions = self.engine_manager.interrupt_actions["run_actions"]
            run_actions['completed'] = True

        return_status = "none"
        if "pause" in self.engine_manager.interrupt_actions:
            self.engine_manager.pause()
            self.engine_manager.get_interrupts(synchronous=True)
            if "pause" in self.engine_manager.interrupt_actions:
                return_status = self.process_engine_interrupts()
        
        if return_status == "return":
            self.status = ScriptExecutionState.FINISHED
            self.context['parent_action'] = action
            self.context['child_actions'] = None
            self.actions = []
            return
        elif return_status != "pending":
            self.engine_manager.get_interrupts(synchronous=True)


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

