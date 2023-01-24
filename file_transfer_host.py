import json
import mimetypes
import os
import datetime
import urllib.request
from io import BytesIO
import glob
from zipfile import ZipFile

from progressbar import ProgressBar
from waitress import serve

from file_transfer_host_app import app#, cache
# from ScriptEngine.script_engine_constants import RUNNING_SCRIPTS_PATH
RUNNING_SCRIPTS_PATH = './tmp/running_scripts.json'
from flask import Flask, request, redirect, Response, jsonify, make_response, send_file, send_from_directory, render_template
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
import shutil
import pyautogui
import subprocess
import threading
import sys
import platform
from utils.file_transfer_host_utils import os_normalize_path

ALLOWED_EXTENSIONS = set(['zip'])

DEFAULT_HTML_HEADER = '''
    <head>
    <style>
      ul {
        column-width: 300px;
        column-gap: 20px;
        column-count: 1;
      }
    </style>
  </head>
'''

SERVER_CACHE = {
    'LIBRARY_ZIP' : None
}

COMPONENTS = {
    'DASHBOARD BUTTON' : '<a href="/dashboard"' + '> Click here to run another </a><br>'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def log_request_info():
    if request.remote_addr not in app.config['WHITELIST_IPS']:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    timestamp = datetime.datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
    print(f'{timestamp} {request.remote_addr} {request.method} {request.path}')


#@cache.memoize()
def get_library_zip(library_zip_path, refresh_cache=True):
    if not refresh_cache:
        print('retrieving library zip from cache')
        return BytesIO(SERVER_CACHE['LIBRARY_ZIP'].getvalue())
    stream = BytesIO()
    with open(library_zip_path, 'rb') as library_zip:
        print('writing library zip to stream')
        stream.write(library_zip.read())
        stream.seek(0)
        print('caching result')
        SERVER_CACHE['LIBRARY_ZIP'] = BytesIO(stream.getvalue())
        return stream


# To send back a library script file it must be a zip file
@app.route('/library', strict_slashes=False)
@cross_origin()
def get_library():
    script_files = glob.glob(
        os_normalize_path(app.config['UPLOAD_LIBRARY_FOLDER'] + '\\*.zip')
    )
    library_zip_changelog_path = app.config['TEMP_FOLDER'] + '\\library_zip_changelog.json'
    if os.path.exists(library_zip_changelog_path):
        with open(library_zip_changelog_path, 'r') as library_zip_changelog:
            library_zip_changelog_dict = json.load(library_zip_changelog)
    else:
        library_zip_changelog_dict = {
            script_file: 0 for script_file in script_files
        }

    current_times = {
        script_file: os.stat(script_file).st_mtime for script_file in script_files
    }

    with open(library_zip_changelog_path, 'w') as library_zip_changelog:
        json.dump(current_times, library_zip_changelog)

    library_zip_path = app.config['TEMP_FOLDER'] + '\\library_zip.zip'
    script_files.sort()
    refresh_cache = True
    if current_times.keys() == library_zip_changelog_dict.keys() and\
       all(current_times[script_file] == library_zip_changelog_dict[script_file] for script_file in script_files):
        # refresh_cache = False
        print('library package unchanged')
    else:
        print('updating library package zip')
        with ZipFile(library_zip_path, 'w') as library_zip:
            for script_file in script_files:
                library_zip.write(script_file)
    stream = get_library_zip(library_zip_path, refresh_cache=refresh_cache)

    print('sending library zip')
    return send_file(
        stream,
        as_attachment=False,
        mimetype='.zip'
    )
    # with open(library_zip_path, 'rb') as library_zip:
    #
    #
    #
    # n_script_files = len(script_files)
    # bar = ProgressBar(maxval=n_script_files)
    # bar.start()
    # stream = BytesIO()
    # with ZipFile(stream, 'w') as script_files_zip:
    #     for script_file in script_files:
    #         print('|', end='')
    #         script_files_zip.write(script_file, os.path.basename(script_file))
    #         bar.update(1)
    # print()
    # stream.seek(0)
    # #
    # return send_file(
    #     stream,
    #     as_attachment=False,
    #     mimetype='.zip'
    # )

@app.route('/run/<scriptname>', strict_slashes=False)
def run_script(scriptname):
    if not os.path.exists(RUNNING_SCRIPTS_PATH):
        timeout_val = request.args.get('timeout')
        script_constants = request.args.getlist('args')

        def initialize_script_manager_args(scriptname, timeout_val, script_constants):
            start_time = datetime.datetime.now()
            start_time_str = start_time.strftime('%Y-%m-%d %H-%M-%S')
            script_log_folder = app.config['LOGFILE_FOLDER'] + '0'.zfill(5) + '-' + scriptname + '-' + start_time_str + '\\'
            os.makedirs(script_log_folder, exist_ok=True)
            timeout_val_split = timeout_val.split('h')
            end_time = start_time + datetime.timedelta(hours=int(timeout_val_split[0]),minutes=int(timeout_val_split[1][:-1]))
            end_time_str = end_time.strftime('%Y-%m-%d %H-%M-%S')
            return scriptname, start_time_str, end_time_str, script_constants, script_log_folder



        def run_in_thread(scriptname, start_time_str, end_time_str, script_constants, script_log_folder):
            print('running ', scriptname, 'from', start_time_str, 'to', end_time_str, 'with constants', script_constants)
            with open(script_log_folder + 'stdout.txt', 'w') as log_file:
                shell_process = subprocess.Popen(['C:\\Users\\takho\\ScriptEngine\\venv\\Scripts\\python',
                                                  'C:\\Users\\takho\\ScriptEngine\\ScriptEngine\\script_manager.py',
                                                  scriptname,
                                                  start_time_str,
                                                  end_time_str,
                                                  *script_constants], shell=True,
                                                 stdout=log_file,
                                                 stderr=log_file,
                                                 cwd='C:\\Users\\takho\\ScriptEngine')
                shell_process.wait()
            print('completed ', scriptname, shell_process)
            exit_code = shell_process.returncode
            with open(script_log_folder + 'completed.txt', 'w') as completed_file:
                completed_file.write(scriptname + ' completed at ' + str(datetime.datetime.now()))
            if exit_code == 1:
                return
            if os.path.exists(RUNNING_SCRIPTS_PATH):
                with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                    running_scripts = json.load(running_script_file)
                    script_thread = threading.Thread(
                        target=run_in_thread,
                        args=initialize_script_manager_args(running_scripts[0],'0h30m',[])
                    )
                    script_thread.start()
            return
        script_manager_args = initialize_script_manager_args(scriptname, timeout_val, script_constants)
        script_thread = threading.Thread(target=run_in_thread, args=script_manager_args)
        script_thread.start()
        # returns immediately after the thread starts
        return ('<p>' + scriptname + ' started! </p>' +\
                    '<a href="http://' + request.host.split(':')[0] + ':3848/logs/' + '0'.zfill(5) + '-' + scriptname +\
                    '-' + script_manager_args[1] + '/"' + '> Click here for logs </a><br>' +\
                    '<a href="/capture"' + '> Click here to monitor </a><br>' +\
                    COMPONENTS['DASHBOARD BUTTON'] +\
                    '<a href="/reset"' + '> Click here to terminate </a><br>', 201)
    else:
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
            return ('<p>Please wait for script completion, script: ' + running_script_file.read() + ' still running!</p>' +\
                    '<a href=/enqueue/' + scriptname + '> Click here to enqueue </a><br>' +\
                        '<a href=/reset> Click here to terminate </a><br>', 400)

@app.route('/enqueue/<scriptname>', methods=['GET'], strict_slashes=False)
def enqueue_script(scriptname):
    if not os.path.exists(RUNNING_SCRIPTS_PATH):
        return ('<p> nothing in que </p>' +\
                '<a href="/run/{}"> Click here to run script </a>'.format(scriptname), 400)
    else:
        running_scripts = []
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
            running_scripts = json.load(running_script_file)
        running_scripts.append(scriptname)
        with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
            json.dump(running_scripts, running_script_file)
    return ('<p> Added ' + scriptname + ' to queue. Now running : ' + str(running_scripts) + '  </p>' +\
            COMPONENTS['DASHBOARD BUTTON'], 200)




def get_running_scripts():
    if not os.path.exists(RUNNING_SCRIPTS_PATH):
        return 'None'

    with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
        running_scripts = json.load(running_script_file)
        return str(running_scripts)
    return 'None'

@app.route('/queue', methods=['GET'], strict_slashes=False)
def show_queue():
    return (get_running_scripts(), 200)

@app.route('/dashboard', methods=['GET'], strict_slashes=False)
def show_dashboard():
    capture_img = "<img style=\"width:100%;max-width:600px;\" src=\"/capture\"><br>"
    running_scripts = get_running_scripts() + "<a href=\"/reset\"/> Clear </a>"  + '<br>'
    file_server = '<a href=\"http://' + request.host.split(':')[0] + ':3848/\"> File Server </a><br>'
    runnable_scripts = get_runnable_scripts()
    return (capture_img + running_scripts + file_server + runnable_scripts, 200)


def get_runnable_scripts():
    def buttonize(script_file):
        return "<li><a href=\"/run/" + script_file.split('.')[0] + "?timeout=0h30m\"/>" + script_file + "</a></li>"

    script_files = subprocess.check_output([
                                               'dir',
                                               'C:\\Users\\takho\\ScriptEngine\\scripts\\scriptFolders',
                                               '/b',
                                               '/a-d'] if platform.system() == 'Windows' else [
        'ls'
    ] if platform.system() == 'Darwin' else [

    ], shell=True
                                           ).decode('utf-8').split('\r\n')
    script_files.sort()
    script_file_buttons = '<html>' + DEFAULT_HTML_HEADER + '<body><ul>' + ''.join(list(map(buttonize, script_files))) + \
                          '</ul></body></html>'
    return script_file_buttons

@app.route('/run', methods=['GET'], strict_slashes=False)
def list_run_scripts():

    # script_file_buttons = '<br>'.join()
    return (get_runnable_scripts(), 201)

def get_log_folders():
    script_files = subprocess.check_output([
       'dir',
       'C:\\Users\\takho\\ScriptEngine\\scripts\\logs',
       '/O-D',
       '/AD'] if platform.system() == 'Windows' else [
        'ls'
    ] if platform.system() == 'Darwin' else [

    ], shell=True
    ).decode('utf-8').split('\r\n')

@app.route('/restart', methods=['GET'], strict_slashes=False)
def restart_server():
    # subprocess.Popen([os_normalize_path('bash_scripts\\scriptDeploymentServer.cmd')],
    #                  cwd='C:\\Users\\takho\\ScriptEngine',
    #                  shell=True)
    print('restarting server')
    # exit(0)
    # request.environ.get('waitress.server.shutdown')()
    return ('<p> not restarting server </p>' +\
            '<a href=/run> Click here to run a script </a>', 201)

@app.route('/reset', methods=['GET'], strict_slashes=False)
def reset_running_scripts():
    if os.path.exists(RUNNING_SCRIPTS_PATH):
        os.remove(RUNNING_SCRIPTS_PATH)
    return ('<p>running scripts cleared</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/img-paths', methods=['GET'], strict_slashes=False)
def get_img_paths():
    def order_script_log_paths_by_date(log_paths, folder_index, reverse=True):
        log_paths_split = list(map(lambda log_path: os.path.normpath(log_path).split(os.path.sep), log_paths))
        # print('1', log_paths_split)
        str_to_datetime = lambda datetime_str: datetime.datetime.now().strptime(datetime_str, '%Y-%m-%d %H-%M-%S')
        # print('2', str_to_datetime)
        # print('2.5', list(map(lambda log_path: '-'.join(log_path[folder_index].split('-')[1:]), log_paths_split)))
        # pre_paths = list(map(lambda log_path: '-'.join(log_path[folder_index].split('-')[1:]), log_paths_split))
        # for pre_path_index in range(0, len(pre_paths)):
        #     if pre_paths[pre_path_index] == '':
        #         print(log_paths_split[pre_path_index])
        #         exit(0)
        log_path_timestamps = list(map(str_to_datetime, map(lambda log_path: '-'.join(log_path[folder_index].split('-')[1:]), log_paths_split)))
        # print('3', log_path_timestamps)
        log_paths_w_timestamp = list(zip(log_paths, log_path_timestamps))
        # print('4', log_paths_w_timestamp)
        log_paths_w_timestamp.sort(key=lambda log_pair: log_pair[1], reverse=reverse)
        return log_paths_w_timestamp

    log_paths = glob.glob('C:\\Users\\takho\\ScriptEngine\\logs\\*\\')
    log_paths = list(map(lambda log_path: log_path.replace('C:\\Users\\takho\\ScriptEngine\\logs\\', '')[:-1], log_paths))
    log_paths_w_timestamp = order_script_log_paths_by_date(log_paths, -1)[:5]
    logs_obj = []
    for log_path,log_timestamp in log_paths_w_timestamp:
        log_imgs = glob.glob('logs\\' + log_path + '\\**\\*.png', recursive=True)
        log_imgs = list(map(lambda log_path: log_path.replace('logs\\', ''), log_imgs))
        log_imgs = list(filter(lambda log_path: not os.path.normpath(log_path).split(os.path.sep)[-2].startswith('searchPattern') and\
                          not os.path.normpath(log_path).split(os.path.sep)[-2].startswith('errors'), log_imgs))
        log_imgs_w_timestamp = order_script_log_paths_by_date(log_imgs, -2, reverse=False)
        logs_obj.append({
            'log_path' : log_path,
            'log_timestamp' : log_timestamp,
            'log_imgs' : log_imgs_w_timestamp
        })
    return logs_obj
    # return jsonify(logs_obj)


@app.route('/github-push', methods=['GET'], strict_slashes=False)
def github_push():
    add_output = subprocess.check_output('git add .')
    commit_output = subprocess.check_output('git commit . -m \"server triggered commit ' + str(datetime.datetime.now()) + '\"')
    push_output = subprocess.check_output('git push')
    return ('add: ' + add_output.decode('utf-8') + '\n' +\
            'commit: ' + commit_output.decode('utf-8') + '\n' +\
            'push: ' + push_output.decode('utf-8') + '\n')
@app.route('/github-pull', methods=['GET'], strict_slashes=False)
def github_pull():
    return (subprocess.check_output('git pull'), 201)


@app.route('/capture', methods=['GET'], strict_slashes=False)
def capture():
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

    # https://stackoverflow.com/questions/7877282/how-to-send-image-generated-by-pil-to-browser
    def serve_pil_image(pil_img):
        img_io = BytesIO()
        pil_img.save(img_io, 'JPEG', quality=70)
        img_io.seek(0)
        capture_response = make_response(send_file(img_io, mimetype='image/jpeg'))
        capture_response.headers['Refresh'] = '3; url=/capture'
        return capture_response

    screenshot = pyautogui.screenshot()
    return serve_pil_image(screenshot)


@app.route('/file-upload', methods=['POST', 'OPTIONS'], strict_slashes=False)
@cross_origin()
def upload_file():
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
        is_library_script = 'scriptType' in request.values and request.values['scriptType'] == 'libraryScript'
        filename = secure_filename(file.filename)
        pathname = os.path.join(app.config[
            'UPLOAD_LIBRARY_FOLDER' if is_library_script else 'UPLOAD_SCRIPT_FOLDER'
        ], filename)
        print('received file :', pathname, is_library_script)
        dir_pathname = os.path.join(
            app.config[
                'UPLOAD_LIBRARY_FOLDER' if is_library_script else 'UPLOAD_SCRIPT_FOLDER'
            ],
            os.path.splitext(filename)[0]
        )
        if os.path.exists(pathname):
            datetime_now = str(datetime.datetime.now()).replace(':', '-').replace('.', '-').replace(' ', '-')
            new_filename = os.path.join(
                app.config[
                    'UPLOAD_LIBRARY_BACKUPS_FOLDER' if is_library_script else 'UPLOAD_SCRIPT_BACKUPS_FOLDER'
                ],
                os.path.splitext(filename)[0] + '-' + datetime_now + '.zip')
            print('creating backup - ' + new_filename)
            shutil.copy(pathname, new_filename)
            os.remove(pathname)
        if os.path.exists(dir_pathname):
            shutil.rmtree(dir_pathname)
        file.save(pathname)
        shutil.unpack_archive(pathname, app.config[
            'UPLOAD_LIBRARY_FOLDER' if is_library_script else 'UPLOAD_SCRIPT_FOLDER'
        ])
        print('file saved : ', filename)
        resp = jsonify({'message' : 'File successfully uploaded'})
        # resp.status_code = 201
        return make_response(resp, 201)
    else:
        print('invalid file type')
        resp = jsonify({'message' : 'Allowed file types are zip'})
        # resp.status_code = 400
        return make_response(resp, 400)

# Serving static files
# @app.route('/', defaults={'path': ''})
# @app.route('/<string:path>')
# @app.route('/<path:path>')
def static_proxy(path):
    if os.path.isfile('logs/' + path):
        # If request is made for a file by angular for example main.js
        # condition will be true, file will be served from the public directory
        return send_from_directory('./logs', path)
    else:
        # Otherwise index.html will be served,
        # angular router will handle the rest
        return render_template("index.html")

if __name__ == "__main__":
    # app.run(host="0.0.0.0", port="3849")
    if len(sys.argv) > 1:
        PORT = sys.argv[1]
    serve(app, host="0.0.0.0", port=app.config["SCRIPT_SERVER_PORT"])
