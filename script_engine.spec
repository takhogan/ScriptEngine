# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import subprocess
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError
from PyInstaller.utils.hooks import collect_submodules, copy_metadata
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

# easyocr imports torchvision, and torchvision registers its operators from a compiled
# library at import time. When torch and torchvision are not a matching pair that
# library does not load, and `import easyocr` fails with "operator torchvision::nms
# does not exist". Checked in a child interpreter so torch is never loaded into the
# build process, and before the analyses so a broken venv fails in seconds.
_nms_check = subprocess.run(
    [sys.executable, '-c',
     'import torch; from torchvision.ops import nms; nms(torch.zeros((1, 4)), torch.ones(1), 0.5)'],
    capture_output=True, text=True,
)
if _nms_check.returncode != 0:
    raise SystemExit(
        "script_engine.spec: torchvision's compiled ops do not work in the build venv, so "
        "every easyOCR action would fail to import easyocr. torch and torchvision are "
        "probably not a matching pair; install both from the same index URL.\n%s"
        % _nms_check.stderr.strip().splitlines()[-1]
    )

def package_metadata(*packages):
    """dist-info for packages that read their own version at import time.

    `apple_compress`, `pyimg4` and `readchar` all run
    `__version__ = version(__package__)` in their __init__, which raises
    PackageNotFoundError when the dist-info is not in the bundle. PyInstaller
    copies modules, not metadata, so a frozen build imported them fine until the
    first line of the module ran. That surfaced as
    "ios_check_prerequisites failed: No package metadata was found for
    apple_compress" - a working iPhone reported as not ready.

    A missing package is skipped rather than failing the build: this spec also
    builds on Windows, where pyimg4 pulls in lzfse instead of apple_compress.
    """
    collected = []
    for package in packages:
        try:
            collected += copy_metadata(package, recursive=True)
        except PackageNotFoundError:
            pass
    return collected


# pymobiledevice3 reaches apple_compress through pyimg4, which it does not
# declare as a dependency, so recursion from it alone does not find them.
ios_metadata = package_metadata('pymobiledevice3', 'pyimg4', 'apple_compress', 'readchar')

# tesserocr 2.10's Windows wheel vendors cysignals as tesserocr.cysignals, and the
# compiled tesserocr module imports it at load time. PyInstaller cannot see an import
# made from inside a .pyd, so without this the bundle ships tesserocr without it and
# every imageToTextAction fails with "No module named 'tesserocr.cysignals'".
# The filter drops cysignals-CSI-helper, a gdb script whose name is not importable.
tesserocr_hiddenimports = collect_submodules('tesserocr', filter=lambda name: '-' not in name)


def compiled_extensions(package):
    """Paths of every compiled extension module in an installed package."""
    package_dir = os.path.join(site_packages, package)
    return (glob.glob(os.path.join(package_dir, '**', '*.pyd'), recursive=True)
            + glob.glob(os.path.join(package_dir, '**', '*.so'), recursive=True))


def extension_module_name(path):
    """site-packages/torchvision/_C_stable.pyd -> torchvision._C_stable, minus any ABI tag."""
    folder, filename = os.path.split(os.path.relpath(path, site_packages))
    return '.'.join(folder.split(os.sep) + [filename.split('.')[0]])


# torchvision loads its compiled ops with torch.ops.load_library on a path it works out
# itself, so PyInstaller never sees the import. pyinstaller-hooks-contrib asks for
# torchvision._C, but torchvision 0.29 renamed it _C_stable (and image to image_stable),
# so the hook matched nothing and the bundle shipped with no ops library: every easyOCR
# action then failed in `import easyocr` with "operator torchvision::nms does not
# exist". Naming the extensions the installed torchvision has, rather than a fixed
# list, survives the next rename.
torchvision_hiddenimports = [extension_module_name(path) for path in compiled_extensions('torchvision')]

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
    datas=[overlay_renderer_data] + ios_metadata,
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
    datas=[overlay_renderer_data] + ios_metadata,
    hiddenimports=[
        'torch', 'torchvision', 'easyocr', 'PIL', 'skimage', 'numpy', 'scipy', 'ScriptEngine'
    ] + tesserocr_hiddenimports + torchvision_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
)

# Fail the build rather than ship an engine whose OCR cannot import. Every compiled
# module in the installed tesserocr and torchvision packages has to be among
# script_manager's binaries; the venv's own tests import them from site-packages and
# never see this gap.
_bundled = {os.path.normcase(os.path.normpath(dest)) for dest, _src, _kind in script_manager_a.binaries}
for _package, _consequence in (
    ('tesserocr', 'imageToTextAction would fail to import tesserocr'),
    ('torchvision', 'every easyOCR action would fail to import easyocr'),
):
    _missing = [
        path for path in compiled_extensions(_package)
        if os.path.normcase(os.path.relpath(path, site_packages)) not in _bundled
    ]
    if _missing:
        raise SystemExit(
            "script_engine.spec: these %s extension modules would be left out of the "
            "bundle, so %s:\n  %s" % (_package, _consequence, "\n  ".join(_missing))
        )

