# -*- mode: python ; coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'ScriptEngine'))

block_cipher = None

# Analyses for all executables
log_preview_a = Analysis(
    ['ScriptEngine/script_log_preview_generator.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(os.path.expanduser("~"), ".EasyOCR"), ".EasyOCR"),
        (os.path.join("venv", "Lib", "site-packages", "torch", "lib"), "torch/lib"),
        (os.path.join("venv", "Lib", "site-packages", "torch"), "torch"),
    ],
    hiddenimports=[
        'PIL', 'numpy'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

python_controller_a = Analysis(
    ['ScriptEngine/python_host_controller.py'],
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

adb_controller_a = Analysis(
    ['ScriptEngine/adb_host_controller.py'],
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
    (log_preview_a, 'script_log_preview_generator', 'script_log_preview_generator'),
    (python_controller_a, 'python_host_controller', 'python_host_controller'),
    (adb_controller_a, 'adb_host_controller', 'adb_host_controller'),
    (script_manager_a, 'script_manager', 'script_manager')
)

# Create PYZ archives
pyz1 = PYZ(log_preview_a.pure, log_preview_a.zipped_data, cipher=block_cipher)
pyz2 = PYZ(python_controller_a.pure, python_controller_a.zipped_data, cipher=block_cipher)
pyz3 = PYZ(adb_controller_a.pure, adb_controller_a.zipped_data, cipher=block_cipher)
pyz4 = PYZ(script_manager_a.pure, script_manager_a.zipped_data, cipher=block_cipher)

# Create EXEs
exe1 = EXE(pyz1, log_preview_a.scripts, [], name='script_log_preview_generator', debug=False, strip=False, upx=True, console=True)
exe2 = EXE(pyz2, python_controller_a.scripts, [], name='python_host_controller', debug=False, strip=False, upx=True, console=True)
exe3 = EXE(pyz3, adb_controller_a.scripts, [], name='adb_host_controller', debug=False, strip=False, upx=True, console=True)
exe4 = EXE(pyz4, script_manager_a.scripts, [], name='script_manager', debug=False, strip=False, upx=True, console=True)

# COLLECT everything into one directory
COLLECT(
    exe1,
    log_preview_a.binaries,
    log_preview_a.zipfiles,
    log_preview_a.datas,
    exe2,
    python_controller_a.binaries,
    python_controller_a.zipfiles,
    python_controller_a.datas,
    exe3,
    adb_controller_a.binaries,
    adb_controller_a.zipfiles,
    adb_controller_a.datas,
    exe4,
    script_manager_a.binaries,
    script_manager_a.zipfiles,
    script_manager_a.datas,
    strip=False,
    upx=True,
    name='script_engine'
) 