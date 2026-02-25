# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import platform
sys.path.append(os.path.join(os.getcwd(), 'ScriptEngine'))

block_cipher = None

# Platform-specific path adjustments
if platform.system() == 'Darwin':  # Mac OS
    torch_lib_path = os.path.join("venv", "lib", "python3.x", "site-packages", "torch", "lib")
    torch_path = os.path.join("venv", "lib", "python3.x", "site-packages", "torch")
else:  # Windows
    torch_lib_path = os.path.join("venv", "Lib", "site-packages", "torch", "lib")
    torch_path = os.path.join("venv", "Lib", "site-packages", "torch")

# Analyses for all executables
device_secrets_manager_a = Analysis(
    ['ScriptEngine/managers/device_secrets_manager.py'],
    pathex=[],
    binaries=[],
    datas=[

    ],
    hiddenimports=[

    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

log_preview_a = Analysis(
    ['ScriptEngine/script_log_preview_generator.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(os.path.expanduser("~"), ".EasyOCR"), ".EasyOCR"),
        (torch_lib_path, "torch/lib"),
        (torch_path, "torch"),
    ],
    hiddenimports=[
        'PIL', 'numpy', 'ScriptEngine.script_log_tree_generator'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

device_controller_a = Analysis(
    ['ScriptEngine/device_controller.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PIL', 'numpy', 'ScriptEngine'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

script_manager_a = Analysis(
    ['ScriptEngine/script_manager.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'torch', 'torchvision', 'easyocr', 'PIL', 'skimage', 'numpy', 'scipy', 'ScriptEngine'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

# MERGE to share dependencies
MERGE(
    (script_manager_a, 'script_manager', 'script_manager'),
    (log_preview_a, 'script_log_preview_generator', 'script_log_preview_generator'),
    (device_controller_a, 'device_controller', 'device_controller'),
    (device_secrets_manager_a, 'device_secrets_manager', 'device_secrets_manager')
)

# Create PYZ archives
pyz0 = PYZ(device_secrets_manager_a.pure, device_secrets_manager_a.zipped_data, cipher=block_cipher)
pyz1 = PYZ(log_preview_a.pure, log_preview_a.zipped_data, cipher=block_cipher)
pyz2 = PYZ(device_controller_a.pure, device_controller_a.zipped_data, cipher=block_cipher)
pyz3 = PYZ(script_manager_a.pure, script_manager_a.zipped_data, cipher=block_cipher)

# Create EXEs
exe0 = EXE(pyz0, device_secrets_manager_a.scripts, [], exclude_binaries=True, name='device_secrets_manager', debug=False, strip=False, upx=True, console=True)
exe1 = EXE(pyz1, log_preview_a.scripts, [], exclude_binaries=True, name='script_log_preview_generator', debug=False, strip=False, upx=True, console=True)
exe2 = EXE(pyz2, device_controller_a.scripts, [], exclude_binaries=True, name='device_controller', debug=False, strip=False, upx=True, console=True)
exe3 = EXE(pyz3, script_manager_a.scripts, [], exclude_binaries=True, name='script_manager', debug=False, strip=False, upx=True, console=True)

# COLLECT everything into one directory
COLLECT(
    exe0,
    device_secrets_manager_a.binaries,
    device_secrets_manager_a.zipfiles,
    device_secrets_manager_a.datas,
    exe1,
    log_preview_a.binaries,
    log_preview_a.zipfiles,
    log_preview_a.datas,
    exe2,
    device_controller_a.binaries,
    device_controller_a.zipfiles,
    device_controller_a.datas,
    exe3,
    script_manager_a.binaries,
    script_manager_a.zipfiles,
    script_manager_a.datas,
    strip=False,
    upx=True,
    name='script_engine'
) 