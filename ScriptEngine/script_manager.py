import sys
import random
import time
from dateutil import tz
import os
import json
import traceback
import multiprocessing, logging
import uuid
import datetime

from script_loader import parse_zip
from script_executor import ScriptExecutor
from script_engine_constants import *
from device_manager import DeviceManager
from script_engine_utils import datetime_to_local_str
from system_script_handler import SystemScriptHandler
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

def load_and_run(script_name, script_id, timeout, constants=None, start_time_str=None, log_level='info', device_details=None, system_script=False):
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
    adb_args = {}
    if device_details is not None and device_details != '' and device_details != 'null':
        with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
            devices_config = json.load(devices_config_file)
            if device_details in devices_config:
                adb_args = devices_config[device_details]
            else:
                script_logger.log('SCRIPT MANAGER: device config for ', device_details, ' not found! ')
    elif 'DEVICE_NAME' in constants and 'AUTO_DETECT_ADB_PORT' in constants and constants['AUTO_DETECT_ADB_PORT'] == 'True':
        adb_args = {
            'DEVICE_NAME' : constants['DEVICE_NAME'],
            'AUTO_DETECT_ADB_PORT' : True
        }
        script_logger.log('SCRIPT MANAGER: setting params through inputs is deprecated ', adb_args)
    script_logger.log('SCRIPT MANAGER: loading adb_args', adb_args)
    device_manager = DeviceManager(script_name, script_object['props'], adb_args)
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(multiprocessing.SUBDEBUG)

    if system_script:
        handle_result = SystemScriptHandler.handle_system_script(device_manager, script_name, {})
        if handle_result == "return":
            return

    main_script = ScriptExecutor(
        script_object,
        timeout,
        script_name,
        start_time_str,
        script_id,
        device_manager,
        log_level=log_level,
        state=constants,
        script_start_time=start_time
    )
    try:
        main_script.run(log_level=log_level)
    except:
        traceback.print_exc()
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

    if n_args > 8:
        for arg_index in range(8, n_args):
            arg_split = sys.argv[arg_index].strip().split(':')
            constants[arg_split[0]] = arg_split[1]

    log_folder = './logs/' + str(0).zfill(5) + '-' +\
                 script_name + '-' + datetime_to_local_str(start_time, delim='-') + '/stdout.txt'
    script_logger.set_log_path(log_folder)
    script_logger.log('SCRIPT MANAGER: completed parsing args ', sys.argv)
    script_logger.log('SCRIPT MANAGER: loading script {} and running with log level {}'.format(script_name, log_level))
    load_and_run(
        script_name,
        script_id,
        timeout=(start_time + datetime.timedelta(minutes=30)).astimezone(tz=tz.tzutc()) if end_time is None else end_time,
        start_time_str=start_time_str,
        constants=constants,
        log_level=log_level,
        device_details=device_details,
        system_script=system_script
    )