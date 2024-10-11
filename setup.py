from cx_Freeze import setup, Executable
import sys
import os
os.environ['CX_FREEZE_LOG_LEVEL'] = 'ERROR'
sys.path.append(os.path.join(os.path.dirname(__file__), 'ScriptEngine'))



executables = [Executable("ScriptEngine/script_manager.py"),Executable("ScriptEngine/adb_host_controller.py"), Executable("ScriptEngine/python_host_controller.py")]


options = {
    'build_exe': {
        'packages': ["ScriptEngine"]
    }
}

setup(
    name = "Script Engine",
    options = options,
    version = "1.0",
    description = 'Runs script studio scripts',
    executables = executables
)
