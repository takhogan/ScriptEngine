@echo off
REM See runBuild.sh: call the venv interpreter directly instead of activating, so the
REM build does not depend on the absolute path baked into the activate script.
REM PyInstaller writes dist\ and build\ to the working directory, and the spec puts
REM .\ScriptEngine on sys.path, so run from this folder whatever the caller's cwd.
REM setlocal hands the caller its own directory back when the script ends.
setlocal
cd /d "%~dp0"
venv\Scripts\python.exe -m PyInstaller --clean -y script_engine.spec
