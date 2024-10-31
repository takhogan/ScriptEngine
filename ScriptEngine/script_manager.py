import sys
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor

from contextlib import redirect_stderr
from dateutil import tz
import os
import cv2
import json
import traceback
import multiprocessing, logging
import uuid
import datetime
import sys
import warnings

from parallelized_script_executor import ParallelizedScriptExecutor
from script_loader import parse_zip
from script_executor import ScriptExecutor
from script_engine_constants import *
from device_manager import DeviceManager
from script_engine_utils import datetime_to_local_str, imageFileExtensions
from system_script_handler import SystemScriptHandler
from script_log_preview_generator import ScriptLogPreviewGenerator
from script_logger import ScriptLogger
script_logger = ScriptLogger()

DEVICES_CONFIG_PATH = './assets/host_devices_config.json'

def str_timeout_to_datetime_timeout(timeout, src=None):
    if not isinstance(timeout, str):
        return timeout
    if src == 'deployment_server':
        timeout = datetime.datetime.strptime(timeout, "%Y-%m-%d %H:%M:%S")
        timeout = timeout.replace(tzinfo=tz.tzutc())
    else:
        dt, _, us = timeout.partition(".")
        utc_tz = tz.gettz('UTC')
        timeout = datetime.datetime.strptime(timeout[:-1], "%Y-%m-%dT%H:%M:%S")
        timeout = timeout.replace(tzinfo=tz.tzutc())

    return timeout


def update_running_scripts_file(scriptname, action):
    if action == 'push':
        running_scripts = []
        if not os.path.exists(RUNNING_SCRIPTS_PATH):
            with open(RUNNING_SCRIPTS_PATH, 'w') as running_scripts_file:
                json.dump(running_scripts, running_scripts_file)
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
            running_scripts = json.load(running_script_file)
            if len(running_scripts) == 0 or running_scripts[0] != scriptname:
                running_scripts.append(scriptname)
        with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
            json.dump(running_scripts, running_script_file)
    elif action == 'pop':
        if not os.path.exists(RUNNING_SCRIPTS_PATH):
            return
        else:
            running_scripts = []
            with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                running_scripts = json.load(running_script_file)
                running_scripts.pop(0)
            script_logger.log('running_scripts ', running_scripts)
            if len(running_scripts) == 0:
                os.remove(RUNNING_SCRIPTS_PATH)
            else:
                with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
                    json.dump(running_scripts, running_script_file)

