from cx_Freeze import setup, Executable
import sys
import os
os.environ['CX_FREEZE_LOG_LEVEL'] = 'ERROR'
sys.path.append(os.path.join(os.path.dirname(__file__), 'ScriptEngine'))
sys.setrecursionlimit(5000)

executables = [
    Executable("ScriptEngine/script_manager.py"),
    Executable("ScriptEngine/adb_host_controller.py"), 
    Executable("ScriptEngine/python_host_controller.py"), 
    Executable("ScriptEngine/script_log_preview_generator.py")
]
model_path = os.path.join(os.path.expanduser("~"), ".EasyOCR")
include_files = [(model_path, ".EasyOCR")]


torch_lib_path = os.path.join("venv", "Lib", "site-packages", "torch", "lib")
torch_modules = os.path.join("venv", "Lib", "site-packages", "torch")

include_files += [
    (torch_lib_path, "lib"),  # Include shared libraries
    (torch_modules, "torch"),  # Include all PyTorch modules
]

options = {
    'build_exe': {
        "packages": ["ScriptEngine", "torch", "torchvision", "easyocr", "PIL", "skimage", "numpy", "scipy"],
        "includes": [],
        "excludes": [],
        "include_files": include_files
    }
}

setup(
    name = "Script Engine",
    options = options,
    version = "1.0",
    description = 'Runs script studio scripts',
    executables = executables
)
