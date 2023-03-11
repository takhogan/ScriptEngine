import atexit
import json
import subprocess

from flask import Flask
from flask_cors import CORS
import os
import socket
import platform


from utils.file_transfer_host_utils import os_normalize_path

# from flask.ext.cache import Cache

# Set up Flask-Cache

app = Flask(__name__,template_folder='./logs')
CORS(app)
# cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.config['PLATFORM'] = platform.system()
app.config['SUBPROCESSES'] = []

LOGFILE_FOLDER = '.\\logs\\'
os.makedirs(LOGFILE_FOLDER, exist_ok=True)
app.config['LOGFILE_FOLDER'] = LOGFILE_FOLDER

SCRIPT_SERVER_PORT = 3849
FILE_SERVER_PORT = SCRIPT_SERVER_PORT - 1
app.config["SCRIPT_SERVER_PORT"] = SCRIPT_SERVER_PORT

BASE_FOLDER = os.getcwd()

app.config['SUBPROCESSES'].append(
    subprocess.Popen(['python', '-m', 'http.server', str(FILE_SERVER_PORT)], cwd=BASE_FOLDER)
)
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

app.config['SUBPROCESSES'].append(
    subprocess.Popen([
        BASE_FOLDER + (
            '\\venv_scheduling_server\\Scripts\\python' if app.config['PLATFORM'] == 'Windows' else
            '/venv_scheduling_server/bin/python'),
        BASE_FOLDER + os_normalize_path('\\script_scheduler.py'),
        socket.gethostbyname(socket.gethostname()),
        str(SCRIPT_SERVER_PORT)],
        cwd=BASE_FOLDER,
        shell=True
    )
)

def on_server_shutdown():
    for server_subprocess in app.config['SUBPROCESSES']:
        if platform.system() == 'Windows':
            server_subprocess.kill()
        else:
            server_subprocess.terminate()

atexit.register(on_server_shutdown)
