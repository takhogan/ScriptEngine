

import threading
import datetime
import queue
import subprocess
import os
import platform
import re




from configobj import ConfigObj 
from PIL import Image
from PIL import UnidentifiedImageError
from io import BytesIO
import cv2
import numpy as np
import random
import time
import sys
import struct
from ScriptEngine.common.script_engine_utils import is_null, state_eval, DummyFile
import pyautogui 
from .device_manager import DeviceManager
from ..helpers.device_action_interpreter import DeviceActionInterpreter
from ..helpers.click_path_generator import ClickPathGenerator
from ..helpers.search_pattern_helper import SearchPatternHelper
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.logging.script_action_log import ScriptActionLog


KEYBOARD_KEYS = set(pyautogui.KEYBOARD_KEYS)
KEY_TO_KEYCODE = {
    "a": "KEYCODE_A",
    "b": "KEYCODE_B",
    "c": "KEYCODE_C",
    "d": "KEYCODE_D",
    "e": "KEYCODE_E",
    "f": "KEYCODE_F",
    "g": "KEYCODE_G",
    "h": "KEYCODE_H",
    "i": "KEYCODE_I",
    "j": "KEYCODE_J",
    "k": "KEYCODE_K",
    "l": "KEYCODE_L",
    "m": "KEYCODE_M",
    "n": "KEYCODE_N",
    "o": "KEYCODE_O",
    "p": "KEYCODE_P",
    "q": "KEYCODE_Q",
    "r": "KEYCODE_R",
    "s": "KEYCODE_S",
    "t": "KEYCODE_T",
    "u": "KEYCODE_U",
    "v": "KEYCODE_V",
    "w": "KEYCODE_W",
    "x": "KEYCODE_X",
    "y": "KEYCODE_Y",
    "z": "KEYCODE_Z",
    "0": "KEYCODE_0",
    "1": "KEYCODE_1",
    "2": "KEYCODE_2",
    "3": "KEYCODE_3",
    "4": "KEYCODE_4",
    "5": "KEYCODE_5",
    "6": "KEYCODE_6",
    "7": "KEYCODE_7",
    "8": "KEYCODE_8",
    "9": "KEYCODE_9",
    "alt": "KEYCODE_ALT_LEFT",
    "altleft": "KEYCODE_ALT_LEFT",
    "altright": "KEYCODE_ALT_RIGHT",
    "backspace": "KEYCODE_DEL",
    "capslock": "KEYCODE_CAPS_LOCK",
    "ctrl": "KEYCODE_CTRL_LEFT",
    "ctrlleft": "KEYCODE_CTRL_LEFT",
    "ctrlright": "KEYCODE_CTRL_RIGHT",
    "delete": "KEYCODE_DEL",
    "down": "KEYCODE_DPAD_DOWN",
    "end": "KEYCODE_MOVE_END",
    "enter": "KEYCODE_ENTER",
    "esc": "KEYCODE_ESCAPE",
    "f1": "KEYCODE_F1",
    "f2": "KEYCODE_F2",
    "f3": "KEYCODE_F3",
    "f4": "KEYCODE_F4",
    "f5": "KEYCODE_F5",
    "f6": "KEYCODE_F6",
    "f7": "KEYCODE_F7",
    "f8": "KEYCODE_F8",
    "f9": "KEYCODE_F9",
    "f10": "KEYCODE_F10",
    "f11": "KEYCODE_F11",
    "f12": "KEYCODE_F12",
    "home": "KEYCODE_MOVE_HOME",
    "insert": "KEYCODE_INSERT",
    "left": "KEYCODE_DPAD_LEFT",
    "menu": "KEYCODE_MENU",
    "numlock": "KEYCODE_NUM_LOCK",
    "pageup": "KEYCODE_PAGE_UP",
    "pagedown": "KEYCODE_PAGE_DOWN",
    "pause": "KEYCODE_MEDIA_PAUSE",
    "printscreen": "KEYCODE_SYSRQ",
    "right": "KEYCODE_DPAD_RIGHT",
    "scrolllock": "KEYCODE_SCROLL_LOCK",
    "shift": "KEYCODE_SHIFT",
    "shiftleft": "KEYCODE_SHIFT_LEFT",
    "shiftright": "KEYCODE_SHIFT_RIGHT",
    "space": "KEYCODE_SPACE",
    "tab": "KEYCODE_TAB",
    "up": "KEYCODE_DPAD_UP"
}

from ScriptEngine.common.logging.script_logger import ScriptLogger,thread_local_storage
script_logger = ScriptLogger()


