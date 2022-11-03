import json

from flask import Flask
from flask_cors import CORS
import os

UPLOAD_FOLDER = '.\\scripts'
TEMP_FOLDER = '.\\tmp'
ASSETS_FOLDER = '.\\assets'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER + '\\scriptFolders', exist_ok=True)
os.makedirs(UPLOAD_FOLDER + '\\scriptBackups', exist_ok=True)
os.makedirs(UPLOAD_FOLDER + '\\scriptLibrary', exist_ok=True)
os.makedirs(UPLOAD_FOLDER + '\\scriptLibraryBackups', exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)
WHITELIST_PATH = ASSETS_FOLDER + '\\whitelist.json'
if not os.path.exists(WHITELIST_PATH):
    with open(WHITELIST_PATH, 'w') as whitelist_file:
        whitelist_file.write('{}')

app = Flask(__name__,template_folder='./logs')
CORS(app)
app.secret_key = "Not reccomended to leave server running for too long as there may be security issues"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['ASSETS_FOLDER'] = ASSETS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
with open(WHITELIST_PATH, 'r') as white_list_file:
    whitelist_json = json.load(white_list_file)
    whitelist = {key for key,value in whitelist_json.items() if value == 'T'}
print('whitelist :', whitelist)
app.config['WHITELIST_IPS'] = whitelist
