#!/bin/bash
# Invoke PyInstaller through the venv interpreter rather than `source venv/bin/activate`.
# activate hardcodes an absolute VIRTUAL_ENV recorded at creation time, so it silently
# points PATH at a directory that no longer exists once the checkout moves, and the build
# dies with "pyinstaller: command not found". `python -m` needs no PATH and no activation,
# and matches what runStartDeviceController.sh and its siblings already do.
set -euo pipefail
cd "$(dirname "$0")"
exec venv/bin/python -m PyInstaller --clean -y script_engine.spec
