import json
import mimetypes
import os
import datetime
import urllib.request
from io import BytesIO
import glob
from zipfile import ZipFile
import sys

# from progressbar import ProgressBar
from waitress import serve

from file_transfer_host_app import app#, cache
# from ScriptEngine.script_engine_constants import RUNNING_SCRIPTS_PATH

from flask import Flask, request, redirect, Response, jsonify, make_response, send_file, send_from_directory, render_template, url_for
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
import shutil
import pyautogui
import subprocess
import threading
import sys
import platform

sys.path.append('.')
from ScriptEngine.messaging_helper import MessagingHelper
from utils.file_transfer_host_utils import os_normalize_path
from utils.script_status_utils import *

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

def initialize_script_object(script_object):
    start_time = datetime.datetime.now()
    start_time_str = start_time.strftime('%Y-%m-%d %H-%M-%S')
    script_log_folder = os_normalize_path(
        app.config['LOGFILE_FOLDER'] + '0'.zfill(5) + '-' + script_object['script_name'] + '-' + start_time_str + '\\'
    )
    os.makedirs(script_log_folder, exist_ok=True)
    timeout_val_split = script_object['script_duration'].split('h')
    end_time = start_time + datetime.timedelta(hours=int(timeout_val_split[0]),
                                               minutes=int(timeout_val_split[1][:-1]))
    end_time_str = end_time.strftime('%Y-%m-%d %H-%M-%S')
    script_object["start_time_str"] = start_time_str
    script_object["end_time_str"] = end_time_str
    script_object["script_log_folder"] = script_log_folder
    script_object["status"] = "started"
    persist_running_script(script_object, script_id=script_object["script_id"])
    return script_object

def create_script_object(
        script_id,
        scriptname,
        timeout_val,
        script_constants,
        log_level,
        notification_level,
        parallel
    ):

    return {
        "script_id" : script_id,
        "script_name": scriptname,
        "status": "pending",
        "script_duration" : timeout_val,
        "start_time_str" : None,
        "end_time_str" : None,
        "log_level" : log_level,
        "notification_level" : notification_level,
        "args" : script_constants,
        "parallel" : parallel,
        "script_log_folder" : None
    }


def run_in_thread(script_object):
    print(
        'running ',
        script_object['script_name'],
        'from',
        script_object['start_time_str'],
        'to',
        script_object['end_time_str'],
        'with constants',
        script_object['args']
    )
    with open(script_object['script_log_folder'] + 'stdout.txt', 'w') as log_file:
        print('args',
            (
                'venv\\Scripts\\python' if platform.system() == 'Windows' else
                'venv/bin/python3'
            ),
            os_normalize_path('ScriptEngine\\script_manager.py'),
            script_object["script_name"],
            script_object["start_time_str"],
            script_object["end_time_str"],
            script_object["log_level"],
            script_object["script_id"],
            *script_object["args"],
            script_object['script_log_folder'])

        shell_process = subprocess.Popen([
            (
                'venv\\Scripts\\python' if platform.system() == 'Windows' else
                'venv/bin/python3'
            ),
            os_normalize_path('ScriptEngine\\script_manager.py'),
            script_object["script_name"],
            script_object["start_time_str"],
            script_object["end_time_str"],
            script_object["log_level"],
            str(script_object["script_id"]),
            *script_object["args"]
        ],
            # shell=True,
            stdout=log_file,
            stderr=log_file,
            cwd=os.getcwd()
        )
        shell_process.wait()
    exit_code = shell_process.returncode
    print('completed ', script_object['script_name'], 'with return code', str(exit_code))
    with open(script_object['script_log_folder'] + 'completed.txt', 'w') as completed_file:
        completed_file.write(script_object['script_name'] + ' completed at ' + str(datetime.datetime.now()) + ' with return code ' + str(exit_code))
    if script_object['notification_level'] is not None:
        notify = (script_object['notification_level'] == 'info')
        notify = notify or ((
            script_object['notification_level'] == 'error'
        ) and (
                exit_code == 1 or
                exit_code == 478
        ))
        if notify:
            messaging_helper = MessagingHelper()
            messaging_helper.send_viber_message(script_object['script_name'] + ' completed with return code ' + str(exit_code))

    print('1', get_running_scripts())
    persist_running_script(None, script_id=script_object["script_id"])
    print('2', get_running_scripts())
    parse_running_scripts()
    print('3', get_running_scripts())

    return
def parse_running_scripts():
    running_scripts = get_running_scripts()
    if len(running_scripts) == 0:
        return
    current_running_script = running_scripts[0]
    if current_running_script["status"] == "pending":
        current_running_script = initialize_script_object(current_running_script)
        script_thread = threading.Thread(target=run_in_thread, args=(current_running_script,))
        script_thread.start()
    if current_running_script["parallel"]:
        for script_index,running_script in enumerate(running_scripts):
            if script_index == 0:
                continue
            if running_script["parallel"]:
                if running_script["status"] == "pending":
                    running_script = initialize_script_object(running_script)
                    script_thread = threading.Thread(target=run_in_thread, args=(running_script,))
                    script_thread.start()
                else:
                    continue
            else:
                break




