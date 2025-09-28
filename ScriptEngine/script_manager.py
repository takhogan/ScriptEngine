# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import time

start_time = time.time()
import os
import asyncio


from dateutil import tz
import json
import traceback
import multiprocessing
import uuid
import datetime
import sys
print(f"builtin initialization took {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.custom_thread_pool import CustomThreadPool
from ScriptEngine.custom_process_pool import CustomProcessPool
from ScriptEngine.common.constants.script_engine_constants import *
from ScriptEngine.common.script_engine_utils import datetime_to_local_str, imageFileExtensions, StateEvaluator
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.system_script_handler import SystemScriptHandler
print(f"non builtin initialization took {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()

DEVICES_CONFIG_PATH = './assets/host_devices_config.json'
print(f"script logger initialization took {time.time() - start_time:.2f} seconds", flush=True)


def hot_swap(current_action_group, current_script, include_scripts, recovery_script=None):
    if recovery_script is not None:
        pass
    pass

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

async def close_threads_and_processes(io_executor, process_executor, timeout=30):
    await asyncio.gather(io_executor.soft_shutdown(script_logger, timeout), process_executor.soft_shutdown(script_logger, timeout))

def load_and_run(script_name, script_id, timeout, constants=None, start_time : datetime.datetime=None, start_time_str : str=None, device_details=None, system_script=False, screen_plan_server_attached=False):
    script_logger.log('SCRIPT_MANAGER: ', ' script trigger time: ',
          datetime_to_local_str(str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')),
          'actual script start time: ', datetime.datetime.now(), ' scheduled end time: ',
          datetime_to_local_str(timeout))
    script_logger.log('constants : ', constants)
    from ScriptEngine.script_loader import parse_zip
    script_object = parse_zip(script_name, system_script)
    device_params = {}
    if device_details is not None and device_details != '' and device_details != 'null':
        if device_details.startswith('file'):
            file_path = ''.join(device_details.split(':')[1:])
            file_type = os.path.splitext(file_path)[1]
            script_logger.log('SCRIPT MANAGER: loading input source', file_path, 'file exists', os.path.exists(file_path))
            import cv2
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
    from ScriptEngine.device_controller import DeviceController
    from ScriptEngine.script_executor import ScriptExecutor
    from ScriptEngine.engine_manager import EngineManager
    from ScriptEngine.script_action_executor import ScriptActionExecutor
    from ScriptEngine.parallelized_script_executor import ParallelizedScriptExecutor
    from ScriptEngine.managers.device_secrets_manager import DeviceSecretsManager
    with CustomThreadPool(max_workers=50) as io_executor, CustomProcessPool(max_workers=os.cpu_count()) as process_executor:
        secrets_manager = DeviceSecretsManager()
        device_controller = DeviceController(script_object['props'], device_params, io_executor, secrets_manager)
        engine_manager = EngineManager(script_id, script_logger.get_log_folder())
        script_action_executor = ScriptActionExecutor(device_controller, io_executor, script_object['props'], screen_plan_server_attached)
        parallelized_executor = ParallelizedScriptExecutor(device_controller, process_executor)
        # TODO: might need fixing
        # logger = multiprocessing.log_to_stderr()
        # logger.setLevel(multiprocessing.SUBDEBUG)

        base_script_object = script_object.copy()
        base_script_object['inputs'] = constants
        base_include_scripts = script_object['include']

        # action logger for the script running the scriptReference
        script_logger.configure_action_logger(script_object['props']['scriptReference'], 1, None)
        main_script = ScriptExecutor(
            base_script_object,
            base_include_scripts,
            timeout,
            script_name,
            start_time_str,
            script_id,
            device_controller,
            engine_manager,
            io_executor,
            script_action_executor,
            parallelized_executor,
            script_start_time=start_time,
            screen_plan_server_attached=screen_plan_server_attached
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
            if system_script:
                handle_result = SystemScriptHandler.handle_system_script(device_controller, script_name, {})
                if handle_result == "return":
                    script_logger.get_action_log().set_status(ScriptExecutionState.SUCCESS.name)
                else:
                    main_script.handle_action(
                        script_object['props']['scriptReference']
                    )
            else:
                main_script.handle_action(
                    script_object['props']['scriptReference']
                )
        except:
            script_logger.log('Script Execution interrupted by exception')
            asyncio.run(close_threads_and_processes(io_executor, process_executor))

            traceback.print_exc()
            errored = True
        else:
            script_logger.log('Script Execution completed')
            asyncio.run(close_threads_and_processes(io_executor, process_executor))
    script_logger.log('Script Manager process completed')
    if errored:
        sys.exit(1)
    # script_logger.log('completed script ', script_name, datetime.datetime.now())
    # update_running_scripts_file(script_name, 'pop')


print(f"Final Method initialization took {time.time() - start_time:.2f} seconds", flush=True)

def main():
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')
    print(f'SCRIPT MANAGER: Process ID: {os.getpid()}')
    print('SCRIPT MANAGER: parsing args ', sys.argv)
    import argparse
    parser = argparse.ArgumentParser(description='Script Manager CLI')
    
    # Required arguments
    parser.add_argument('--script-name', '-s', required=True, help='Name of the script to run')
    
    # Optional arguments
    parser.add_argument('--start-time', '-st', help='Script start time (format: YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end-time', '-et', help='Script end time (format: YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--log-level', '-l', default='info', help='Logging level')
    parser.add_argument('--script-id', '-id', help='Script ID (UUID)')
    parser.add_argument('--device', '-d', help='Device details')
    parser.add_argument('--system-script', '-sys', action='store_true', help='Whether this is a system script')
    parser.add_argument('--screen-plan-server-attached', '-spsa', action='store_true', help='Whether a screenplan client server is attached')
    parser.add_argument('--constants', '-c', nargs='*', help='Constants in format key:value')
    
    args = parser.parse_args()
    
    script_name = args.script_name
    
    if args.start_time:
        start_time_str = args.start_time
        start_time = str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')
    else:
        start_time = datetime.datetime.now(datetime.timezone.utc)
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
    
    end_time = str_timeout_to_datetime_timeout(args.end_time, src='deployment_server') if args.end_time else None
    log_level = args.log_level
    script_id = args.script_id if args.script_id else uuid.uuid4()
    device_details = None if (not args.device or args.device == '' or args.device == 'null') else args.device
    system_script = args.system_script
    
    constants = []
    if args.constants:
        for const in args.constants:
            key_value = const.strip().split(':')
            if len(key_value) == 2:
                constants.append([key_value[0], key_value[1], False])
    
    log_folder = './logs/' + str(0).zfill(5) + '-' +\
                 script_name + '-' + datetime_to_local_str(start_time, delim='-') + '/'
    print('log_folder', log_folder, start_time)
    os.makedirs(log_folder, exist_ok=True)

    script_logger.set_log_file_path(log_folder + 'global-stdout.txt')
    script_logger.set_log_folder(log_folder)
    script_logger.set_log_header('SCRIPT MANAGER')
    script_logger.set_log_path_prefix(script_logger.get_log_folder() + script_logger.get_log_header() + '-')

    script_logger.set_log_level(log_level)
    script_logger.log('completed parsing args ', sys.argv)
    script_logger.log('loading script {} and running with log level {}'.format(
        script_name, script_logger.get_log_level())
    )
    script_timeout = (start_time + datetime.timedelta(minutes=30)).astimezone(tz=tz.tzutc()) if end_time is None else end_time

    StateEvaluator.configure_script_context(
        script_name=script_name,
        script_id=str(script_id),
        timeout=script_timeout,
        script_start_time=start_time,
        device_details=device_details,
    )

    load_and_run(
        script_name,
        script_id,
        timeout=script_timeout,
        start_time=start_time,
        start_time_str=start_time_str,
        constants=constants,
        device_details=device_details,
        system_script=system_script,
        screen_plan_server_attached=args.screen_plan_server_attached
    )

if __name__ == '__main__':
    main()
