from python_host_controller import python_host
from adb_host_controller import adb_host
from system_host_controller import SystemHostController
from script_logger import ScriptLogger
script_logger = ScriptLogger()

class DeviceManager:
    def __init__(self, base_script_name, props, adb_args):
        script_logger.log('Intializing Device Manager')
        self.python_host = python_host(props.copy())
        self.adb_host = adb_host(props.copy(), self.python_host, adb_args)
        self.system_host = SystemHostController(base_script_name, props.copy())