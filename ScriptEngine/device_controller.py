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

import asyncio
import base64
import json
import sys
import datetime
import os


from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from ScriptEngine.custom_thread_pool import CustomThreadPool
script_logger = ScriptLogger()
from typing import Dict
from ScriptEngine.managers.device_manager import DeviceManager
from ScriptEngine.managers.device_secrets_manager import DeviceSecretsManager
from ScriptEngine.common.script_engine_utils import DummyFile

from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter


DEVICES_CONFIG_PATH = './assets/host_devices_config.json'
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')


class DeviceController:
    def __init__(self, default_props, default_device_params, io_executor : CustomThreadPool, secrets_manager: DeviceSecretsManager):
        script_logger.log('Intializing Device Manager')
        if 'script-engine-device-type' in default_device_params and default_device_params['script-engine-device-type'] == 'file':
            self.input_source = default_device_params
        else:
            self.input_source = None
        
        self.default_props = default_props
        self.default_device_params = default_device_params
        self.io_executor = io_executor
        self.secrets_manager = secrets_manager

        self.devices: Dict[str, DeviceManager] = {}
    
    def initialize_device(self, device_type, device_params=None):
        if device_params is not None and device_params['deviceId'] in self.devices:
            return self.devices[device_params['deviceId']]
        elif device_type in self.devices:
            return self.devices[device_type]
        
        if (device_type == 'python'):
            from ScriptEngine.managers.desktop_device_manager import DesktopDeviceManager
            if device_params is None:
                self.devices[device_type] = DesktopDeviceManager(self.default_props.copy(), self.input_source)
                return self.devices[device_type]
            else:
                self.devices[device_params['deviceId']] = DesktopDeviceManager(self.default_props.copy(), self.input_source)
                return self.devices[device_params['deviceId']]
        elif (device_type == 'adb'):
            from ScriptEngine.managers.adb_device_manager import ADBDeviceManager
            if device_params is None:
                self.devices[device_type] = ADBDeviceManager(self.default_props.copy(), self.default_device_params, self.input_source)
                return self.devices[device_type]
            else:
                device_params = self.get_device_params(device_params['deviceId'])
                self.devices[device_params['deviceId']] = ADBDeviceManager(self.default_props.copy(), device_params, self.input_source)
                return self.devices[device_params['deviceId']]
        elif (device_type == 'kvm'):
            from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager
            if device_params is None:
                password_name = self.default_device_params['passwordName']
                password = self.secrets_manager.get_secret(password_name)
                self.devices[device_type] = PiKVMDeviceManager(
                    self.default_device_params['ip'], 
                    self.default_device_params['username'], 
                    password,
                    self.input_source
                )
                return self.devices[device_type]
            else:
                device_params = self.get_device_params(device_params['deviceId'])
                password_name = device_params['passwordName']
                password = self.secrets_manager.get_secret(password_name)
                self.devices[device_params['deviceId']] = PiKVMDeviceManager(
                    device_params['ip'],
                    device_params['username'],
                    password,
                    self.input_source
                )
                return self.devices[device_params['deviceId']]
    
    def get_device_action(self, device_type, action_type, device_params=None):
        device = self.initialize_device(device_type, device_params)
        if action_type == 'screenshot':
            return device.screenshot
        elif action_type == 'key_down':
            return device.key_down
        elif action_type == 'key_up':
            return device.key_up
        elif action_type == 'key_press':
            return device.key_press
        elif action_type == 'hotkey':
            return device.hotkey
        elif action_type == 'mouse_down':
            return device.mouse_down
        elif action_type == 'mouse_up':
            return device.mouse_up
        elif action_type == 'mouse_move':
            return device.smooth_move
        elif action_type == 'click':
            return device.click
        elif action_type == 'click_and_drag':
            return device.click_and_drag
        elif action_type == 'scroll':
            return device.scroll
        elif action_type == 'start_device':
            return device.start_device
        elif action_type == 'stop_device':
            return device.stop_device
        elif action_type == 'get_status':
            return device.get_status
    
    def ensure_device_initialized(self, device_type, device_params=None):
        device = self.initialize_device(device_type, device_params)
        device.ensure_device_initialized()
            
    
    def get_device_attribute(self, device_type, attribute_name, device_params=None):
        device = self.initialize_device(device_type, device_params)
        return getattr(device, attribute_name)
    
    def device_id_to_device_type(self, device_id):
        if ':' not in device_id:
            device_type = 'python'
        else:
            device_subtype = device_id.split(':')[0]
            if device_subtype == 'avd' or device_subtype == 'bluestacks':
                device_type = 'adb'
            elif device_subtype == 'pikvm':
                device_type = 'kvm'
        return device_type

    @staticmethod
    def get_device_params(device_key):
        params = None
        with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
            devices_config = json.load(devices_config_file)
            if device_key in devices_config:
                params = devices_config[device_key]
            else:
                script_logger.log('DEVICE CONTROLLER: device config for ', device_key, ' not found! ')
        script_logger.log('DEVICE CONTROLLER: loading args', params)
        return params
    
    def parse_inputs(self, inputs):
        device_key = inputs[1]
        device_type = self.device_id_to_device_type(device_key)
        script_logger.log('DEVICE CONTROLLER: device type', device_type, device_key)
        device_params = {
            'deviceId' : device_key
        }
        
        device_action = inputs[2]
        if device_action == 'check_status':
            status = self.get_device_action(device_type, 'get_status', device_params)()
            return {
                "data": status
            }
        elif device_action == 'screen_capture':
            screenshot = self.get_device_action(device_type, 'screenshot', device_params)()
            from cv2 import imencode
            _, buffer = imencode('.jpg', screenshot)
            byte_array = buffer.tobytes()
            base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
            return {
                "data": base64_encoded_string
            }
        elif device_action == "click":
            # process_adb_host.get_screen_orientation()
            self.get_device_action(device_type, 'click', device_params)(int(float(inputs[3])), int(float(inputs[4])), 'left')
            return {
                "data" : "success"
            }
        elif device_action == "click_and_drag":
            # process_adb_host.get_screen_orientation()
            self.get_device_action(device_type, 'click_and_drag', device_params)(
                int(float(inputs[3])), int(float(inputs[4])), int(float(inputs[5])), int(float(inputs[6]))
            )
            return {
                "data" : "success"
            }
        elif device_action == "send_keys":
            DeviceActionInterpreter.parse_keyboard_action(
                self, json.loads(inputs[3]), {}, {}
            )
            return {
                "data": "success"
            }



