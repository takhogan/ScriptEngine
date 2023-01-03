dir C:\Users\\takho\\ScriptEngine\\scripts\\scriptFolders\\\*.zip
@echo off
set /p "id=Enter ID: "
start cmd /k "chdir C:\Users\takho\ScriptEngine && C:\Users\takho\ScriptEngine\venv\Scripts\activate && python C:\Users\takho\ScriptEngine\ScriptEngine\script_manager.py %id%