def load_and_run(script_name, script_id, timeout, constants=None, start_time_str=None, device_details=None, system_script=False):
    # if you want to open zip then you pass .zip in command line args
    # update_running_scripts_file(script_name, 'push')
    script_logger.log('SCRIPT_MANAGER: ', ' script trigger time: ',
          datetime_to_local_str(str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')),
          'actual script start time: ', datetime.datetime.now(), ' scheduled end time: ',
          datetime_to_local_str(timeout))
    script_logger.log('constants : ', constants)
    script_object = parse_zip(script_name, system_script)
    #https://stackoverflow.com/questions/28331512/how-to-convert-pythons-isoformat-string-back-into-datetime-objec
    # exit(0)
    device_params = {}
    if device_details is not None and device_details != '' and device_details != 'null':
        if device_details.startswith('file'):
            file_path = ''.join(device_details.split(':')[1:])
            file_type = os.path.splitext(file_path)[1]
            script_logger.log('SCRIPT MANAGER: loading input source', file_path, 'file exists', os.path.exists(file_path))
            if file_type[1:] in imageFileExtensions:
                input_img = cv2.imread(file_path)
                height,width,_ = input_img.shape
                device_params = {
                    'script-engine-device-type': 'file',
                    'screenshot' : lambda: input_img,
                    'width' : width,
                    'height' : height,
                }
            else:
                raise Exception('file type not supported "' + file_type + '"')
        else:
            with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
                devices_config = json.load(devices_config_file)
                if device_details in devices_config:
                    device_params = devices_config[device_details]
                    device_params['script-engine-device-type'] = 'bluestacks'
                else:
                    script_logger.log('SCRIPT MANAGER: device config for ', device_details, ' not found! ')
    script_logger.log('SCRIPT MANAGER: loading adb_args', device_params)
    errored = False
    multiprocessing.set_start_method('spawn')

    with ThreadPoolExecutor(max_workers=50) as io_executor, ProcessPoolExecutor(max_workers=os.cpu_count()) as process_executor:
        device_manager = DeviceManager(script_name, script_object['props'], device_params, io_executor)

        # TODO: might need fixing
        # logger = multiprocessing.log_to_stderr()
        # logger.setLevel(multiprocessing.SUBDEBUG)

        if system_script:
            handle_result = SystemScriptHandler.handle_system_script(device_manager, script_name, {})
            if handle_result == "return":
                return

        base_script_object = script_object.copy()
        base_script_object['inputs'] = constants

        # action logger for the script running the scriptReference
        script_logger.configure_action_logger(script_object['props']['scriptReference'], 1, None)
        main_script = ScriptExecutor(
            base_script_object,
            timeout,
            script_name,
            start_time_str,
            script_id,
            device_manager,
            process_executor,
            script_start_time=start_time
        )

        try:
            main_script.parse_inputs({})
            # action logger for the scriptReference
            main_script.context["script_counter"] += 1
            script_logger.configure_action_logger(
                script_object['props']['scriptReference'],
                main_script.context["script_counter"],
                script_logger.get_action_log()
            )
            script_logger.get_action_log().add_supporting_file_reference('text', 'global-stdout.txt', log_header=False)
            main_script.handle_action(
                script_object['props']['scriptReference']
            )
        except:
            io_executor.shutdown(wait=True)
            traceback.print_exc()
            errored = True
        else:
            io_executor.shutdown(wait=True)

        sys.stderr.write("<--IGNORE-OPENCV-VIDEO-ENCODING-SCRIPT-ENGINE-ERRORS-->")
        sys.stderr.flush()
        with redirect_stderr(sys.stdout):
            ScriptLogPreviewGenerator.assemble_script_log_preview(
                main_script.script_action_log.get_action_log_path(),
                main_script.log_folder + 'script-log-preview'
            )
            main_script.script_action_log.add_supporting_file_reference(
                'video', 'script-log-preview.mp4', log_header=False
            )
    if errored:
        exit(1)
    # script_logger.log('completed script ', script_name, datetime.datetime.now())
    # update_running_scripts_file(script_name, 'pop')



if __name__=='__main__':
    print('SCRIPT MANAGER: parsing args ', sys.argv)
    script_name = sys.argv[1]
    start_time = None
    end_time = None
    n_args = len(sys.argv)
    constants = {}
    if n_args > 2:
        start_time_str = sys.argv[2]
        start_time = str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')
    else:
        start_time = datetime.datetime.now(datetime.timezone.utc)
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
    if n_args > 3:
        end_time = str_timeout_to_datetime_timeout(sys.argv[3], src='deployment_server')

    if n_args > 4:
        log_level = sys.argv[4]
    else:
        log_level = 'info'
    if n_args > 5:
        script_id = sys.argv[5]
    else:
        script_id = uuid.uuid4()

    if n_args > 6:
        device_details = None if (sys.argv[6] == '' or sys.argv[6] == 'null') else sys.argv[6]
    else:
        device_details = None

    if n_args > 7:
        system_script = (sys.argv[7] if isinstance(sys.argv[7], bool) else sys.argv[7] == 'true')
    else:
        system_script = False

    constants = []
    args_index = 8
    if n_args > args_index:
        for arg_index in range(args_index, n_args):
            arg_split = sys.argv[arg_index].strip().split(':')
            constants.append([arg_split[0], arg_split[1], False])

    log_folder = './logs/' + str(0).zfill(5) + '-' +\
                 script_name + '-' + datetime_to_local_str(start_time, delim='-') + '/'
    script_logger.set_log_file_path(log_folder + 'global-stdout.txt')
    script_logger.set_log_folder(log_folder)
    script_logger.set_log_header('SCRIPT MANAGER')
    script_logger.set_log_path_prefix(script_logger.get_log_folder() + script_logger.get_log_header() + '-')

    script_logger.set_log_level(log_level)
    script_logger.log('completed parsing args ', sys.argv)
    script_logger.log('loading script {} and running with log level {}'.format(
        script_name, script_logger.get_log_level())
    )
    load_and_run(
        script_name,
        script_id,
        timeout=(start_time + datetime.timedelta(minutes=30)).astimezone(tz=tz.tzutc()) if end_time is None else end_time,
        start_time_str=start_time_str,
        constants=constants,
        device_details=device_details,
        system_script=system_script
    )