# The check above passes on a torchvision with no extensions at all, so also require
# its ops library (_C, or _C_stable from 0.29 on) by name.
_torchvision_ops = os.path.normcase(os.path.join('torchvision', '_C'))
if not any(dest.startswith(_torchvision_ops) for dest in _bundled):
    raise SystemExit(
        "script_engine.spec: no torchvision\\_C extension (.pyd/.so) is among "
        "script_manager's binaries, so every easyOCR action would fail to import easyocr."
    )

# The iOS tunnel server: its own executable because it is the one thing here
# that runs as root (ScriptEngine/ios_tunnel_server.py explains why). Keeping it
# separate means the launchd job names one binary that does one job, rather than
# pointing root at the device controller with a flag.
#
# Signing matters for this one in particular: SMAppService validates the daemon
# against the containing app's code signature at launch, which is what stands in
# for the file-ownership checks a copied-out binary would need. forge's osxSign
# signs every Mach-O in the bundle, this one included.
ios_tunnel_server_a = Analysis(
    ['ScriptEngine/ios_tunnel_server.py'],
    pathex=[],
    binaries=[],
    datas=ios_metadata,
    hiddenimports=[
        # pymobiledevice3 reaches its tunnel transports through
        # remote/module_imports.py, inside a try/except ImportError, so
        # PyInstaller's static analysis does not follow them. A build that
        # leaves them out does not fail: verify_tunnel_imports() returns False
        # at runtime and the daemon exits with EXIT_IMPORTS_MISSING.
        'pymobiledevice3.remote.tunnel_service',
        'pymobiledevice3.tunneld.server',
        # qh3 carries QUIC (the default transport on this Python) and
        # pytun_pmd3 creates the utun interface, which is the whole reason this
        # process needs root.
        'qh3', 'qh3.asyncio', 'qh3.asyncio.client', 'pytun_pmd3',
        'zeroconf', 'ifaddr', 'construct', 'cryptography', 'opack2', 'aiofiles',
        # tunneld serves its tunnel list over HTTP.
        'uvicorn', 'fastapi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # None of the engine's vision stack is reachable from the tunnel server,
        # and a root daemon has no business loading it. Excluded explicitly so a
        # stray import does not quietly drag it in.
        'torch', 'torchvision', 'easyocr', 'skimage', 'scipy', 'cv2', 'pyautogui',
    ],
)

# MERGE to share dependencies
MERGE(
    (script_manager_a, 'script_manager', 'script_manager'),
    (log_preview_a, 'script_log_preview_generator', 'script_log_preview_generator'),
    (device_controller_a, 'device_controller', 'device_controller'),
    (device_secrets_manager_a, 'device_secrets_manager', 'device_secrets_manager'),
    (ios_tunnel_server_a, 'ios_tunnel_server', 'ios_tunnel_server')
)

# Create PYZ archives
pyz0 = PYZ(device_secrets_manager_a.pure, device_secrets_manager_a.zipped_data, cipher=block_cipher)
pyz1 = PYZ(log_preview_a.pure, log_preview_a.zipped_data, cipher=block_cipher)
pyz2 = PYZ(device_controller_a.pure, device_controller_a.zipped_data, cipher=block_cipher)
pyz3 = PYZ(script_manager_a.pure, script_manager_a.zipped_data, cipher=block_cipher)
pyz4 = PYZ(ios_tunnel_server_a.pure, ios_tunnel_server_a.zipped_data, cipher=block_cipher)

# Create EXEs
exe0 = EXE(pyz0, device_secrets_manager_a.scripts, [], exclude_binaries=True, name='device_secrets_manager', debug=False, strip=False, upx=True, console=True)
exe1 = EXE(pyz1, log_preview_a.scripts, [], exclude_binaries=True, name='script_log_preview_generator', debug=False, strip=False, upx=True, console=True)
exe2 = EXE(pyz2, device_controller_a.scripts, [], exclude_binaries=True, name='device_controller', debug=False, strip=False, upx=True, console=True)
exe3 = EXE(pyz3, script_manager_a.scripts, [], exclude_binaries=True, name='script_manager', debug=False, strip=False, upx=True, console=True)
exe4 = EXE(pyz4, ios_tunnel_server_a.scripts, [], exclude_binaries=True, name='ios_tunnel_server', debug=False, strip=False, upx=True, console=True)

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
    exe4,
    ios_tunnel_server_a.binaries,
    ios_tunnel_server_a.zipfiles,
    ios_tunnel_server_a.datas,
    strip=False,
    upx=True,
    name='script_engine'
) 