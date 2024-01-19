class SystemScriptHandler:
    def __init__(self):
        pass

    @staticmethod
    def handle_system_script(device_manager, script_name, script_args):
        print('handle system script', script_name)
        if script_name == 'startDevice':
            device_manager.adb_host.start_device()
            return "return"
        elif script_name == 'stopDevice':
            device_manager.adb_host.stop_device()
            return "return"