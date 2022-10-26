from flask import Flask
from flask_cors import CORS
import os

UPLOAD_FOLDER = '.\\scripts'
TEMP_FOLDER = '.\\tmp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER + '\\backups', exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

app = Flask(__name__,template_folder='./logs')
CORS(app)
app.secret_key = "Not reccomended to leave server running for too long as there may be security issues"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024