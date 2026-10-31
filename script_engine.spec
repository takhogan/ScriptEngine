# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import sysconfig
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    datas=[],
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