class ADBDeviceManager(DeviceManager):
    def __init__(self, props, adb_args, input_source=None):
        script_logger.log('Configuring ADB with adb_args', adb_args)
        self.stop_command_gather = False
        self.search_pattern_helper = SearchPatternHelper()
        self.status = 'uninitialized'
        self.props = props
        self.adb_ip = '127.0.0.1'
        self.width = None
        self.height = None
        self.xmax = 32726
        self.ymax = 32726
        self.click_path_generator = ClickPathGenerator(41.0, 71.0, self.xmax, self.ymax, 45, 0.4)
        self.image_stitch_calculator_path = './build/ImageStitchCalculator.exe'
        self.event_counter = 1

        #TODO CORRECT ABOVE
        self.distances_dist = {

        }
        # set device here
        # script_logger.log(self.adb_path)
        # shell_process = subprocess.Popen([self.adb_path, 'shell'],stdin=subprocess.PIPE)
        # device_name = shell_process.communicate(b"getevent -pl 2>&1 | sed -n '/^add/{h}/ABS_MT_TOUCH/{x;s/[^/]*//p}'")
        self.props['scriptMode'] = 'train'
        self.emulator_type = None
        self.adb_path = None
        self.emulator_path = None
        self.device_name = None
        self.window_name = None
        self.auto_detect_adb_port = None
        self.adb_port = None
        self.full_ip = None
        self.screen_orientation = None

        if input_source is not None:
            self.dummy_mode = True
            self.input_source = input_source
            self.width = input_source["width"]
            self.height = input_source["height"]
        else:
            self.dummy_mode = False

        if len(adb_args) == 0 and input_source is None:
            raise Exception('ADB HOST CONTROLLER: no adb args or input source provided')

        try:
            status, _, _ = self.configure_adb({
                'actionData' : {
                    'adbPath' : adb_args['adbPath'] if 'adbPath' in adb_args else None,
                    'emulatorType' : '"' + adb_args['type'] + '"',
                    'emulatorPath' : adb_args['emulatorPath'] if 'emulatorPath' in adb_args else None,
                    'deviceName' : '"' + adb_args['deviceName'] + '"',
                    'windowName' : '"' + adb_args['name'] + '"',
                    'adbPort' : '"' + adb_args['port'] + '"'
                }
            }, {}, {})
        except Exception as e:
            script_logger.log('ADB HOST CONTROLLER: exception', e)
            status = ScriptExecutionState.FAILURE
        if status == ScriptExecutionState.FAILURE:
            script_logger.log('ADB HOST CONTROLLER: adb configuration failed')
            raise Exception('ADB configuration failed')
    
    def configure_adb(self, configurationAction, state, context):
        emulator_type = state_eval(configurationAction['actionData']['emulatorType'], {}, state)
        self.emulator_type = emulator_type
        state['EMULATOR_TYPE'] = emulator_type
        script_logger.log('configuring emulator of type', self.emulator_type)

        if configurationAction['actionData']["emulatorPath"] is not None:
            emulator_path = state_eval(configurationAction['actionData']["emulatorPath"], {}, state)
        else:
            if self.emulator_type == 'bluestacks':
                emulator_path = 'C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe'
            elif self.emulator_type == 'avd':
                os_name = platform.system()
                if os_name == 'Windows':
                    user_home = os.path.expandvars(r'%LOCALAPPDATA%')
                    emulator_path = os.path.join(user_home, 'Android', 'Sdk', 'emulator', 'emulator.exe')
                elif os_name == 'Darwin':
                    user_home = os.path.expanduser("~")
                    emulator_path = os.path.join(user_home, 'Library/Android/sdk/emulator/')
                elif os_name == 'Linux':
                    user_home = os.path.expanduser("~")
                    emulator_path = os.path.join(user_home, 'Android/Sdk/emulator/emulator')
                else:
                    raise Exception(f"Unsupported OS: {os_name}")
            else:
                raise Exception(f"Unsupported emulator type: {self.emulator_type}")
        self.emulator_path = emulator_path
        state['EMULATOR_PATH'] = emulator_path
        script_logger.log('using emulator path', self.emulator_path)

        if configurationAction['actionData']["adbPath"] is not None:
            adb_path = state_eval(configurationAction['actionData']["adbPath"], {}, state)
            script_logger.log(f"loading adb path from adb args {adb_path}")
            self.adb_path = adb_path
        else:
            adb_path = None
            os_name = platform.system()
            try:
                if os_name == "Windows":
                    result = subprocess.run(["where", "adb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    result = subprocess.run(["which", "adb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                if result.returncode == 0:
                    adb_path = result.stdout.decode().strip()
                    script_logger.log(f"adb found in path at location: {adb_path}")
                else:
                    script_logger.log("adb not found in PATH")
            except Exception as e:
                script_logger.log("adb not found in PATH", e)
                pass
            if adb_path is not None:
                self.adb_path = adb_path
            else:
                if os_name == 'Windows':
                    # On Windows, use the AppData path for Android SDK
                    user_home = os.path.expandvars(r'%LOCALAPPDATA%')
                    adb_path = os.path.join(user_home, 'Android', 'Sdk', 'platform-tools', 'adb.exe')
                elif os_name == 'Darwin':
                    # macOS
                    user_home = os.path.expanduser("~")
                    adb_path = os.path.join(user_home, 'Library/Android/sdk/platform-tools/adb')
                elif os_name == 'Linux':
                    # Linux
                    user_home = os.path.expanduser("~")
                    adb_path = os.path.join(user_home, 'Android/Sdk/platform-tools/adb')
                else:
                    raise Exception(f"Unsupported OS: {os_name}")
                if os.path.exists(adb_path):
                    script_logger.log(f'configuring adb path, found adb at location {adb_path}')
                else:
                    raise Exception('Failed to find adb command path')
                self.adb_path = adb_path

        state['ADB_PATH'] = self.adb_path

        device_name = state_eval(configurationAction['actionData']["deviceName"], {}, state)
        self.device_name = device_name
        state['DEVICE_NAME'] = device_name

        if self.emulator_type == 'bluestacks':
            init_bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
            instance_window_name = init_bluestacks_config['bst.instance.{}.display_name'.format(
                self.device_name
            )]
            script_logger.log('ADB CONTROLLER: detected window name {} for device {}'.format(
                instance_window_name,
                self.device_name
            ))
            self.window_name = instance_window_name
            state['WINDOW_NAME'] = instance_window_name
        else:
            self.window_name = state_eval(configurationAction['actionData']["windowName"], {}, state)
        self.adb_port = str(state_eval(configurationAction['actionData']['adbPort'], {}, state))
        self.auto_detect_adb_port = (self.adb_port == 'auto')
        self.detect_adb_port()
        state['ADB_PORT'] = self.adb_port
        state['AUTO_DETECT_ADB_PORT'] = self.auto_detect_adb_port

        self.status = 'initialized'
        script_logger.log('Configured ADB: ',
              'adb_path', self.adb_path,
              'emulator_path', self.emulator_path,
              'device_name', self.device_name,
              'window_name', self.window_name,
              'adb_port', self.adb_port,
              'auto_detect_adb_port', self.auto_detect_adb_port,
              'full_ip', self.full_ip
        )
        return ScriptExecutionState.SUCCESS, state, context

    def get_device_name_to_emulator_name_mapping(self):
        script_logger = ScriptLogger.get_logger()
        device_list = self.get_device_list_output()
        script_logger.log('device_list', device_list)
        devices = {}

        for line in device_list:  # Skip the first line (header)
            if line.strip() and 'device' in line:
                device_id = line.split('\t')[0]
                if device_id.startswith('emulator'):
                    result = subprocess.run([self.adb_path, '-s', device_id, 'emu', 'avd', 'name'],
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                            text=True)
                    if result.returncode == 0:
                        result = result.stdout.split('\n')[0]
                        script_logger.log('device name matched', result)
                        devices[result] = device_id
                    else:
                        script_logger.log('device name fetch failed: ', result)
        return devices

    def detect_adb_port(self):
        script_logger = ScriptLogger.get_logger()
        og_port = self.adb_port
        if not self.auto_detect_adb_port:
            self.full_ip = self.adb_ip + ':' + self.adb_port
            return

        if self.emulator_type == 'bluestacks':
            bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
            self.adb_port = bluestacks_config['bst.instance.{}.status.adb_port'.format(
                self.device_name
            )]
            self.full_ip = self.adb_ip + ':' + self.adb_port
        elif self.emulator_type == 'avd':
            devices = self.get_device_name_to_emulator_name_mapping()
            if self.device_name in devices:
                script_logger.log('ADB CONTROLLER: found device name {} in mapping, updating full_ip'.format(self.device_name))
                self.full_ip = devices[self.device_name]
                self.adb_port = self.full_ip.split('-')[1]
            else:
                self.full_ip = self.adb_ip + ':' + self.adb_port
        else:
            raise Exception('Unsupported emulator type: ' + self.emulator_type)
        if self.adb_port != 'auto':
            script_logger.log('ADB CONTROLLER: changed adb port from {} to auto detected port {} full ip updated to {}'.format(
                og_port,
                self.adb_port,
                self.full_ip
            ))
        else:
            script_logger.log('ADB CONTROLLER: unable to detect adb port for ' + self.device_name)





    def start_device(self):
        # check if window is open
        if self.emulator_type == 'bluestacks':
            start_device_command = '"{}" --instance "{}"'.format(
                self.emulator_path,
                self.device_name
            )
            start_device_process = subprocess.Popen(
                [self.emulator_path, '--instance', self.device_name],
                cwd="/",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        elif self.emulator_type == 'avd':
            start_device_command = '"{}" -avd "{}"'.format(self.emulator_path, self.device_name)
            # Start the emulator using subprocess.Popen
            os_name = platform.system()
            if os_name == 'Windows':
                DETACHED_PROCESS = 0x00000008
                start_device_process = subprocess.Popen(
                    start_device_command,
                    cwd="/",  # You can change this to the actual working directory if needed
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=DETACHED_PROCESS
                )
            elif os_name == 'Darwin' or os_name == 'Linux':
                start_device_process = subprocess.Popen(
                    ['./emulator', '-avd', self.device_name],
                    cwd=self.emulator_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )
            else:
                raise Exception('Unsupported OS ' + os_name)
            timeout = 120
            start_time = time.time()
            while True:
                output = start_device_process.stdout.readline().decode().strip().lower()  # Read the output line-by-line
                if output:
                    script_logger.log(output)  # Optionally print each line for logging purposes

                if "boot completed" in output or "successfully loaded snapshot" in output:
                    script_logger.log("Emulator started successfully!")
                    break

                if time.time() - start_time > timeout:
                    print("Emulator start timed out.")
                    break

                # Check if the process has exited (i.e., poll() returns a non-None value)
                if start_device_process.poll() is not None:
                    script_logger.log("Emulator process exited prematurely.")
                    break
        else:
            script_logger.log('ADB CONTROLLER: emulator type ', self.emulator_type, ' not supported')
            return
        script_logger.log(
            'ADB CONTROLLER: started device',
            self.device_name, 'with command',
            start_device_command,
            'PID:', start_device_process.pid
        )

    def stop_device(self):
        if self.emulator_type == 'bluestacks':
            if platform.system() == 'Windows':
                self.detect_adb_port()
                init_bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
                instance_window_name = init_bluestacks_config['bst.instance.{}.display_name'.format(
                    self.device_name
                )]

                script_logger.log('ADB CONTROLLER: detected window name {} for device {}'.format(
                    instance_window_name,
                    self.device_name
                ))
                self.window_name = instance_window_name
                stop_device_command = 'taskkill /fi "WINDOWTITLE eq {}" /IM "HD-Player.exe" /F'.format(
                    self.window_name
                )
                script_logger.log('ADB CONTROLLER: stopping device', self.device_name, 'with command', stop_device_command)

                stop_device_process = subprocess.run(
                    stop_device_command,
                    cwd="/",
                    shell=True,
                    capture_output=True,
                    timeout=15
                )

                stop_device_command = 'adb -s emulator-{} emu kill'.format(
                    self.adb_port
                )

                script_logger.log('ADB CONTROLLER: stopping adb instance', self.device_name, 'with command', stop_device_command)

                stop_device_process = subprocess.run(
                    stop_device_command,
                    cwd="/",
                    shell=True,
                    capture_output=True,
                    timeout=15
                )
            else:
                raise Exception('OS and emulator type combination not supported ' + platform.system() + '-' + self.emulator_type)
        elif self.emulator_type == 'avd':
            devices = self.get_device_name_to_emulator_name_mapping()
            if self.device_name in devices:
                self.full_ip = devices[self.device_name]
                stop_device_command = 'adb -s {} emu kill'.format(
                    self.full_ip
                )
                stop_device_process = subprocess.run(
                    stop_device_command,
                    cwd="/",
                    shell=True,
                    capture_output=True,
                    timeout=15
                )
            else:
                raise Exception('unable to run command, device not active' + self.device_name)
        else:
            raise Exception('ADB CONTROLLER: emulator type ' + self.emulator_type + ' not supported')
        script_logger.log(
            'ADB CONTROLLER: stopped device',
            self.device_name,
            'with command',
            stop_device_command,
            'with result',
            stop_device_process.returncode,
            stop_device_process
        )

    def get_status(self):
        if self.adb_port == 'auto':
            self.detect_adb_port()
        devices_output = self.get_device_list_output()

        if not any(self.full_ip in device_line for device_line in devices_output):
            self.run_disconnect_command()
            self.run_connect_command()
            time.sleep(3)
            devices_output = self.get_device_list_output()

        emulator_active = any((
            self.full_ip in devices_output_line and 'offline' not in devices_output_line
        ) for devices_output_line in devices_output)
        if emulator_active:
            return 'online'
        else:
            return 'offline'

    def get_screen_orientation(self):
        script_logger = ScriptLogger.get_logger()
        shell_process = subprocess.Popen([
            self.adb_path,
            '-s',
            self.full_ip,
            'shell'
        ], stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        output,err = shell_process.communicate("dumpsys input | grep 'SurfaceOrientation'".encode('utf-8'))
        surface_orientation_text = bytes.decode(output, 'utf-8')
        surface_orientation_match = re.search(r'\d+', surface_orientation_text)

        if surface_orientation_match:
            surface_orientation = int(surface_orientation_match.group(0))
            script_logger.log('screen_orientation', surface_orientation)
        else:
            surface_orientation = 0
            script_logger.log('Error: surface orientation not found, setting to 0')

        self.screen_orientation = surface_orientation
        return self.screen_orientation

    def run_kill_command(self):
        return subprocess.run(self.adb_path + ' kill-server', cwd="/", shell=True, timeout=15)

    def run_start_command(self):
        return subprocess.run(self.adb_path + ' start-server', cwd="/", shell=True, timeout=15)


    def restart_adb(self):
        script_logger = ScriptLogger.get_logger()
        script_logger.log('ADB CONTROLLER restarting adb server')
        self.run_kill_command()
        self.run_start_command()
        time.sleep(3)
        self.detect_adb_port()
        script_logger.log('ADB CONTROLLER: connecting to adb device')
        self.run_disconnect_command()
        self.run_connect_command()
        time.sleep(3)

    def ensure_device_initialized(self, reinitialize=False):
        script_logger = ScriptLogger.get_logger()
        if self.dummy_mode:
            script_logger.log('skipping adb init system. script running in mock mode')
            return
        max_adb_attempts = 6
        max_window_attempts = 36
        adb_attempts = 0
        window_attempts = 0
        source_im = None
        if reinitialize or self.width is None or self.height is None:
            self.detect_adb_port()
            if self.auto_detect_adb_port:
                if self.emulator_type == 'bluestacks':
                    #check if window is open
                    init_bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
                    instance_window_name = init_bluestacks_config['bst.instance.{}.display_name'.format(
                        self.device_name
                    )]
                    script_logger.log('ADB CONTROLLER: detected window name {} for device {}'.format(
                        instance_window_name,
                        self.device_name
                    ))
                    self.window_name = instance_window_name

                    check_for_window = lambda window_name: "HD-Player" in bytes.decode(subprocess.run(
                        'tasklist /FI "WINDOWTITLE eq {}"'.format(window_name),
                        capture_output=True,
                        shell=True
                    ).stdout, 'utf-8')


                    while not check_for_window(instance_window_name):
                        script_logger.log('ADB CONTROLLER: window {} not found, sleeping for 5 seconds'.format(instance_window_name))
                        time.sleep(5)
                        window_attempts += 1
                        if window_attempts > max_window_attempts:
                            script_logger.log('ADB CONTROLLER: window {} not found and exceeded max attempts'.format(instance_window_name))
                            raise Exception('ADB connection failed')

                    self.detect_adb_port()

                    # state['ADB_PORT'] = self.adb_port
            script_logger.log('ADB CONTROLLER: initializing/reinitializing adb')
            script_logger.log('ADB PATH : ', self.adb_path)


            devices_output = self.get_device_list_output()
            script_logger.log('ADB CONTROLLER: listing devices')
            if not any(self.full_ip in device_line for device_line in devices_output):
                self.run_disconnect_command()
                self.run_connect_command()
                time.sleep(3)
                devices_output = self.get_device_list_output()


            emulator_active = any((
                self.full_ip in devices_output_line and 'offline' not in devices_output_line
            ) for devices_output_line in devices_output)

            if not emulator_active:
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
                self.restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = any((
                    self.full_ip in devices_output_line and 'offline' not in devices_output_line
                ) for devices_output_line in devices_output)

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    script_logger.log('ADB CONTROLLER: adb connection timed out ')
                    raise Exception('ADB connection failed')
                else:
                    adb_attempts += 1
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 15 seconds')
                self.restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = any((
                    self.full_ip in devices_output_line and 'offline' not in devices_output_line
                ) for devices_output_line in devices_output)
                time.sleep(15)

            screencap_succesful = False
            try:
                source_im = self.get_screencap(compressed=True)
                emulator_active = True
                screencap_succesful = True
            except UnidentifiedImageError:
                script_logger.log('ADB CONTROLLER: Scrrencap Failed, trying again in 15 seconds')
                self.restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = any((
                    self.full_ip in devices_output_line and 'offline' not in devices_output_line
                ) for devices_output_line in devices_output)

            if not emulator_active:
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output)
                self.restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = any((
                    self.full_ip in devices_output_line and 'offline' not in devices_output_line
                ) for devices_output_line in devices_output)

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    script_logger.log('ADB CONTROLLER: adb connection timed out ')
                    raise Exception('ADB connection failed')
                else:
                    adb_attempts += 1
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 15 seconds')
                self.restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = any((
                    self.full_ip in devices_output_line and 'offline' not in devices_output_line
                ) for devices_output_line in devices_output)
                time.sleep(15)

            if not screencap_succesful:
                try:
                    source_im = self.get_screencap(compressed=True)
                except UnidentifiedImageError:
                    script_logger.log('ADB CONTROLLER: Screencap failed, unable to resolve issue')
                    raise Exception('ADB connection failed')
            self.width = source_im.shape[1]
            self.height = source_im.shape[0]

            self.set_commands()
            self.get_screen_orientation()

            script_logger.log('ADB CONTROLLER: adb configuration successful ', self.full_ip, devices_output)
        if is_null(self.props['width']):
            self.props['width'] = self.width
        if is_null(self.props['height']):
            self.props['height'] = self.height

        # self.set_bluestacks_device()

        self.status = 'ready'
        return source_im

    def run_connect_command(self):
        script_logger = ScriptLogger.get_logger()
        script_logger.log('connecting to device', self.full_ip)
        return subprocess.run(
            self.adb_path + ' connect ' + self.full_ip, 
            cwd="/", 
            shell=True, 
            timeout=30
        )

    def run_disconnect_command(self):
        script_logger = ScriptLogger.get_logger()
        script_logger.log('disconnecting from device', self.full_ip)
        return subprocess.run(
            self.adb_path + ' disconnect ' + self.full_ip, 
            cwd="/", 
            shell=True, 
            timeout=30,
            stderr=subprocess.STDOUT
        )

    def get_device_list_output(self):
        script_logger = ScriptLogger.get_logger()
        try:
            device_list = subprocess.run(
                [self.adb_path, 'devices'], 
                cwd="/", capture_output=True, timeout=15
            )
            devices_output = bytes.decode(device_list.stdout, 'utf-8').splitlines()
        except subprocess.TimeoutExpired as t:
            script_logger.log('ADB CONTROLLER: get devices timed out ', t)
            devices_output = []
        return devices_output

    def enqueue_output(self, out, queue):
        for line in iter(out.readline, b''):
            if self.stop_command_gather:
                break
            queue.put(line)
        out.close()

    def set_commands(self, timeout=1):
        script_logger = ScriptLogger.get_logger()
        # Run the adb getevent command
        process = subprocess.Popen([self.adb_path, '-s', self.full_ip ,'shell' ,'getevent', '-p'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   bufsize=1)
        self.stop_command_gather = False
        # Use a selector to wait for I/O readiness without blocking
        q = queue.Queue()

        # Start a daemon thread to read stdout from the subprocess
        t = threading.Thread(target=self.enqueue_output, args=(process.stdout, q))
        t.daemon = True
        t.start()

        output = []
        device_line = False
        device_path = ""
        start_time = time.time()

        # Read output from the queue for the duration of the timeout
        while (time.time() - start_time) < timeout:
            try:
                line = q.get_nowait()
            except queue.Empty:
                time.sleep(0.1)  # Add a small delay to prevent busy-waiting
            else:
                output.append(line)
                if 'add device' in line:
                    device_line = True  # Next line should have the device name
                elif device_line:
                    if "BlueStacks Virtual Touch" in line or "\"virtio_input_multi_touch_1\"" in line:
                        # Extract the device path from the previous 'add device' line
                        device_path = output[-2].split()[3].strip(':')
                        break
                    device_line = False  # Reset for the next device

        # Ensure the subprocess is terminated
        self.stop_command_gather = True
        t.join()
        process.terminate()
        process.wait()
        if device_path:
            script_logger.log('ADB CONTROLLER:', 'configured input device ', device_path)
            self.sendevent_command = 'sendevent ' + device_path +' {} {} {};'
            self.commands = {
                "tracking_id_mousedown": self.sendevent_command.format(3, int('39', 16), 0),
                "touch_major_func": self.touch_major_func,
                "abs_mt_pressure_down": self.sendevent_command.format(3, int('3a', 16), int('81', 16)),
                "x_command_func": self.x_command_func,
                "y_command_func": self.y_command_func,
                "action_terminate_command": self.sendevent_command.format(0, 0, 0),
                "abs_mt_pressure_up": self.sendevent_command.format(3, int('3a', 16), 0),
                "tracking_id_mouseup": self.sendevent_command.format(3, int('39', 16), '-1'),
                "syn_mt_report": self.sendevent_command.format(0, 2, 0)
            }
            return device_path
        else:
            self.sendevent_command = 'sendevent /dev/input/event5 {} {} {};'
            self.commands = {
                "tracking_id_mousedown": self.sendevent_command.format(3, int('39', 16), 0),
                "touch_major_func": self.touch_major_func,
                "abs_mt_pressure_down": self.sendevent_command.format(3, int('3a', 16), int('81', 16)),
                "x_command_func": self.x_command_func,
                "y_command_func": self.y_command_func,
                "action_terminate_command": self.sendevent_command.format(0, 0, 0),
                "abs_mt_pressure_up": self.sendevent_command.format(3, int('3a', 16), 0),
                "tracking_id_mouseup": self.sendevent_command.format(3, int('39', 16), '-1'),
                "syn_mt_report": self.sendevent_command.format(0, 2, 0)
            }
            return None

    def get_screencap(self, compressed):
        script_logger = ScriptLogger.get_logger()
        if compressed:
            screenshot_command = self.adb_path + ' -s {} exec-out screencap -p'.format(self.full_ip)
            script_logger.log('ADB CONTROLLER', 'taking screenshot', 'with command', screenshot_command)

            try:
                process = subprocess.Popen(
                    screenshot_command,
                    cwd="/",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate(timeout=15)

                if process.returncode != 0:
                    script_logger.log(f"Command failed with return code {process.returncode}")
                    script_logger.log(f"Error output: {stderr.decode('utf-8')}")
                    raise UnidentifiedImageError()
                else:
                    script_logger.log("Command executed successfully.")

            except subprocess.TimeoutExpired:
                script_logger.log('screencap command timed out')
                stdout, stderr = process.communicate(timeout=10)
                process.kill()
                script_logger.log(stdout.decode('utf-8', errors='ignore'))
                raise UnidentifiedImageError()
            bytes_im = BytesIO(stdout)
            source_im = Image.open(bytes_im)
            img = cv2.cvtColor(np.array(source_im), cv2.COLOR_RGB2BGR)
        else:
            screenshot_command = self.adb_path + ' -s {} exec-out screencap'.format(self.full_ip)
            script_logger.log('ADB CONTROLLER', 'taking screenshot', 'with command', screenshot_command)
            try:
                process = subprocess.Popen(
                    screenshot_command,
                    cwd="/",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate(timeout=15)

                if process.returncode != 0:
                    script_logger.log(f"Command failed with return code {process.returncode}")
                    script_logger.log(f"Error output: {stderr.decode('utf-8')}")
                    raise UnidentifiedImageError()
                else:
                    script_logger.log("Command executed successfully.")

            except subprocess.TimeoutExpired:
                script_logger.log('screencap command timed out')
                stdout, stderr = process.communicate(timeout=10)
                process.kill()
                script_logger.log(stdout.decode('utf-8', errors='ignore'))
                raise UnidentifiedImageError()
            raw_data = stdout
            header_size = 16
            header_format = '<4I'  # Little-endian, 4 unsigned integers
            w, h, f, c = struct.unpack(header_format, raw_data[:header_size])

            script_logger.log(f"Width: {w}, Height: {h}, Format: {f}, Colorspace: {c}, Image Size: {len(raw_data) - header_size}")

            # Map the pixel format to bytes per pixel (Bpp)
            if f == 1:  # PIXEL_FORMAT_RGBA_8888
                Bpp = 4
                pixel_data = raw_data[header_size:]
                # Remove alpha channel
                rgb_data = np.frombuffer(pixel_data, dtype=np.uint8)
                rgb_data = rgb_data.reshape((h, w, Bpp))
                # Remove alpha channel
                rgb_data = rgb_data[:, :, :3]
                # Convert to BGR
                img = cv2.cvtColor(rgb_data, cv2.COLOR_RGB2BGR)
            elif f == 4:  # PIXEL_FORMAT_RGB_565
                Bpp = 2
                pixel_data = raw_data[header_size:]
                pixels = np.frombuffer(pixel_data, dtype=np.uint16)
                pixels = pixels.reshape((h, w))
                # Extract RGB components
                r = ((pixels >> 11) & 0x1F).astype(np.uint8)
                g = ((pixels >> 5) & 0x3F).astype(np.uint8)
                b = (pixels & 0x1F).astype(np.uint8)
                # Scale components to 8 bits
                r = (r * 255) // 31
                g = (g * 255) // 63
                b = (b * 255) // 31
                # Stack components into BGR image
                img = np.stack([b, g, r], axis=-1)
            else:
                raise ValueError(f"Unsupported pixel format: {f}")
        return img

    def screenshot(self, compress_png=False):
        script_logger = ScriptLogger.get_logger()
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, returning screenshot of input source')
            return self.input_source['screenshot']()
        try:
            source_im = self.get_screencap(compressed=compress_png)
        except (UnidentifiedImageError, struct.error, ValueError) as e:
            script_logger.log('ADB CONTROLLER: screencap failed', e)
            try:
                source_im = self.get_screencap(compressed=compress_png)
                return source_im
            except Exception as e:
                script_logger.log('ADB CONTROLLER: screencap retry failed', e)
            source_im = self.ensure_device_initialized(reinitialize=True)
            if source_im is None:
                raise Exception('ADB connection failed')
        return source_im

    def key_up(self, key):
        script_logger.log('adb keypress and hold unimplemented! defaulting to pyautogui')
        pyautogui.keyUp(key)

    def key_down(self, key):
        script_logger.log('adb keypress and hold unimplemented! defaulting to pyautogui')
        pyautogui.keyDown(key)

    def key_press(self, key):
        self.ensure_device_initialized()
        if key not in KEY_TO_KEYCODE:
            script_logger.log('key not found!', key)
            return
        keycode = KEY_TO_KEYCODE[key]
        key_input_string = "input keyevent \"{}\"".format(keycode)
        shell_process = subprocess.Popen([
            self.adb_path,
            '-s',
            self.full_ip,
            'shell'
        ],
        stdin=subprocess.PIPE)
        shell_process.communicate(key_input_string.encode('utf-8'))

    def hotkey(self, keys):
        script_logger.log('adb hotkey unimplemented! defaulting to pyautogui')
        pyautogui.hotkey(keys)

    def save_screenshot(self, save_name):
        pass

    def touch_major_func(self):
        return self.sendevent_command.format(3, int('30', 16), self.event_counter)

    def x_command_func(self, x_val):
        return self.sendevent_command.format(3, int('35', 16), x_val)

    def y_command_func(self, y_val):
        return self.sendevent_command.format(3, int('36', 16), y_val)

    def click(self, x, y, button='left', important=True, mouse_up=True):
        # 1st point always the og x,y
        self.ensure_device_initialized()
        script_logger.log('clicking')
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click returning')
            return
        click_command = []
        if self.emulator_type == 'bluestacks':
            #yes x and y is flipped for some reason in bluestacks
            # if self.device_profile == 'windows-bluestacks-8GB':
            #     mapped_x_val = int(((self.height - y) / self.height) * self.ymax)
            #     mapped_y_val = int((x / self.width) * self.xmax)
            # else:
            if self.screen_orientation == 0:
                # Default orientation, apply direct mapping.
                mapped_x_val = int((x / self.width) * self.xmax)
                mapped_y_val = int((y / self.height) * self.ymax)
            elif self.screen_orientation == 1:
                # Rotated 90 degrees counterclockwise, swap x and y, then map.
                mapped_x_val = int(((self.height - y) / self.height) * self.ymax)
                mapped_y_val = int((x / self.width) * self.xmax)
                # mapped_x_val = int((y / self.height) * self.xmax)
                # mapped_y_val = int(((self.width - x) / self.width) * self.ymax)
            elif self.screen_orientation == 2:
                # Rotated 180 degrees counterclockwise, invert x and y, then map.
                mapped_x_val = int(((self.width - x) / self.width) * self.xmax)
                mapped_y_val = int(((self.height - y) / self.height) * self.ymax)
            elif self.screen_orientation == 3:
                # Rotated 270 degrees counterclockwise (or 90 degrees clockwise), swap and invert, then map.
                mapped_x_val = int((x / self.width) * self.ymax)
                mapped_y_val = int(((self.height - y) / self.height) * self.xmax)
            else:
                raise Exception('Screen orientation not set')
            print(mapped_x_val, mapped_y_val, x, y, self.width, self.height, self.xmax, self.ymax)
            init_click_commands = [
                self.commands["x_command_func"](mapped_x_val),
                self.commands["y_command_func"](mapped_y_val),
                self.commands["syn_mt_report"],
                self.commands["action_terminate_command"]
            ]
            # init_click_commands = [commandlet for command in init_click_commands for commandlet in command.split(' ')]
            # script_logger.log(init_click_commands)
            # subprocess.run(init_click_commands, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            click_command += ['('] + init_click_commands + [') && ']
            n_events = np.random.geometric(p=0.739)
            if important:
                n_events = 1
            if n_events > 1:
                click_tail_x, click_tail_y = self.click_path_generator.generate_click_tail_sequence(n_events)
                x_pos = mapped_x_val
                y_pos = mapped_y_val
                # script_logger.log(click_tail_x,click_tail_y)
                for click_tail_index in range(0, n_events - 1):
                    x_delta = click_tail_x[click_tail_index]
                    y_delta = click_tail_y[click_tail_index]
                    coord_commands = []
                    x_pos += x_delta
                    coord_commands.append(self.commands["x_command_func"](x_pos))
                    y_pos += y_delta
                    coord_commands.append(self.commands["y_command_func"](y_pos))
                    if len(coord_commands) > 0:
                        click_command += ['('] + coord_commands + [self.commands["syn_mt_report"], self.commands["action_terminate_command"], ') && ']
            else:
                pass
            # subprocess.run([self.adb_path, 'shell', 'input', 'tap', x, y])
            # need to verify that tap will still work with only x as header (maybe try replaying some of the x header clicks)
            self.last_y = y
            self.last_x = x
            footer_commands = ['(',
                               self.commands["syn_mt_report"],
                               self.commands["action_terminate_command"],
                               ')'] if mouse_up else []
            click_command += footer_commands
        elif self.emulator_type == 'avd':
            click_command.append('input tap {} {};'.format(
                x, y
            ))
            # if important:
            #     n_events = 1
            # if n_events > 1:
            #     click_tail_x, click_tail_y = self.click_path_generator.generate_click_tail_sequence(n_events)
            # else:
            #     click_tail_x = []
            #     click_tail_y = []
            # delta_xs = [mapped_x_val] + click_tail_x
            # delta_ys = [mapped_y_val] + click_tail_y
            # click_command += self.delta_sequence_to_commands(mapped_x_val,mapped_y_val,delta_xs,delta_ys)
        else:
            raise Exception('Unrecognized emulator type: ' + self.emulator_type)

        shell_process = subprocess.Popen([
            self.adb_path,
            '-s',
            self.full_ip,
            'shell'
        ], stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        script_logger.log(
            'ADB CONTROLLER : sending click command ',
            [
              self.adb_path,
              '-s',
              self.full_ip,
              'shell'
            ],
            ''.join(click_command),
            shell_process.communicate((''.join(click_command)).encode('utf-8'), timeout=15)
        )
        # script_logger.log((''.join(click_command)).encode('utf-8'))
        self.event_counter += 1

    def mouse_down(self, x, y):
        self.click(x, y, button='left',important=True, mouse_up=False)

    def mouse_up(self, x, y):
        self.click(x, y)

    def scroll(self, x, y, scroll_distance):
        raise Exception('Scroll Action unsupported on device type Android')

    def smooth_move(self, x1, y1, x2, y2):
        return super().smooth_move()

    def delta_sequence_to_commands(self, x_pos, y_pos, delta_xs, delta_ys, unmap=False, split=True):
        script_logger.log('sequence len', len(delta_xs))
        commands = []

        # TODO below may or may not be neccesary
        # if self.screen_orientation == 0:
        #     # Default orientation, apply direct mapping.
        #     unmap_coords = lambda x,y: int((x / self.xmax) * self.width),int((y / self.ymax) * self.height)
        # elif self.screen_orientation == 1:
        #     # Rotated 90 degrees counterclockwise, swap x and y, then map.
        #     mapped_x_val = int(((self.height - y) / self.height) * self.ymax)
        #     mapped_y_val = int((x / self.width) * self.xmax)
        # elif self.screen_orientation == 2:
        #     # Rotated 180 degrees counterclockwise, invert x and y, then map.
        #     mapped_x_val = int(((self.width - x) / self.width) * self.xmax)
        #     mapped_y_val = int(((self.height - y) / self.height) * self.ymax)
        # elif self.screen_orientation == 3:
        #     # Rotated 270 degrees counterclockwise (or 90 degrees clockwise), swap and invert, then map.
        #     mapped_x_val = int((x / self.width) * self.ymax)
        #     mapped_y_val = int(((self.height - y) / self.height) * self.xmax)
        # else:
        #     raise Exception('Screen orientation not set')
        final_x_pos = x_pos
        final_y_pos = y_pos
        unmap_coords = lambda x, y: (int((x / self.xmax) * self.width), int((y / self.ymax) * self.height))
        for delta_index in range(0, len(delta_xs)):
            x_delta = delta_xs[delta_index]
            y_delta = delta_ys[delta_index]
            if split:
                commands.append('input swipe {} {} {} {} 50;'.format(
                    *unmap_coords(x_pos, y_pos),
                    *unmap_coords(x_pos + x_delta, y_pos + y_delta)
                ))
                x_pos += x_delta
                y_pos += y_delta
            else:
                final_x_pos += x_delta
                final_y_pos += y_delta

        if not split:
            commands.append('input swipe {} {} {} {} {};'.format(
                *unmap_coords(x_pos, y_pos),
                *unmap_coords(final_x_pos, final_y_pos),
                int(np.clip(np.random.normal(1500, 500, 1)[0], 500, 3000))
            ))
        return commands

    def click_and_drag(self, source_x, source_y, target_x, target_y, mouse_down=True, mouse_up=True):
        self.ensure_device_initialized()
        if self.dummy_mode:
            frac_source_x = (source_x / self.width)
            frac_target_x = (target_x / self.width)
            frac_source_y = (source_y / self.height)
            frac_target_y = (target_y / self.height)
            delta_x, delta_y = self.click_path_generator.generate_click_path(
                frac_source_x, frac_source_y,
                frac_target_x, frac_target_y
            )
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click and drag returning')
            return delta_x, delta_y
        command_strings = []
        if self.emulator_type == 'bluestacks':
            frac_source_x = (source_x / self.width)
            frac_target_x = (target_x / self.width)
            frac_source_y = (source_y / self.height)
            frac_target_y = (target_y / self.height)
            # script_logger.log('({},{}),({},{})'.format(frac_source_x, frac_source_y, frac_target_x, frac_target_y))
            delta_x, delta_y = self.click_path_generator.generate_click_path(
                frac_source_x, frac_source_y,
                frac_target_x, frac_target_y
            )
            n_events = len(delta_x)
            mapped_source_x = int(frac_source_x * self.xmax)
            mapped_source_y = int(frac_source_y * self.ymax)

            init_click_commands = [

            ]

            command_strings += init_click_commands
            x_pos = mapped_source_x
            y_pos = mapped_source_y
            # script_logger.log(click_tail_x,click_tail_y)
            for delta_index in range(0, n_events):
                x_delta = delta_x[delta_index]
                y_delta = delta_y[delta_index]
                coord_commands = []
                x_pos += x_delta
                coord_commands.append(self.commands["x_command_func"](x_pos))
                y_pos += y_delta
                coord_commands.append(self.commands["y_command_func"](y_pos))
                if len(coord_commands) > 0:
                    command_strings += coord_commands + [self.commands["syn_mt_report"],
                                                        self.commands["action_terminate_command"],
                                                        'sleep 0.001;' if random.random() < 0 else '']

            footer_commands = [
                self.commands["syn_mt_report"],
                self.commands["action_terminate_command"]
            ] if mouse_up else []
            command_strings += footer_commands
        elif self.emulator_type == 'avd':
            # frac_source_x = (source_x / self.width)
            # frac_target_x = (target_x / self.width)
            # frac_source_y = (source_y / self.height)
            # frac_target_y = (target_y / self.height)
            # # script_logger.log('({},{}),({},{})'.format(frac_source_x, frac_source_y, frac_target_x, frac_target_y))
            # delta_x, delta_y = self.click_path_generator.generate_click_path(
            #     frac_source_x, frac_source_y,
            #     frac_target_x, frac_target_y
            # )
            mapped_source_x = int((source_x / self.width) * self.xmax)
            mapped_source_y = int((source_y / self.height) * self.ymax)
            # x_pos = mapped_source_x
            # y_pos = mapped_source_y
            delta_x = [int(self.xmax * (target_x - source_x) / self.width)]
            delta_y = [int(self.ymax * (target_y - source_y) / self.height)]
            command_strings.append('input swipe {} {} {} {} {};'.format(
                source_x, source_y,
                target_x, target_y,
                int(np.clip(np.random.normal(1500, 500, 1)[0], 500, 3000))
            ))
            # command_strings += self.delta_sequence_to_commands(x_pos,y_pos,delta_x,delta_y, unmap=True, split=False)
        else:
            raise Exception('Unrecognized emulator type ' + self.emulator_type)
        shell_process = subprocess.Popen([
            self.adb_path,
            '-s',
            self.full_ip,
            'shell'
        ], stdin=subprocess.PIPE)
        script_logger.log(
            'ADB CONTROLLER : sending click command ',
            [
                self.adb_path,
                '-s',
                self.full_ip,
                'shell'
            ],
            ''.join(command_strings),
            shell_process.communicate((''.join(command_strings)).encode('utf-8'))
        )
        self.event_counter += 1
        return delta_x, delta_y