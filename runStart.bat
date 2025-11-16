@echo off
set "PYTHONPATH=..\ScriptEngine"
setlocal enabledelayedexpansion
set "args="
for %%a in (%*) do (
    set "args=!args! "%%a""
)
..\ScriptEngine\venv\Scripts\python.exe -m ScriptEngine.script_manager!args!