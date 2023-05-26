import sys
import random
import time
from dateutil import tz
import os
import json
import traceback


import datetime

sys.path.append("..")
from script_loader import parse_zip
from script_executor import ScriptExecutor
from script_engine_constants import *
from device_manager import DeviceManager

def str_timeout_to_datetime_timeout(timeout, src=None):
    if not isinstance(timeout, str):
        return timeout

    if src == 'deployment_server':
        timeout = datetime.datetime.strptime(timeout, "%Y-%m-%d %H-%M-%S")
    else:
        dt, _, us = timeout.partition(".")
        utc_tz = tz.gettz('UTC')
        is_utc = timeout[-1] == 'Z'
        timeout = datetime.datetime.strptime(timeout[:-1], "%Y-%m-%dT%H:%M:%S")
        if is_utc:
            timeout = timeout.replace(tzinfo=utc_tz).astimezone(tz.tzlocal())
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
            print('running_scripts ', running_scripts)
            if len(running_scripts) == 0:
                os.remove(RUNNING_SCRIPTS_PATH)
            else:
                with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
                    json.dump(running_scripts, running_script_file)

def load_and_run(script_name, script_id, timeout, constants=None, start_time=None, log_level='info'):
    # if you want to open zip then you pass .zip in command line args
    # update_running_scripts_file(script_name, 'push')
    print('SCRIPT_MANAGER: script start time: ', datetime.datetime.now(), ' script trigger time: ', start_time, ' scheduled end time: ', timeout)
    print('constants : ', constants)
    script_object = parse_zip(script_name)
    #https://stackoverflow.com/questions/28331512/how-to-convert-pythons-isoformat-string-back-into-datetime-objec
    # exit(0)
    adb_args = {}
    if 'DEVICE_NAME' in constants and 'AUTO_DETECT_ADB_PORT' in constants and constants['AUTO_DETECT_ADB_PORT'] == 'True':
        adb_args = {
            'DEVICE_NAME' : constants['DEVICE_NAME'],
            'AUTO_DETECT_ADB_PORT' : True
        }
    device_manager = DeviceManager(script_name, script_object['props'], adb_args)
    main_script = ScriptExecutor(
        script_object,
        timeout,
        script_name,
        start_time,
        script_id,
        device_manager,
        log_level=log_level,
        state=constants,
        start_time=start_time
    )
    try:
        main_script.run(log_level=log_level)
    except:
        traceback.print_exc()
    # print('completed script ', script_name, datetime.datetime.now())
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
        start_time = datetime.datetime.now()
        start_time_str = start_time.strftime('%Y-%m-%d %H-%M-%S')
    if n_args > 3:
        end_time = str_timeout_to_datetime_timeout(sys.argv[3], src='deployment_server').replace(tzinfo=tz.tzlocal())

    if n_args > 4:
        log_level = sys.argv[4]
    else:
        log_level = 'info'
    if n_args > 5:
        script_id = int(sys.argv[5])
    else:
        script_id = 1

    if n_args > 6:
        for arg_index in range(6, n_args):
            arg_split = sys.argv[arg_index].strip().split(':')
            constants[arg_split[0]] = arg_split[1]
    print('SCRIPT MANAGER: loading script and running with log level ', log_level)
    load_and_run(
        script_name,
        script_id,
        (start_time + datetime.timedelta(minutes=30)).replace(tzinfo=tz.tzlocal()) if end_time is None else end_time,
        start_time=start_time_str,
        constants=constants,
        log_level=log_level
    )