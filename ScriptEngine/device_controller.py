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

import argparse
import asyncio
import base64
import faulthandler
import importlib
import json
import sys
import datetime
import os
import threading
import time


from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from ScriptEngine.custom_thread_pool import CustomThreadPool
script_logger = ScriptLogger()
from typing import Dict
from ScriptEngine.managers.device_manager import DeviceManager
from ScriptEngine.managers.device_secrets_manager import DeviceSecretsManager
from ScriptEngine.common.script_engine_utils import DummyFile

from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter


from ScriptEngine.common.constants.script_engine_constants import DATA_ROOT, DEVICES_CONFIG_PATH, LOGS_FOLDER
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

# Global lock for response writing to prevent interleaving
response_lock = asyncio.Lock()

# Per-device locks to ensure only one thread per device at a time
device_locks: Dict[str, asyncio.Lock] = {}
device_locks_lock = asyncio.Lock()  # Lock for accessing device_locks dict


# Requests run in worker threads (asyncio.to_thread), so a device action that
# wedges leaves the event loop healthy and the process alive: the only symptom
# is that the response frame never reaches stdout and deviceinterface.mjs fails
# the command with a queue timeout minutes later. Dump every thread's stack once
# a request has been running this long, so the stuck frame ends up in the logs
# instead of being something to reproduce by hand.
STALL_DUMP_SECONDS = float(os.environ.get('SCREENPLAN_DEVICE_STALL_SECONDS', '30'))
stall_dump_lock = threading.Lock()


def get_stall_dump_path():
    return os.path.join(LOGS_FOLDER, '{}-device-controller-stalls.txt'.format(formatted_today))


def dump_stalled_request(request_id, inputs, started_at):
    """
    Write every thread's stack for a request that has not returned yet.

    The dump goes to a file of its own, never to stderr: deviceinterface.mjs
    rejects the in-flight request as soon as the child writes anything to
    stderr, so diagnostics sent there would break the request being diagnosed.
    """
    elapsed = time.monotonic() - started_at
    dump_path = get_stall_dump_path()
    try:
        with stall_dump_lock:
            with open(dump_path, 'a', encoding='utf-8') as dump_file:
                dump_file.write('\n===== {} request {} ({}) still running after {:.1f}s =====\n'.format(
                    datetime.datetime.now(), request_id, ' '.join(map(str, inputs[1:])), elapsed
                ))
                # faulthandler writes straight to the file descriptor, so the
                # buffered header has to be flushed first to keep the order.
                dump_file.flush()
                faulthandler.dump_traceback(file=dump_file, all_threads=True)
    except Exception as dump_error:
        script_logger.log('DEVICE CONTROLLER: could not write stall dump', dump_error, level='error')
        return
    script_logger.log(
        'DEVICE CONTROLLER: request {} still running after {:.1f}s, thread stacks written to {}'.format(
            request_id, elapsed, dump_path
        ),
        level='error'
    )


def start_stall_watchdog(request_id, inputs):
    """Arm a one-shot stall dump. The caller cancels the timer once the request returns."""
    watchdog = threading.Timer(
        STALL_DUMP_SECONDS, dump_stalled_request, args=(request_id, inputs, time.monotonic())
    )
    watchdog.daemon = True
    watchdog.start()
    return watchdog


def warm_request_path_imports():
    """
    Import what a device action needs here, on the main thread, before the event
    loop starts.

    parse_inputs runs inside asyncio.to_thread, so every module it imports lazily
    is imported from a worker thread the first time a command arrives. That
    includes scipy.stats, which ClickPathGenerator.generate_speed_path pulls in
    for every mouse move, and the desktop manager's own native stack. In the
    packaged (PyInstaller) build that first import did not return: a click logged
    its generated path and then nothing more, no response frame was ever written,
    and the controller failed the command on its queue timeout while the process
    itself stayed healthy. The same code run from the venv imports in well under a
    second. Doing the work here keeps it off the request path either way.
    """
    for module_name in ('scipy.stats', 'ScriptEngine.managers.desktop_device_manager'):
        started_at = time.monotonic()
        # Logged before as well as after: if a warm-up is what hangs, the last
        # line in the log names the module rather than leaving a process that
        # started and then never began listening.
        script_logger.log('DEVICE CONTROLLER: warming', module_name, level='debug')
        try:
            importlib.import_module(module_name)
        except Exception as import_error:
            # A host with no desktop stack still drives adb and kvm devices, so a
            # failed warm-up is worth reporting but not worth refusing to start over.
            script_logger.log('DEVICE CONTROLLER: could not warm', module_name, import_error, level='error')
        else:
            script_logger.log('DEVICE CONTROLLER: warmed {} in {:.2f}s'.format(
                module_name, time.monotonic() - started_at
            ), level='debug')


