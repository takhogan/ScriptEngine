import sys

sys.path.append(".")
from script_execution_state import ScriptExecutionState
import time


from io import BytesIO
from PIL import Image
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim
import datetime
import os

from avd_controller import AVD
from osx_controller import OSX
from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
import subprocess


class ScriptExecutor:
    def __init__(self, script_obj, log_level='INFO'):
        self.log_level = log_level
        self.props = script_obj['props']
        self.actions = script_obj["actionRows"][0]["actions"]
        self.action_rows = script_obj["actionRows"]
        self.avd = self.props['avd']
        self.osx = self.props['osx']
        self.include_scripts = script_obj['include']
        self.log_folder = './logs/' + self.props['script_name'] + '-' + self.props['start_time']
        os.mkdir(self.log_folder)
        self.log_folder += '/'

        self.state = {
            'script_counter': 0
        }

        self.status = ScriptExecutionState.FINISHED


    def handle_action(self, action):
        print('parsing action : ', action["actionName"], ' children: ', list(map(lambda childGroupLink: self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]["actionName"], action['childGroups'])))
        self.state["script_counter"] += 1
        if "targetSystem" in action["actionData"]:
            if action["actionData"]["targetSystem"] == "android":
                self.status, self.state = self.avd.handle_action(action, self.state, self.props, self.log_level, self.log_folder)
            elif action["actionData"]["targetSystem"] == "mac":
                self.status, self.state = self.osx.handle_action(action, self.state, self.props, self.log_level, self.log_folder)
            else:
                self.status = ScriptExecutionState.ERROR
                print("target system " + action["actionData"]["targetSystem"] + " unimplemented!")
                exit(0)
        else:
            if action["actionName"] == 'scriptReference':
                ref_script = self.include_scripts[action["actionData"]["scriptName"]]
                ref_script["props"]["avd"] = self.avd
                ref_script["props"]["osx"] = self.osx
                ref_script["include"] = self.include_scripts
                ref_script["props"]["start_time"] = self.props["start_time"]
                ref_script_executor = ScriptExecutor(ref_script, self.log_level)
                ref_script_executor.run()
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
            elif action["actionName"] == "sleepStatement":
                time.sleep(int(action["actionData"]["sleepTime"]))
                self.status = ScriptExecutionState.SUCCESS
            else:
                print("no target system: ")
                print(action)
                exit(0)


    def execute_actions(self):
        def get_child_action(childGroupLink):
            return self.action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]

        for action in self.actions:
            self.handle_action(action)
            if self.status == ScriptExecutionState.FINISHED:
                self.actions = []
                return
            elif self.status == ScriptExecutionState.SUCCESS:
                self.actions = list(map(get_child_action, action["childGroups"]))
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
            if len(self.actions) == 0:
                break


if __name__ == '__main__':
    # TODO DONT LEAVE PASSCODE IN ANY SOURCE CONTORL
    '''
        
        ./adb shell wm size
        ./adb devices | grep "\<device\>"
        
    '''
