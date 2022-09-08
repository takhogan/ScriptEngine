import os
import datetime
import urllib.request
from io import BytesIO

import pyautogui
from script_scheduler_host_app import app
from flask import Flask, request, redirect, jsonify, make_response, send_file
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
import shutil

ALLOWED_EXTENSIONS = set(['zip'])
ALLOWED_IPS = set([
    '10.0.0.98',
    '10.0.0.119'
])

@app.route('/capture', methods=['GET'])
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

    # https://stackoverflow.com/questions/7877282/how-to-send-image-generated-by-pil-to-browser
    def serve_pil_image(pil_img):
        img_io = BytesIO()
        pil_img.save(img_io, 'JPEG', quality=70)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')

    screenshot = pyautogui.screenshot()
    return serve_pil_image(screenshot)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="3851")