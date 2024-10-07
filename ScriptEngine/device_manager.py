from python_host_controller import python_host
from adb_host_controller import adb_host
from system_host_controller import SystemHostController
from script_logger import ScriptLogger
script_logger = ScriptLogger()

class DeviceManager:
    def __init__(self, base_script_name, props, device_params, io_executor):
        script_logger.log('Intializing Device Manager')
        if 'script-engine-device-type' in device_params and device_params['script-engine-device-type'] == 'file':
            input_source = device_params
        else:
            input_source = None
        self.python_host = python_host(props.copy(), io_executor, input_source=input_source)
        self.adb_host = adb_host(props.copy(), self.python_host, device_params, io_executor, input_source=input_source)
        self.system_host = SystemHostController(base_script_name, props.copy(), io_executor)