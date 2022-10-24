import os
import datetime
import urllib.request
from io import BytesIO
import glob

from script_launcher_app import app
from flask import Flask, request, redirect, jsonify, make_response, send_file, send_from_directory, render_template
from flask_cors import CORS, cross_origin
import subprocess

ALLOWED_IPS = set([
    '10.0.0.98',
    '10.0.0.117',
    '10.0.0.8'
])


@app.route('/run', methods=['GET'])
def list_run_scripts():
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    return (subprocess.check_output(['ls']), 201)

@app.route('/run/<scriptname>')
def run_script(scriptname):
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    return (scriptname, 201)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="3851")