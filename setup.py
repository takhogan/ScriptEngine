from cx_Freeze import setup, Executable
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'ScriptEngine'))



executables = [Executable("ScriptEngine/script_manager.py")]


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
