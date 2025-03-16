@echo off
set "PYTHONPATH=..\ScriptEngine"
..\ScriptEngine\venv\Scripts\python.exe -m ScriptEngine.managers.device_secrets_manager %*