# Device types that drive something outside this host and therefore need a
# device attached to the run. 'python' is the host desktop itself, so it needs
# nothing attached.
DEVICE_TYPES_REQUIRING_ATTACHMENT = ('adb', 'kvm')


class DeviceController:
    def __init__(self, default_props, default_device_params, io_executor : CustomThreadPool, secrets_manager: DeviceSecretsManager, device_selection=None):
        script_logger.log('Intializing Device Manager')
        if 'script-engine-device-type' in default_device_params and default_device_params['script-engine-device-type'] == 'file':
            self.input_source = default_device_params
        else:
            self.input_source = None
        
        self.default_props = default_props
        self.default_device_params = default_device_params
        self.io_executor = io_executor
        self.secrets_manager = secrets_manager
        # What the run asked to attach ('--device'), kept only so a missing
        # device is reported in terms of the choice the caller made rather than
        # the empty params dict it produced. None when nothing was selected.
        self.device_selection = device_selection

        self.devices: Dict[str, DeviceManager] = {}

    def _require_attached_device(self, device_type):
        """Raises when an action needs a device but the run has none attached.

        Two ways to get here, and they need different fixes: the run named no
        device at all, or it named one that host_devices_config.json no longer
        holds. Both used to fall through to whichever device manager was
        constructed with empty params and surface as 'ADB HOST CONTROLLER: no
        adb args or input source provided' — a message that names neither the
        script's requirement nor the selection that was missing.
        """
        if self.default_device_params or self.input_source is not None:
            return
        if self.device_selection:
            raise Exception(
                'DEVICE CONTROLLER: this script has actions that require a device '
                "(target system '{}'), and the run was started with device '{}', but no "
                'configuration for that device exists in {}. Reconnect it on the controller, '
                'or attach a different device when starting the script.'.format(
                    device_type, self.device_selection, DEVICES_CONFIG_PATH
                )
            )
        raise Exception(
            'DEVICE CONTROLLER: this script has actions that require a device '
            "(target system '{}'), but no device was attached to the run. Attach a device "
            "when starting the script, or set those actions to target system 'none' if they "
            'do not need one.'.format(device_type)
        )

    def _resolve_device_params(self, device_id, device_type):
        """Config for an explicitly named device, or a message saying which one is gone.

        get_device_params logs and returns None for an id the config does not
        hold; the callers then subscripted that None. Same failure as an
        unattached run, reached from the interactive device controller instead.
        """
        params = self.get_device_params(device_id)
        if params is None:
            raise Exception(
                "DEVICE CONTROLLER: device '{}' was requested for a {} action, but no "
                'configuration for it exists in {}. Reconnect it on the controller, or '
                'pick a different device.'.format(device_id, device_type, DEVICES_CONFIG_PATH)
            )
        return params

    def initialize_device(self, device_type, device_params=None):
        if device_params is not None and device_params['deviceId'] in self.devices:
            return self.devices[device_params['deviceId']]
        elif device_type in self.devices:
            return self.devices[device_type]

        # Only the run-wide default can be missing; an explicit device_params
        # came from a caller that already resolved one.
        if device_params is None and device_type in DEVICE_TYPES_REQUIRING_ATTACHMENT:
            self._require_attached_device(device_type)

        if (device_type == 'python'):
            from ScriptEngine.managers.desktop_device_manager import DesktopDeviceManager
            if device_params is None:
                self.devices[device_type] = DesktopDeviceManager(self.default_props.copy(), self.input_source)
                return self.devices[device_type]
            else:
                self.devices[device_params['deviceId']] = DesktopDeviceManager(self.default_props.copy(), self.input_source)
                return self.devices[device_params['deviceId']]
        elif (device_type == 'adb'):
            from ScriptEngine.managers.adb_device_manager import ADBDeviceManager
            if device_params is None:
                self.devices[device_type] = ADBDeviceManager(self.default_props.copy(), self.default_device_params, self.input_source)
                return self.devices[device_type]
            else:
                device_params = self._resolve_device_params(device_params['deviceId'], device_type)
                self.devices[device_params['deviceId']] = ADBDeviceManager(self.default_props.copy(), device_params, self.input_source)
                return self.devices[device_params['deviceId']]
        elif (device_type == 'kvm'):
            from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager
            if device_params is None:
                password_name = self.default_device_params['passwordName']
                password = self.secrets_manager.get_secret(password_name)
                self.devices[device_type] = PiKVMDeviceManager(
                    self.default_device_params['ip'], 
                    self.default_device_params['username'], 
                    password,
                    self.input_source
                )
                return self.devices[device_type]
            else:
                device_params = self._resolve_device_params(device_params['deviceId'], device_type)
                password_name = device_params['passwordName']
                password = self.secrets_manager.get_secret(password_name)
                self.devices[device_params['deviceId']] = PiKVMDeviceManager(
                    device_params['ip'],
                    device_params['username'],
                    password,
                    self.input_source
                )
                return self.devices[device_params['deviceId']]
    
    def get_device_action(self, device_type, action_type, device_params=None):
        device = self.initialize_device(device_type, device_params)
        action_method_map = {
            'mouse_move': 'smooth_move'
        }
        method_name = action_method_map.get(action_type, action_type)
        return getattr(device, method_name)
    
    def ensure_device_initialized(self, device_type, device_params=None):
        device = self.initialize_device(device_type, device_params)
        device.ensure_device_initialized()
            
    
    def get_device_attribute(self, device_type, attribute_name, device_params=None):
        device = self.initialize_device(device_type, device_params)
        return getattr(device, attribute_name)
    
    def device_id_to_device_type(self, device_id):
        if ':' not in device_id:
            device_type = 'python'
        else:
            device_subtype = device_id.split(':')[0]
            if device_subtype == 'avd' or device_subtype == 'bluestacks' or device_subtype == 'adb':
                device_type = 'adb'
            elif device_subtype == 'pikvm':
                device_type = 'kvm'
        return device_type

    @staticmethod
    def get_device_params(device_key):
        params = None
        with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
            devices_config = json.load(devices_config_file)
            if device_key in devices_config:
                params = devices_config[device_key]
            else:
                script_logger.log('DEVICE CONTROLLER: device config for ', device_key, ' not found! ', level='error')
        script_logger.log('DEVICE CONTROLLER: loading args', params, level='debug')
        return params
    
    def parse_inputs(self, inputs):
        device_key = inputs[1]
        device_type = self.device_id_to_device_type(device_key)
        script_logger.log('DEVICE CONTROLLER: device type', device_type, device_key, level='debug')
        device_params = {
            'deviceId' : device_key
        }
        
        device_action = inputs[2]
        if device_action == 'check_status':
            status = self.get_device_action(device_type, 'get_status', device_params)()
            return {
                "data": status
            }
        elif device_action == 'screen_capture':
            screenshot = self.get_device_action(device_type, 'screenshot', device_params)()
            from cv2 import imencode
            _, buffer = imencode('.jpg', screenshot)
            byte_array = buffer.tobytes()
            base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
            return {
                "data": base64_encoded_string
            }
        elif device_action == "click":
            # process_adb_host.get_screen_orientation()
            self.get_device_action(device_type, 'click', device_params)(int(float(inputs[3])), int(float(inputs[4])), 'left')
            return {
                "data" : "success"
            }
        elif device_action == "click_and_drag":
            # process_adb_host.get_screen_orientation()
            self.get_device_action(device_type, 'click_and_drag', device_params)(
                int(float(inputs[3])), int(float(inputs[4])), int(float(inputs[5])), int(float(inputs[6]))
            )
            return {
                "data" : "success"
            }
        elif device_action == "send_keys":
            DeviceActionInterpreter.parse_keyboard_action(
                self, json.loads(inputs[3]), {}, {}, device_params
            )
            return {
                "data": "success"
            }
        elif device_action == "list_applications":
            applications = self.get_device_action(device_type, 'list_applications', device_params)()
            return {
                "data": applications
            }
        elif device_action == "start_application":
            self.get_device_action(device_type, 'start_application', device_params)(inputs[3], [])
            return {
                "data": "success"
            }
        elif device_action == "stop_application":
            self.get_device_action(device_type, 'stop_application', device_params)(inputs[3])
            return {
                "data": "success"
            }



