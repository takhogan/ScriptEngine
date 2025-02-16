# -*- mode: python ; coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'ScriptEngine'))

block_cipher = None

# Define the binaries to create
a = Analysis(
    ['ScriptEngine/script_manager.py'],  # Main script
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(os.path.expanduser("~"), ".EasyOCR"), ".EasyOCR"),
        (os.path.join("venv", "Lib", "site-packages", "torch", "lib"), "torch/lib"),
        (os.path.join("venv", "Lib", "site-packages", "torch"), "torch"),
    ],
    hiddenimports=[
        'torch',
        'torchvision',
        'easyocr',
        'PIL',
        'skimage',
        'numpy',
        'scipy',
        'ScriptEngine'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Main script executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='script_manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Additional executables
other_executables = [
    'ScriptEngine/adb_host_controller.py',
    'ScriptEngine/python_host_controller.py',
    'ScriptEngine/script_log_preview_generator.py'
]

other_analyses = []
other_exes = []

for script in other_executables:
    a = Analysis(
        [script],
        pathex=[],
        binaries=[],
        datas=[],  # Each exe will share the same data files from the main bundle
        hiddenimports=[
            'torch',
            'torchvision',
            'easyocr',
            'PIL',
            'skimage',
            'numpy',
            'scipy',
            'ScriptEngine'
        ],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    other_analyses.append(a)
    
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
    
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=os.path.splitext(os.path.basename(script))[0],
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    other_exes.append(exe)

# Create the collection including all executables
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[exe for exe in other_exes],
    *[a.binaries for a in other_analyses],
    *[a.zipfiles for a in other_analyses],
    *[a.datas for a in other_analyses],
    strip=False,
    upx=True,
    upx_exclude=[],
    name='script_engine',
) 