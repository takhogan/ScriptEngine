from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()

class SystemScriptHandler:
    def __init__(self):
        pass

    @staticmethod
    def handle_system_script(device_controller, script_name, script_args):
        script_logger.log('SystemScriptHandler: Handling system script', script_name)
        if script_name == 'startDevice':
            device_controller.get_device_action('adb', 'start_device')()
            return "return"
        elif script_name == 'stopDevice':
            device_controller.get_device_action('adb', 'stop_device')()
            return "return"
