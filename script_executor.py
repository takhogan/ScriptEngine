import sys

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from python_host_controller import python_host
from adb_host_controller import adb_host
import time
import os


class ScriptExecutor:
    def __init__(self, script_obj, log_level='INFO'):
        self.log_level = log_level
        self.props = script_obj['props']
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.python_host = python_host(self.props)
        self.adb_host = adb_host(self.props, self.python_host, '127.0.0.1:5555')
        # TODO IP shouldn't be hard coded
        self.include_scripts = script_obj['include']
        print(self.props['script_name'])
        self.log_folder = './logs/' + self.props['script_name'] + '-' + self.props['start_time']
        os.mkdir(self.log_folder)
        os.mkdir(self.log_folder + '/search_patterns')
        self.log_folder += '/'

        self.state = {
            'script_counter': 0,
            'search_patterns' : {}
        }

        self.status = ScriptExecutionState.FINISHED


    def handle_action(self, action):
        print(self.props["script_name"] + ' ' + action["actionData"]["targetSystem"] + ' action : ', action["actionName"], ' children: ', list(map(lambda childGroupLink: self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]["actionName"], action['childGroups'])))
        self.state["script_counter"] += 1
        if "targetSystem" in action["actionData"]:
            if action["actionData"]["targetSystem"] == "adb":
                self.adb_host.init_system()
                self.status, self.state = self.adb_host.handle_action(action, self.state, self.props, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "python":
                self.status, self.state = self.python_host.handle_action(action, self.state, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "none":
                if action["actionName"] == 'scriptReference':
                    ref_script = self.include_scripts[action["actionData"]["scriptName"]]
                    ref_script["props"]["start_time"] = self.props["start_time"]
                    ref_script["include"] = self.include_scripts
                    ref_script_executor = ScriptExecutor(ref_script, self.log_level)
                    ref_script_executor.run()
                    # print('finished')
                    if ref_script_executor.status == ScriptExecutionState.FINISHED:
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        self.status = ScriptExecutionState.ERROR
                elif action["actionName"] == "conditionalStatement":
                    if eval(action["actionData"]["condition"], self.state):
                        print('condition success!')
                        self.status = ScriptExecutionState.SUCCESS
                    else:
                        print('condition failure!')
                        self.status = ScriptExecutionState.FAILURE
                elif action["actionName"] == "variableAssignment":
                    expression = eval(action["actionData"]["expression"], self.state)
                    self.state[action["actionData"]["variableName"]] = expression
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


    def execute_actions(self):
        def get_child_action(childGroupLink):
            return self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]

        for action in self.actions:
            # print('action: ', action)
            self.handle_action(action)
            if self.status == ScriptExecutionState.FINISHED:
                self.actions = []
                return
            elif self.status == ScriptExecutionState.SUCCESS:
                # print('acton: ', action, ' childGroups: ', action['childGroups'])
                self.actions = list(map(get_child_action, action["childGroups"]))
                # print('next: ', self.actions)
                self.status = ScriptExecutionState.STARTING
                return
            elif self.status == ScriptExecutionState.FAILURE:
                continue
            else:
                self.status = ScriptExecutionState.ERROR
                return


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