async def get_device_lock(device_key: str) -> asyncio.Lock:
    """Get or create a lock for a specific device."""
    async with device_locks_lock:
        if device_key not in device_locks:
            device_locks[device_key] = asyncio.Lock()
        return device_locks[device_key]

async def process_input(device_controller: DeviceController, inputs: list):
    """Process a single input with per-device locking and global response locking."""
    device_key = inputs[1]
    request_id = inputs[0]
    
    # Get the lock for this specific device
    device_lock = await get_device_lock(device_key)
    
    # Wait for this device to be available (only one thread per device)
    async with device_lock:
        stall_watchdog = start_stall_watchdog(request_id, inputs)
        try:
            # Process the input in a thread pool (non-blocking for event loop)
            output = await asyncio.to_thread(device_controller.parse_inputs, inputs)
        except Exception as e:
            script_logger.log('DEVICE CONTROLLER: error in parse_inputs', inputs, e, level='error')
            output = {
                "data" : "device controller error"
            }
        finally:
            stall_watchdog.cancel()
        
        # Write response with global lock to prevent interleaving
        async with response_lock:
            input_response = json.dumps(output)
            script_logger.log('DEVICE CONTROLLER: Sending response for {}'.format(request_id), flush=True)
            script_logger.log('<--{}-->'.format(request_id) + input_response + '<--{}-->'.format(request_id), file=DummyFile(), flush=True)
            # script_logger.log('DEVICE CONTROLLER: response', input_response, flush=True)
            script_logger.log('DEVICE CONTROLLER: Response sent for {}'.format(request_id), flush=True)

