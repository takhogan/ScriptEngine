# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import sys
import sysconfig
from PyInstaller.utils.hooks import collect_submodules
sys.path.append(os.path.join(os.getcwd(), 'ScriptEngine'))

block_cipher = None

# site-packages of the interpreter running this build, which is the venv, because
# runBuild.sh/.cmd activate it before invoking pyinstaller.
#
# Asking sysconfig rather than spelling the layout out per platform. The previous
# Darwin branch carried a literal "venv/lib/python3.x/site-packages" that was never
# substituted, so it resolved to nothing and the build failed on a missing datas
# path; the Windows branch hardcoded "venv/Lib", which breaks whenever the venv is
# named or located differently. One derived path is correct on both, and follows a
# Python upgrade automatically.
site_packages = sysconfig.get_paths()["purelib"]
torch_path = os.path.join(site_packages, "torch")
torch_lib_path = os.path.join(torch_path, "lib")

for _required in (torch_path, torch_lib_path):
    if not os.path.isdir(_required):
        raise SystemExit(
            "script_engine.spec: expected to find %s.\n"
            "Run this through runBuild.sh (macOS/Linux) or runBuild.cmd (Windows) so the "
            "venv is active, and make sure dependencies are installed." % _required
        )

# tesserocr 2.10's Windows wheel vendors cysignals as tesserocr.cysignals, and the
# compiled tesserocr module imports it at load time. PyInstaller cannot see an import
# made from inside a .pyd, so without this the bundle ships tesserocr without it and
# every imageToTextAction fails with "No module named 'tesserocr.cysignals'".
# The filter drops cysignals-CSI-helper, a gdb script whose name is not importable.
tesserocr_hiddenimports = collect_submodules('tesserocr', filter=lambda name: '-' not in name)

# Inlined into every *.overlay.html log file; log_overlay.py reads it from
# its own folder, so it ships next to that module.
overlay_renderer_data = (
    'ScriptEngine/common/logging/log_overlay_renderer.js',
    'ScriptEngine/common/logging',
)

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
    datas=[overlay_renderer_data],
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
    datas=[overlay_renderer_data],
    hiddenimports=[
        'torch', 'torchvision', 'easyocr', 'PIL', 'skimage', 'numpy', 'scipy', 'ScriptEngine'
    ] + tesserocr_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

# Fail the build rather than ship an engine whose OCR cannot import. Every compiled
# module in the installed tesserocr package has to be among script_manager's binaries;
# the venv's own tests import tesserocr from site-packages and never see this gap.
_tesserocr_dir = os.path.join(site_packages, 'tesserocr')
_bundled = {os.path.normcase(os.path.normpath(dest)) for dest, _src, _kind in script_manager_a.binaries}
_missing = [
    path for path in glob.glob(os.path.join(_tesserocr_dir, '**', '*.pyd'), recursive=True)
    + glob.glob(os.path.join(_tesserocr_dir, '**', '*.so'), recursive=True)
    if os.path.normcase(os.path.relpath(path, site_packages)) not in _bundled
]
if _missing:
    raise SystemExit(
        "script_engine.spec: these tesserocr extension modules would be left out of the "
        "bundle, so imageToTextAction would fail to import tesserocr:\n  %s"
        % "\n  ".join(_missing)
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