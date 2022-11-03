import datetime
import urllib.request
import glob

from script_launcher_app import app
from flask import request, redirect, jsonify, make_response, send_from_directory, render_template
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
    def buttonize(script_file):
        return "<li><a href=\"/run/" + script_file.split('.')[0] + "\"/>" + script_file + "</a></li>"
    script_files = subprocess.check_output([
        'dir',
        'C:\\Users\\takho\\ScriptEngine\\scripts\\',
        '/b',
        '/a-d'], shell=True
    ).decode('utf-8').split('\r\n')
    script_file_buttons = '<br>'.join(list(map(buttonize, script_files)))
    return (script_file_buttons, 201)

@app.route('/run/<scriptname>')
def run_script(scriptname):
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    #use subprocess
    return (scriptname + ' started!', 201)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="3851")