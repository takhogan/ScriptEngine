import subprocess
import sys

sys.path.append(".")
import time
from script_execution_state import ScriptExecutionState


class OSX:
    def __init__(self):
        pass

    def run_script(self, action, state):
        print('run_script: ', action)
        if action["actionData"]["awaitScript"]:
            outputs = subprocess.run(action["actionData"]["shellScript"], cwd="/", shell=True, capture_output=True)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8')
            # print('output : ', outputs, 'state : ', state)
            return state
        else:
            proc = subprocess.Popen(action["actionData"]["shellScript"], cwd="/", shell=True)
            return state

    def handle_action(self, action, state, props, log_level, log_folder):
        if action["actionName"] == "shellScript":
            return ScriptExecutionState.SUCCESS, self.run_script(action, state)
        elif action["actionName"] == "sleepStatement":
            time.sleep(int(action["actionData"]["sleepTime"]))
            return ScriptExecutionState.SUCCESS, state