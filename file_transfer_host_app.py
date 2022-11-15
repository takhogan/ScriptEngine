import json

from flask import Flask
from flask_cors import CORS
import os
import platform

from utils.file_transfer_host_utils import os_normalize_path

app = Flask(__name__,template_folder='./logs')
CORS(app)

app.config['PLATFORM'] = platform.system()



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
