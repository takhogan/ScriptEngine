from ScriptEngine.common.logging.script_logger import ScriptLogger
from .custom_thread_pool import CustomThreadPool
script_logger = ScriptLogger()
from typing import Dict
from .managers.device_manager import DeviceManager

class DeviceController:
    def __init__(self, base_script_name, props, device_params, io_executor : CustomThreadPool):
        script_logger.log('Intializing Device Manager')
        if 'script-engine-device-type' in device_params and device_params['script-engine-device-type'] == 'file':
            self.input_source = device_params
        else:
            self.input_source = None
        
        self.base_script_name = base_script_name
        self.props = props
        self.device_params = device_params
        self.io_executor = io_executor

        self.devices: Dict[str, DeviceManager] = {}
    
    def initialize_device(self, device_type):
        if (device_type == 'python'):
            from ScriptEngine.managers.desktop_device_manager import DesktopDeviceManager
            self.devices[device_type] = DesktopDeviceManager(self.props.copy(), self.input_source)
        elif (device_type == 'adb'):
            from ScriptEngine.managers.adb_device_manager import ADBDeviceManager
            self.devices[device_type] = ADBDeviceManager(self.props.copy(), self.device_params, self.input_source)

    def get_device_action(self, device_type, action_type):
        self.initialize_device(device_type)
        if action_type == 'screenshot':
            return self.devices[device_type].screenshot
        elif action_type == 'key_down':
            return self.devices[device_type].keyDown
        elif action_type == 'key_up':
            return self.devices[device_type].keyUp
        elif action_type == 'press':
            return self.devices[device_type].press
        elif action_type == 'hotkey':
            return self.devices[device_type].hotkey
        elif action_type == 'mouse_down':
            return self.devices[device_type].mouse_down
        elif action_type == 'mouse_up':
            return self.devices[device_type].mouse_up
        elif action_type == 'mouse_move':
            return self.devices[device_type].smooth_move
        elif action_type == 'click':
            return self.devices[device_type].click
        elif action_type == 'click_and_drag':
            return self.devices[device_type].click_and_drag
        elif action_type == 'scroll':
            return self.devices[device_type].scroll
        elif action_type == 'start_device':
            return self.devices[device_type].start_device
        elif action_type == 'stop_device':
            return self.devices[device_type].stop_device
            
    
    def get_device_attribute(self, device_type, attribute_name):
        return getattr(self.devices[device_type], attribute_name)
