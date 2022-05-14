import copy
import sys

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from python_host_controller import python_host
from adb_host_controller import adb_host
import time
import os
import datetime


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
        if state is not None:
            self.state.update(state)

        self.context = {
            'parent_actions': None,
            'parent_action': None,
            'child_actions': None,
            'script_attributes': set(),
            'script_counter': 0,
            'search_patterns': {},
            'replay_stack' : []
        }
        if context is not None:
            self.context.update(context)

        self.status = ScriptExecutionState.FINISHED


    def handle_action(self, action):
        print(self.props["script_name"] + ' ' + action["actionData"]["targetSystem"] + ' action : ', action["actionName"], ' children: ', list(map(lambda childGroupLink: self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]["actionName"], action['childGroups'])))
        self.context["script_counter"] += 1
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
                        print('self.context: ', self.context)
                        child_context = {
                            'script_attributes': self.context["script_attributes"].copy()
                        }
                        print("source: ", action["actionData"]["scriptAttributes"], " target: ", child_context["script_attributes"])
                        child_context["script_attributes"].update(action["actionData"]["scriptAttributes"])
                        print("child_context: ", child_context, "self context: ", self.context, " actionData: ", action["actionData"]["scriptAttributes"])
                    else:
                        child_context = action["actionData"]["initializedScript"].context
                    print("child_context: ", child_context, "self context: ", self.context)

                    is_error_handler = 'searchAreaErrorHandler' in child_context["script_attributes"] and \
                                       self.context["parent_action"] is not None and \
                                       self.context["parent_action"]["actionName"] == "searchPatternContinueAction"
                    is_object_handler = 'searchAreaObjectHandler' in child_context["script_attributes"] and \
                                        self.context["parent_action"] is not None and \
                                        self.context["parent_action"]["actionName"] == "searchPatternContinueAction"
                    print('is_error_handler: ', is_error_handler)
                    print('is_object_handler: ', is_object_handler)
                    print('is_new_script: ', is_new_script)
                    if is_new_script:
                        ref_script = self.include_scripts[action["actionData"]["scriptName"]]
                        ref_script["props"]["start_time"] = self.props["start_time"]
                        ref_script["include"] = self.include_scripts
                        script_ref_start_time = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
                        script_ref_log_folder = self.log_folder + action["actionData"]["scriptName"] + '-' + script_ref_start_time
                        if is_error_handler or is_object_handler:
                            ref_script_executor = ScriptExecutor(
                                ref_script,
                                self.log_level,
                                script_ref_log_folder,
                                child_context,
                                {
                                    "target_search_pattern" : self.context["search_patterns"][
                                        self.context["parent_action"]["actionData"]["searchPatternID"]
                                    ]
                                }
                            )
                        else:
                            ref_script_executor = ScriptExecutor(
                                ref_script,
                                self.log_level,
                                script_ref_log_folder,
                                child_context
                            )
                    else:
                        ref_script_executor = action["actionData"]["initializedScript"]

                    if is_error_handler:
                        if self.context["search_patterns"][
                            self.context["parent_action"]["actionData"]["searchPatternID"]
                        ]["stitcher_status"] != "STITCHER_OK":
                            ref_script_executor.run_one()
                        else:
                            ref_script_executor.status = ScriptExecutionState.FINISHED
                    else:
                        ref_script_executor.run_one()

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
                        elif ref_script_executor.status == ScriptExecutionState.FAILURE:
                            self.status = ScriptExecutionState.FAILURE
                        else:
                            self.status = ScriptExecutionState.ERROR
                    action["actionData"]["initializedScript"] = ref_script_executor
                    print(action["actionData"]["scriptName"] + " returning with status " + ref_script_executor.status.name + "/" + self.status.name)
                elif action["actionName"] == "conditionalStatement":
                    if eval(action["actionData"]["condition"], self.state):
                        print('condition success!')
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        print('condition failure!')
                        self.status = ScriptExecutionState.FAILURE
                elif action["actionName"] == "variableAssignment":
                    expression = eval(action["actionData"]["inputExpression"], self.state)
                    self.state[action["actionData"]["outputVarName"]] = expression
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
        return action


    def execute_actions(self):
        def get_child_action(childGroupLink):
            return self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]

        n_actions = len(self.actions)
        is_return = False
        for action_index in range(0, n_actions):
            action = self.actions[action_index]
            child_actions = list(map(get_child_action, action["childGroups"]))
            self.context['child_actions'] = child_actions
            # print('action: ', action)
            self.actions[action_index] = self.handle_action(action)
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
                # print('next: ', self.actions)
                self.status = ScriptExecutionState.STARTING
                return
            elif self.status == ScriptExecutionState.FAILURE:
                self.context['child_actions'] = None
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
            # TODO clearly need to keep track of parent of parent etc
            self.context["parent_action"] = None
            self.status = ScriptExecutionState.RETURN


    def run_one(self, log_level=None):
        if log_level is not None:
            self.log_level = log_level
        self.status = ScriptExecutionState.STARTING
        self.execute_actions()
        if self.status == ScriptExecutionState.STARTING:
            print('continuing run_one')
            while self.status != ScriptExecutionState.FINISHED and self.status != ScriptExecutionState.ERROR:
                self.execute_actions()
                # print(self.status, ' status ')
                if len(self.actions) == 0:
                    if len(self.context["replay_stack"]) > 0:
                        replay_stack_item = self.context["replay_stack"].pop()
                        self.actions = [replay_stack_item]
                    else:
                        self.status = ScriptExecutionState.FINISHED
                    break

    # we need a props variable and corresponding json
    # json will be manually editable

    def run(self, log_level=None):
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
