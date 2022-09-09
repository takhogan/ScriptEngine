import os
import datetime
import urllib.request
from io import BytesIO
import glob

from file_transfer_host_app import app
from flask import Flask, request, redirect, jsonify, make_response, send_file
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
import shutil
import pyautogui
import subprocess

ALLOWED_EXTENSIONS = set(['zip'])
ALLOWED_IPS = set([
    '10.0.0.98',
    '10.0.0.119',
    '10.0.0.8'
])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/img-paths', methods=['GET'])
def get_img_paths():
    def order_script_log_paths_by_date(log_paths, folder_index):
        log_paths_split = list(map(os.path.split, log_paths))
        str_to_datetime = lambda datetime_str: datetime.datetime.now().strptime(datetime_str, '%Y-%m-%d %H-%M-%S')
        log_path_timestamps = list(map(str_to_datetime, map(lambda log_path: '-'.join(log_path[folder_index].split('-')[1:]), log_paths_split)))
        log_paths_w_timestamp = list(zip(log_paths, log_path_timestamps))
        log_paths_w_timestamp.sort(key=lambda log_pair: log_pair[1], reverse=True)
        return log_paths_w_timestamp

    log_paths = glob.glob('C:\\Users\\takho\\ScriptEngine\\logs\\*')
    log_paths_w_timestamp = order_script_log_paths_by_date(log_paths, -1)[-5:]
    logs_obj = []
    for log_path,log_timestamp in log_paths_w_timestamp:
        log_imgs = glob.glob(log_path + '\\**\\*.png', recursive=True)
        log_imgs_w_timestamp = order_script_log_paths_by_date(log_imgs, -2)
        logs_obj.append({
            'log_path' : log_path,
            'log_timestamp' : log_timestamp,
            'log_imgs' : log_imgs_w_timestamp
        })
    return jsonify(logs_obj)

@app.route('/github-pull', methods=['GET'])
def github_pull():
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp

    return (subprocess.check_output('git pull'), 201)


@app.route('/capture', methods=['GET'])
def capture():
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }

        return ('', 204, headers)

    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type' : 'application/json'
    }
    print('received request ', request.remote_addr)

    # https://stackoverflow.com/questions/7877282/how-to-send-image-generated-by-pil-to-browser
    def serve_pil_image(pil_img):
        img_io = BytesIO()
        pil_img.save(img_io, 'JPEG', quality=70)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')

    screenshot = pyautogui.screenshot()
    return serve_pil_image(screenshot)

@app.route('/file-upload', methods=['POST', 'OPTIONS'])
@cross_origin()
def upload_file():
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }

        return ('', 204, headers)

    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type' : 'application/json'
    }
    print('received request ', request.remote_addr)
    # check if the post request has the file part
    if 'file' not in request.files:
        print('no file in request')
        resp = jsonify({'message' : 'No file part in the request'})
        resp.status_code = 400
        return make_response(resp, 400)
    file = request.files['file']
    if file.filename == '':
        print('no file selected')
        resp = jsonify({'message' : 'No file selected for uploading'})
        resp.status_code = 400
        return make_response(resp, 400)
    if file and allowed_file(file.filename):
        print('starting upload')
        filename = secure_filename(file.filename)
        pathname = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        dir_pathname = os.path.join(app.config['UPLOAD_FOLDER'], os.path.splitext(filename)[0])
        if os.path.exists(pathname):
            datetime_now = str(datetime.datetime.now()).replace(':', '-').replace('.', '-').replace(' ', '-')
            new_filename = os.path.join(
                app.config['UPLOAD_FOLDER'],
                'backups',
                os.path.splitext(filename)[0] + '-' + datetime_now + '.zip')
            print('creating backup - ' + new_filename)
            shutil.copy(pathname, new_filename)
            os.remove(pathname)
        if os.path.exists(dir_pathname):
            shutil.rmtree(dir_pathname)
        print('saving file')
        file.save(pathname)
        shutil.unpack_archive(pathname, app.config['UPLOAD_FOLDER'])
        resp = jsonify({'message' : 'File successfully uploaded'})
        # resp.status_code = 201
        return make_response(resp, 201)
    else:
        print('invalid file type')
        resp = jsonify({'message' : 'Allowed file types are zip'})
        # resp.status_code = 400
        return make_response(resp, 400)



# def gcloud_endpoint(request):
#     if request.method == 'OPTIONS':
#         # Allows GET requests from any origin with the Content-Type
#         # header and caches preflight response for an 3600s
#         headers = {
#             'Access-Control-Allow-Origin': '*',
#             'Access-Control-Allow-Methods': 'GET',
#             'Access-Control-Allow-Headers': 'Content-Type',
#             'Access-Control-Max-Age': '3600'
#         }
#
#         return ('', 204, headers)
#
#     headers = {
#         'Access-Control-Allow-Origin': '*',
#         'Content-Type' : 'application/json'
#     }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port="3849")