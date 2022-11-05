import json

from flask import Flask
from flask_cors import CORS
import os

UPLOAD_FOLDER = '.\\scripts'
TEMP_FOLDER = '.\\tmp'
ASSETS_FOLDER = '.\\assets'
os.makedirs(TEMP_FOLDER, exist_ok=True)
WHITELIST_PATH = ASSETS_FOLDER + '\\whitelist.json'
if not os.path.exists(WHITELIST_PATH):
    with open(WHITELIST_PATH, 'w') as whitelist_file:
        whitelist_file.write('{}')

app = Flask(__name__,template_folder='./logs')
CORS(app)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['UPLOAD_SCRIPT_FOLDER'] = UPLOAD_FOLDER + '\\scriptFolders'
app.config['UPLOAD_LIBRARY_FOLDER'] = UPLOAD_FOLDER + '\\scriptLibrary'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_SCRIPT_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_LIBRARY_FOLDER'], exist_ok=True)

app.config['UPLOAD_SCRIPT_BACKUPS_FOLDER'] = UPLOAD_FOLDER + '\\scriptFolderBackups'
app.config['UPLOAD_LIBRARY_BACKUPS_FOLDER'] = UPLOAD_FOLDER + '\\scriptLibraryBackups'
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