async def read_input(device_controller: DeviceController):
    script_logger.log("DEVICE CONTROLLER PROCESS: listening for input")
    input_line = ''
    while True:
        input_line += await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = input_line.strip().split('###')
        if len(inputs) <= 2:
            script_logger.log('DEVICE CONTROLLER PROCESS: received partial inputs ', inputs)
            continue
        inputs = inputs[0:2] + inputs[2].split(' ')
        input_line = ''
        script_logger.log('DEVICE CONTROLLER PROCESS: received inputs ', inputs)
        if len(inputs) > 2:
            try:
                output = device_controller.parse_inputs(inputs)
            except Exception as e:
                script_logger.log('DEVICE CONTROLLER: error in parse_inputs', e)
                output = {
                    "data" : "device controller error"
                }
            input_response = json.dumps(output)
            script_logger.log('DEVICE CONTROLLER: Sending response for {}'.format(inputs[0]), flush=True)
            script_logger.log('<--{}-->'.format(inputs[0]) + input_response + '<--{}-->'.format(inputs[0]), file=DummyFile(), flush=True)
            # script_logger.log('DEVICE CONTROLLER: response', input_response, flush=True)
            script_logger.log('DEVICE CONTROLLER: Response sent for {}'.format(inputs[0]), flush=True)

async def device_controller_main(device_controller: DeviceController):
    await asyncio.gather(read_input(device_controller))

if __name__ == '__main__':
    os.makedirs('./logs', exist_ok=True)
    script_logger.set_log_file_path('./logs/{}-device-controller-main.txt'.format(formatted_today))
    script_logger.set_log_header('{}-device-controller-main-'.format(formatted_today))
    script_logger.set_log_folder('./logs/')
    script_logger.set_action_log(ScriptActionLog(
        {
            'actionName' : 'configurationAction',
            'actionGroup' : 0,
            'actionData' : {
                'targetSystem': 'python'
            }
        },
        script_logger.get_log_folder(),
        script_logger.get_log_header(),
        0
    ))
    with CustomThreadPool(max_workers=50) as io_executor:
        asyncio.run(device_controller_main(DeviceController({
            "dir_path": "./",
            "width" : None,
            "height" : None,
            "scriptMode" : 'train'

        }, {}, io_executor, DeviceSecretsManager())))
        asyncio.run(io_executor.soft_shutdown(script_logger))