async def read_input(device_controller: DeviceController):
    script_logger.log("DEVICE CONTROLLER PROCESS: listening for input")
    input_line = ''
    while True:
        input_line += await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = input_line.strip().split('###')
        if len(inputs) <= 2:
            script_logger.log('DEVICE CONTROLLER PROCESS: received partial inputs ', inputs, level='debug')
            continue
        inputs = inputs[0:2] + inputs[2].split(' ')
        input_line = ''
        script_logger.log('DEVICE CONTROLLER PROCESS: received inputs ', inputs, level='debug')
        if len(inputs) > 2:
            # Process input asynchronously (will queue per device automatically)
            asyncio.create_task(process_input(device_controller, inputs))

async def device_controller_main(device_controller: DeviceController):
    await asyncio.gather(read_input(device_controller))

def parse_args():
    parser = argparse.ArgumentParser(description='ScreenPlan device controller')
    parser.add_argument('--log-level', '-l', default='info', choices=['debug', 'info', 'error'],
                        help='Logging level, mirroring the Script-Engine-Controller that spawned '
                             'this process: debug = every log including the per-request input and '
                             'device-type traces; info = info/error only; error = errors only')
    # Declared so it shows in --help and is not reported as unrecognized. The
    # value itself is read from sys.argv by script_engine_constants at import
    # time, before this parser runs.
    parser.add_argument('--data-root',
                        help="Root of the controller's data folder (tmp/, logs/, certs/, scripts/). "
                             'Defaults to $SCREENPLAN_DATA_ROOT, then the per-user app data folder.')
    # parse_known_args, not parse_args: runStartDeviceController.bat/.sh forward
    # their arguments after `-m ScriptEngine.device_controller`, so a Python flag
    # meant for the interpreter (`-u`) arrives here as a script argument instead.
    # Refusing to start over a stray argument would be worse than ignoring it.
    return parser.parse_known_args()


if __name__ == '__main__':
    cli_args, unknown_args = parse_args()
    os.makedirs(LOGS_FOLDER, exist_ok=True)
    script_logger.set_log_level(cli_args.log_level)
    script_logger.set_log_file_path(os.path.join(LOGS_FOLDER, '{}-device-controller-main.txt'.format(formatted_today)))
    script_logger.set_log_header('{}-device-controller-main-'.format(formatted_today))
    script_logger.set_log_folder(LOGS_FOLDER + '/')
    script_logger.set_action_log(ScriptActionLog(
        {
            'actionName' : 'configurationAction',
            'actionGroup' : 0,
            'actionData' : {
                'targetSystem': 'python'
            }
        },
        script_logger.get_log_folder(),
        script_logger.get_log_header(),
        0
    ))
    script_logger.log('DEVICE CONTROLLER: starting at log level', cli_args.log_level)
    if unknown_args:
        script_logger.log('DEVICE CONTROLLER: ignoring unrecognized arguments', unknown_args, level='debug')
    warm_request_path_imports()
    with CustomThreadPool(max_workers=50) as io_executor:
        asyncio.run(device_controller_main(DeviceController({
            # No script folder of its own, so actions that resolve per-script
            # files (jsonFileAction's tmp/) land under the controller's data
            # root. This used to be "./", which meant the same thing only
            # because the data root was the working directory.
            "dir_path": DATA_ROOT,
            "width" : None,
            "height" : None,
            "scriptMode" : 'train'

        }, {}, io_executor, DeviceSecretsManager())))
        asyncio.run(io_executor.soft_shutdown(script_logger))
