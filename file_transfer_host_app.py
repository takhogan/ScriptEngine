import json
import subprocess

from flask import Flask
from flask_cors import CORS
import os
import platform


from utils.file_transfer_host_utils import os_normalize_path

# from flask.ext.cache import Cache

# Set up Flask-Cache

app = Flask(__name__,template_folder='./logs')
CORS(app)
# cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.config['PLATFORM'] = platform.system()

LOGFILE_FOLDER = '.\\logs\\'
os.makedirs(LOGFILE_FOLDER, exist_ok=True)
app.config['LOGFILE_FOLDER'] = LOGFILE_FOLDER

subprocess.Popen(['python', '-m', 'http.server', '3848'], cwd='C:\\Users\\takho\\ScriptEngine\\')
UPLOAD_FOLDER = os_normalize_path('.\\scripts')
TEMP_FOLDER = os_normalize_path('.\\tmp')
ASSETS_FOLDER = os_normalize_path('.\\assets')
os.makedirs(TEMP_FOLDER, exist_ok=True)
WHITELIST_PATH = ASSETS_FOLDER + os_normalize_path('\\whitelist.json')
if not os.path.exists(WHITELIST_PATH):
    with open(WHITELIST_PATH, 'w') as whitelist_file:
        whitelist_file.write('{}')



app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['UPLOAD_SCRIPT_FOLDER'] = UPLOAD_FOLDER + os_normalize_path('\\scriptFolders')
app.config['UPLOAD_LIBRARY_FOLDER'] = UPLOAD_FOLDER + os_normalize_path('\\scriptLibrary')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

os.makedirs(app.config['UPLOAD_SCRIPT_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_LIBRARY_FOLDER'], exist_ok=True)

app.config['UPLOAD_SCRIPT_BACKUPS_FOLDER'] = UPLOAD_FOLDER + os_normalize_path('\\scriptFolderBackups')
app.config['UPLOAD_LIBRARY_BACKUPS_FOLDER'] = UPLOAD_FOLDER + os_normalize_path('\\scriptLibraryBackups')
os.makedirs(app.config['UPLOAD_SCRIPT_BACKUPS_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_LIBRARY_BACKUPS_FOLDER'], exist_ok=True)


app.secret_key = "Not reccomended to leave server running for too long as there may be security issues"

app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['ASSETS_FOLDER'] = ASSETS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
with open(WHITELIST_PATH, 'r') as white_list_file:
    whitelist_json = json.load(white_list_file)
    whitelist = {key for key,value in whitelist_json.items() if value == 'T'}
print('whitelist :', whitelist)
app.config['WHITELIST_IPS'] = whitelist

# subprocess.Popen([
#     'C:\\Users\\takho\\ScriptEngine\\venv_scheduling_server\\Scripts\\python',
#     'C:\\Users\\takho\\ScriptEngine\\script_scheduler.py'],
#     cwd='C:\\Users\\takho\\ScriptEngine',
#     shell=True
# )