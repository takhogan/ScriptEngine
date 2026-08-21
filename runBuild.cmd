@echo off
REM See runBuild.sh: call the venv interpreter directly instead of activating, so the
REM build does not depend on the absolute path baked into the activate script.
"%~dp0venv\Scripts\python.exe" -m PyInstaller --clean -y "%~dp0script_engine.spec"