@app.route('/run/<scriptname>', strict_slashes=False)
def run_script(scriptname):
    running_scripts = get_running_scripts()
    if 'queue' in request.args:
        queue_script = request.args.get('queue') == 'True'
    else:
        queue_script = False
    if len(running_scripts) == 0 or queue_script:
        if 'timeout' in request.args:
            timeout_val = request.args.get('timeout')
        else:
            timeout_val = '0h30m'
        if 'log_level' in request.args:
            log_level = request.args.get('log_level')
        else:
            log_level = 'info'

        if 'notification_level' in request.args:
            notification_level = request.args.get('notification_level')
        else:
            notification_level = None

        if 'parallel' in request.args:
            parallel = request.args.get('parallel') == 'True'
        else:
            parallel = False

        if 'args' in request.args:
            script_constants = request.args.getlist('args')
        else:
            script_constants = []
        print('script_constants ', script_constants)

        script_id = get_next_script_id()
        running_script_object = create_script_object(
            script_id,
            scriptname,
            timeout_val,
            script_constants,
            log_level,
            notification_level,
            parallel
        )
        persist_running_script(running_script_object)
        parse_running_scripts()
        script_object = get_script_object(script_id)
        # returns immediately after the thread starts
        if queue_script:
            return ('<p> Added ' + script_object['script_name'] + ' to queue. Now running : ' + str(get_running_scripts()) + '  </p>' + \
             COMPONENTS['DASHBOARD BUTTON'], 200)
        else:
            return ('<p>' + script_object['script_name'] + ' started! </p>' +\
                        '<a href="http://' + request.host.split(':')[0] + ':3848/logs/' + '0'.zfill(5) + '-' + script_object["script_name"] +\
                        '-' + script_object['start_time_str'] + '/"' + '> Click here for logs </a><br>' +\
                        '<a href="/capture"' + '> Click here to monitor </a><br>' +\
                        COMPONENTS['DASHBOARD BUTTON'] +\
                        '<a href="/reset_scripts"' + '> Click here to terminate </a><br>', 201)
    else:
        request_args = dict(request.args)
        if 'args' in request.args:
            script_constants = request.args.getlist('args')
        else:
            script_constants = []
        request_args['queue'] = 'True'
        request_args['args'] = script_constants
        queue_link = url_for('run_script', scriptname=scriptname, **request_args)
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
            return ('<p>Please wait for script completion, script: ' + running_script_file.read() + ' still running!</p>' +\
                    '<a href=' + queue_link +'> Click here to enqueue </a><br>' +\
                        '<a href=/reset_scripts> Click here to terminate </a><br>', 400)

@app.route('/queue', methods=['GET'], strict_slashes=False)
def show_queue():
    return (get_running_scripts(), 200)

def get_space_remaining():
    if app.config['PLATFORM'] == 'Windows':
        bytes_free = subprocess.check_output('dir|find "bytes free"', shell=True).decode('utf-8')
    else:
        bytes_free = 'Bytes free command unimplemented'
    bytes_free_split = bytes_free.split(' ')
    # print(bytes_free_split)
    # bytes_free_val = int(bytes_free_split[3])
    # bytes_free = str(round(bytes_free_val / 1000000000, 2)) + 'GB free'
    return '<p>' + bytes_free +'</p><br>'

def to_paragraph_blocks(input_str):
    input_str = input_str.replace(' ', '&nbsp;')
    return ''.join(list(map(lambda line: '<p>' + line + '</p>', input_str.split('\n'))))

@app.route('/dashboard', methods=['GET'], strict_slashes=False)
def show_dashboard():
    server_settings = get_server_settings()
    capture_img = "<a href=\"/capture\"/> <img style=\"width:100%;max-width:600px;\" src=\"/capture\"> </a><br>"
    running_scripts = get_running_scripts_status() + "<a href=\"/reset_script\"/> Clear Running Script </a>" +\
                      "<a href=\"/reset_scripts\"/> Clear All Scripts </a>" + '<br>'
    if server_settings['stop_event_processing']:
        running_events = '<p> Event processing paused </p><br>'
    else:
        running_events = to_paragraph_blocks(get_running_events_status()) + "<a href=\"/reset_event\"/> Clear Running Event </a>" + \
                          "<a href=\"/reset_events\"/> Clear All Events </a>" + '<br>'
    completed_events = to_paragraph_blocks(get_completed_events_status()) + "<a href=\"/reset_completed_events\"/> Clear Completed Events </a>" + '<br>'
    clear_all = "<a href=\"/reset\"/> Clear All </a>"  + '<br>'
    file_server = '<a href=\"http://' + request.host.split(':')[0] + ':3848/\"> File Server </a><br>'
    server_settings = "<a href=\"/settings\"/> Settings </a>"  + '<br>'
    space_remaining = get_space_remaining()
    runnable_scripts = get_runnable_scripts()
    return (capture_img + running_scripts + running_events + completed_events + clear_all + file_server + server_settings + space_remaining + runnable_scripts, 200)

