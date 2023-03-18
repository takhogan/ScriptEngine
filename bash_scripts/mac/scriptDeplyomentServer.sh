SCRIPT_ENGINE_PATH="/Users/takhogan/Dropbox/Mac (2)/Documents/ScriptEngine"
cd "$SCRIPT_ENGINE_PATH";
pwd;
source venv_host_server/bin/activate;
python3 file_transfer_host.py;
deactivate;