@app.route('/settings', methods=['GET'], strict_slashes=False)
def show_settings():
    server_settings = get_server_settings()
    for key in server_settings.keys():
        if key in request.args:
            server_settings[key] = False if request.args.get(key) == 'False' else 'True'
    save_server_settings(server_settings)
    return_html = ''
    for key, value in server_settings.items():
        return_html += f"<p>{key}: {value} <a href='/settings?{key}={(not value)}'>Toggle</a></p>"
    return_html += COMPONENTS["DASHBOARD BUTTON"]
    return (return_html, 201)

def get_runnable_scripts():
    def buttonize(script_file):
        return "<li><a href=\"/run/" + script_file.split('.')[0] + "?timeout=0h30m\"/>" + script_file + "</a></li>"


    if platform.system() == 'Windows':
        try:
            script_files = subprocess.check_output([
               'dir',
               os.getcwd() + '\\scripts\\scriptFolders',
               '/b',
               '/a-d'] if platform.system() == 'Windows' else [
                'ls scripts/scriptFolders'
            ] if platform.system() == 'Darwin' else [

            ], shell=True
                                                   ).decode('utf-8')
        except subprocess.CalledProcessError as e:
            print(f"Error getting list of scripts {e}")
            script_files = ''
        script_files = script_files.split('\r\n')
    else:
        script_files = list(map(os.path.basename, glob.glob('./scripts/scriptFolders/*.zip')))
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
       os.getcwd() + '\\scripts\\logs',
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

def clear_running_script():
    running_scripts = []
    if os.path.exists(RUNNING_SCRIPTS_PATH):
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_scripts_file:
            running_scripts = json.load(running_scripts_file)
    if len(running_scripts) > 0:
        running_scripts = running_scripts[1:]
    if len(running_scripts) > 0:
        with open(RUNNING_SCRIPTS_PATH, 'w') as running_scripts_file:
            json.dump(running_scripts, running_scripts_file)
    elif os.path.exists(RUNNING_SCRIPTS_PATH):
        os.remove(RUNNING_SCRIPTS_PATH)

def clear_running_scripts():
    if os.path.exists(RUNNING_SCRIPTS_PATH):
        os.remove(RUNNING_SCRIPTS_PATH)

def clear_running_event():
    running_events = []
    if os.path.exists(RUNNING_EVENTS_PATH):
        with open(RUNNING_EVENTS_PATH, 'r') as running_events_file:
            running_events = json.load(running_events_file)
    if len(running_events) > 0:
        running_events = running_events[1:]
    with open(RUNNING_EVENTS_PATH, 'w') as running_events_file:
        json.dump(running_events, running_events_file)

def clear_running_events():
    if os.path.exists(RUNNING_EVENTS_PATH):
        os.remove(RUNNING_EVENTS_PATH)

def clear_completed_events():
    if os.path.exists(COMPLETED_EVENTS_PATH):
        os.remove(COMPLETED_EVENTS_PATH)

@app.route('/reset', methods=['GET'], strict_slashes=False)
def reset_all():
    clear_running_scripts()
    clear_running_events()
    clear_completed_events()
    return ('<p>cleared all temp files</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/reset_script', methods=['GET'], strict_slashes=False)
def reset_running_script():
    clear_running_script()
    return ('<p>running script cleared</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/reset_scripts', methods=['GET'], strict_slashes=False)
def reset_running_scripts():
    clear_running_scripts()
    return ('<p>running scripts cleared</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/reset_event', methods=['GET'], strict_slashes=False)
def reset_running_event():
    running_events = get_running_events()
    if len(running_events) > 0:
        print('reset events running _events: ', running_events)
        print('re[0]', running_events[0])
        update_completed_events(running_events[0])
        persist_event_status(running_events[0]["sequence_name"], None)
    return ('<p>running event cleared</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/reset_events', methods=['GET'], strict_slashes=False)
def reset_running_events():
    running_events = get_running_events()
    for running_event in running_events:
        update_completed_events(running_event)
    clear_running_events()
    return ('<p>running events cleared</p>' + \
            COMPONENTS["DASHBOARD BUTTON"], 201)

@app.route('/reset_completed_events', methods=['GET'], strict_slashes=False)
def reset_completed_events():
    clear_completed_events()
    return ('<p>completed events cleared</p>' + \
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
        if platform.system() == 'Darwin':
            pil_img = pil_img.convert('RGB')
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
