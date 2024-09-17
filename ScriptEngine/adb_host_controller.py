import asyncio
import base64
import threading
import datetime
import queue
import subprocess
import os
import json
import platform
import shlex
import re


DEVICES_CONFIG_PATH = './assets/host_devices_config.json'


from configobj import ConfigObj
from PIL import Image
from PIL import UnidentifiedImageError
from io import BytesIO
import cv2
import numpy as np
import random
import time
import sys
from scipy.stats import truncnorm
from script_engine_utils import get_glob_digit_regex_string, is_null, masked_mse, state_eval, DummyFile
import pyautogui

sys.path.append("..")
from device_action_interpeter import DeviceActionInterpreter
from script_execution_state import ScriptExecutionState
from click_path_generator import ClickPathGenerator
from image_matcher import ImageMatcher
from search_pattern_helper import SearchPatternHelper
from click_action_helper import ClickActionHelper
from detect_object_helper import DetectObjectHelper
from forward_detect_peek_helper import ForwardDetectPeekHelper
from rv_helper import RandomVariableHelper
from color_compare_helper import ColorCompareHelper


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

from script_logger import ScriptLogger
script_logger = ScriptLogger()
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

class adb_host:
    def __init__(self, props, host_os, adb_args, input_source=None):
        script_logger.log('Configuring ADB with adb_args', adb_args)
        self.stop_command_gather = False
        self.device_profile = 'windows-bluestacks'
        self.host_os = host_os
        self.image_matcher = ImageMatcher()
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
        # exit(0)
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

        if len(adb_args) > 0 and input_source is None:
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
                exit(1)


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
                    emulator_path = os.path.join(user_home, 'Library/Android/sdk/emulator/emulator')
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
            adb_in_path = False
            os_name = platform.system()
            try:
                if os_name == "Windows":
                    result = subprocess.run(["where", "adb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    result = subprocess.run(["which", "adb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                if result.returncode == 0:
                    adb_path = result.stdout.decode().strip()
                    script_logger.log(f"adb found in path at location: {adb_path}")
                    adb_in_path = True
                else:
                    script_logger.log("adb not found in PATH")
                    adb_in_path = False
            except Exception as e:
                pass
            if adb_in_path:
                self.adb_path = 'adb'
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
              'auto_detect_adb_port', self.auto_detect_adb_port)
        return ScriptExecutionState.SUCCESS, state, context

    def get_device_name_to_emulator_name_mapping(self):
        device_list = self.get_device_list_output()
        script_logger.log('device_list', device_list)
        devices = {}
        lines = device_list.splitlines()

        for line in lines[1:]:  # Skip the first line (header)
            if line.strip() and 'device' in line:
                device_id = line.split('\t')[0]
                if device_id.startswith('emulator'):
                    result = subprocess.run(['adb', '-s', device_id, 'emu', 'avd', 'name'],
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
                self.full_ip = devices[self.device_name]
                self.adb_port = self.full_ip.split('-')[1]
            else:
                self.full_ip = self.adb_ip + ':' + self.adb_port
        else:
            raise Exception('Unsupported emulator type: ' + self.emulator_type)
        if self.adb_port != 'auto':
            script_logger.log('ADB CONTROLLER: changed adb port from {} to auto detected port {}'.format(
                og_port,
                self.adb_port
            ))





    def start_device(self):
        # check if window is open
        if self.emulator_type == 'bluestacks':
            start_device_command = '"{}" --instance "{}"'.format(
                self.emulator_path,
                self.device_name
            )
            start_device_process = subprocess.Popen(
                start_device_command,
                cwd="/",
                shell=True,
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
                    '"/Users/takhogan/Library/Android/sdk/emulator/emulator" -avd "Small_Phone_API_34"',
                    cwd="/",  # You can change this to the actual working directory if needed
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )
            else:
                raise Exception('Unsupported OS ' + os_name)
            timeout = 120
            start_time = time.time()
            while True:
                output = start_device_process.stdout.readline().decode().strip()  # Read the output line-by-line
                if output:
                    script_logger.log(output)  # Optionally print each line for logging purposes

                if "boot completed" in output.lower():
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
        try:
            devices_output = self.get_device_list_output()
        except subprocess.TimeoutExpired as t:
            script_logger.log('ADB CONTROLLER: get devices timed out ', t)
            devices_output = ''
        if self.full_ip not in devices_output:
            self.run_connect_command()
            time.sleep(3)
            try:
                devices_output = self.get_device_list_output()
            except subprocess.TimeoutExpired as t:
                script_logger.log('ADB CONTROLLER: get devices timed out ', t)
                devices_output = ''
        emulator_active = (
            self.full_ip in devices_output and 'offline' not in devices_output
        )
        if emulator_active:
            return 'online'
        else:
            return 'offline'

    def get_screen_orientation(self):
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

    def init_system(self, reinitialize=False):
        if self.dummy_mode:
            script_logger.log('skipping adb init system. script running in mock mode')
            return
        max_adb_attempts = 6
        max_window_attempts = 36
        adb_attempts = 0
        window_attempts = 0
        source_im = None
        if reinitialize or self.width is None or self.height is None:
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
                            exit(478)

                    self.detect_adb_port()

                    # state['ADB_PORT'] = self.adb_port
            script_logger.log('ADB CONTROLLER: initializing/reinitializing adb')
            script_logger.log('ADB PATH : ', self.adb_path)


            devices_output = self.get_device_list_output()
            script_logger.log('ADB CONTROLLER: listing devices')
            if not self.full_ip in devices_output:
                self.run_connect_command()
                time.sleep(3)
                devices_output = self.get_device_list_output()

            run_kill_command = lambda: subprocess.run(self.adb_path + ' kill-server', cwd="/", shell=True, timeout=30)
            run_start_command = lambda: subprocess.run(self.adb_path + ' start-server', cwd="/", shell=True, timeout=30)

            def restart_adb():
                script_logger.log('ADB CONTROLLER restarting adb server')
                run_kill_command()
                run_start_command()
                time.sleep(3)
                script_logger.log('ADB CONTROLLER: connecting to adb device')
                self.run_connect_command()
                time.sleep(3)


            emulator_active = (
                (self.full_ip in devices_output) and 'offline' not in devices_output
            )

            if not emulator_active:
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                    (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    script_logger.log('ADB CONTROLLER: adb connection timed out ')
                    exit(478)
                else:
                    adb_attempts += 1
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                    ('emulator' in devices_output or
                     self.full_ip in devices_output) and 'offline' not in devices_output
                )
                time.sleep(30)

            get_im_command = subprocess.run(
                self.adb_path + ' -s {} exec-out screencap -p'.format(self.full_ip),
                cwd="/",
                shell=True,
                capture_output=True,
                timeout=15
            )
            screencap_succesful = False
            bytes_im = BytesIO(get_im_command.stdout)
            try:
                source_im = np.array(Image.open(bytes_im))
                emulator_active = True
                screencap_succesful = True
            except UnidentifiedImageError:
                script_logger.log('ADB CONTROLLER: Scrrencap Failed, trying again in 30 seconds, get_im_command: ', get_im_command)
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                        (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            if not emulator_active:
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output)
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                        (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    script_logger.log('ADB CONTROLLER: adb connection timed out ')
                    exit(478)
                else:
                    adb_attempts += 1
                script_logger.log('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                        (self.full_ip in devices_output) and 'offline' not in devices_output
                )
                time.sleep(30)

            if not screencap_succesful:
                get_im_command = subprocess.run(
                    self.adb_path + ' -s {} exec-out screencap -p'.format(self.full_ip),
                    cwd="/",
                    shell=True,
                    capture_output=True,
                    timeout=15
                )
                bytes_im = BytesIO(get_im_command.stdout)
                try:
                    source_im = np.array(Image.open(bytes_im))
                except UnidentifiedImageError:
                    script_logger.log('ADB CONTROLLER: Screencap failed, get_im_command: ', get_im_command)
                    exit(478)
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
        script_logger.log('connecting to device', self.full_ip)
        return subprocess.run(
            self.adb_path + ' connect ' + self.full_ip, cwd="/", shell=True, timeout=30
        )

    def get_device_list_output(self):
        device_list = subprocess.run(
            self.adb_path + ' devices ',
            cwd="/", shell=True, capture_output=True, timeout=15
        )
        return bytes.decode(device_list.stdout, 'utf-8')

    def enqueue_output(self, out, queue):
        for line in iter(out.readline, b''):
            if self.stop_command_gather:
                break
            queue.put(line)
        out.close()

    def set_commands(self, timeout=1):
        # Run the adb getevent command
        process = subprocess.Popen(['adb','-s', self.full_ip ,'shell' ,'getevent', '-p'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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

    def screenshot(self):
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, returning screenshot of input source')
            return self.input_source['screenshot']()
        screenshot_command = self.adb_path + ' -s {} exec-out screencap -p'.format(self.full_ip)
        script_logger.log('ADB CONTROLLER', 'taking screenshot', 'with command', screenshot_command)
        get_im_command = subprocess.run(
            screenshot_command,
            cwd="/",
            shell=True,
            capture_output=True,
            timeout=15
        )
        bytes_im = BytesIO(get_im_command.stdout)
        try:
            source_im = Image.open(bytes_im)
        except UnidentifiedImageError:
            script_logger.log('get_im_command: ', get_im_command)
            source_im = self.init_system(reinitialize=True)
            if source_im is None:
                exit(478)
        return cv2.cvtColor(np.array(source_im), cv2.COLOR_RGB2BGR)

    def keyUp(self, key):
        script_logger.log('adb keypress and hold unimplemented!')
        pyautogui.keyUp(key)

    def keyDown(self, key):
        script_logger.log('adb keypress and hold unimplemented!')
        pyautogui.keyDown(key)

    def press(self, key):
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
        script_logger.log('adb hotkey unimplemented!')
        pyautogui.hotkey(keys)

    def save_screenshot(self, save_name):
        pass

    def touch_major_func(self):
        return self.sendevent_command.format(3, int('30', 16), self.event_counter)

    def x_command_func(self, x_val):
        return self.sendevent_command.format(3, int('35', 16), x_val)

    def y_command_func(self, y_val):
        return self.sendevent_command.format(3, int('36', 16), y_val)

    def click(self, x, y, important=False):
        # 1st point always the og x,y
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click returning')
            return

        if self.device_profile == 'mac-avd':
            mapped_x_val = int((x / self.width) * self.xmax)
            mapped_y_val = int((y / self.height) * self.ymax)
            init_click_commands = [
                self.commands["tracking_id_mousedown"],
                self.commands["touch_major_func"](),
                self.commands["abs_mt_pressure_down"],
                self.commands["x_command_func"](mapped_x_val),
                self.commands["y_command_func"](mapped_y_val),
                self.commands["action_terminate_command"]
            ]
            # init_click_commands = [commandlet for command in init_click_commands for commandlet in command.split(' ')]
            # script_logger.log(init_click_commands)
            # exit(0)
            # subprocess.run(init_click_commands, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            click_command = ['('] + init_click_commands + [') && ']
            # exit(0)
            n_events = np.random.geometric(p=0.739)
            if important:
                n_events = 1
            if n_events > 1:
                tail_type = np.random.choice(['x', 'y', 'm'], p=[0.4526, 0.21, 0.3374])
                tail_sequence_x = []
                tail_sequence_y = []
                if tail_type == 'm':
                    action_to_index = {
                        'x': 0,
                        'xy': 1,
                        'y': 2
                    }
                    transition_matrix = np.array([[0.13333333, 0.14285714, 0.36],
                                                  [0.46666667, 0.5, 0.44],
                                                  [0.4, 0.35714286, 0.2]])
                    last_action = np.random.choice(['x', 'xy', 'y'], p=[2 / 18, 13 / 18, 3 / 18])
                    if last_action == 'x' or last_action == 'xy':
                        tail_sequence_x.append(last_action)
                        if last_action == 'x':
                            tail_sequence_y.append(0)
                    if last_action == 'y' or last_action == 'xy':
                        tail_sequence_y.append(last_action)
                        if last_action == 'y':
                            tail_sequence_x.append(0)
                    # click_command += ['(', ]
                    for tail_event in range(1, n_events - 1):
                        event_action = np.random.choice(['x', 'xy', 'y'],
                                                        p=transition_matrix[:, action_to_index[last_action]])
                        # gen_event_sequence.append(event_action)
                        last_action = event_action
                        if last_action == 'x' or last_action == 'xy':
                            tail_sequence_x.append(last_action)
                            if last_action == 'x':
                                tail_sequence_y.append(0)
                        if last_action == 'y' or last_action == 'xy':
                            tail_sequence_y.append(last_action)
                            if last_action == 'y':
                                tail_sequence_x.append(0)
                elif tail_type == 'x':
                    tail_sequence_x += ['x'] * (n_events - 2)
                    tail_end = np.random.choice(['x', 'xy'], p=[42 / 43, 1 / 43])
                    tail_sequence_x += [tail_end]
                    tail_sequence_y += [0] * (n_events - 2)
                    if tail_end == 'xy':
                        tail_sequence_y += [tail_end]
                    else:
                        tail_sequence_y += [0]
                elif tail_type == 'y':
                    tail_sequence_y += ['y'] * (n_events - 2)
                    tail_end = np.random.choice(['y', 'xy'], p=[20 / 21, 1 / 21])
                    tail_sequence_y += [tail_end]
                    tail_sequence_x += [0] * (n_events - 2)
                    if tail_end == 'xy':
                        tail_sequence_x += [tail_end]
                    else:
                        tail_sequence_x += [0]
                    # examine distribution of distances for different tail types (in particular 0 distance moves)
                sign_x = random.randint(0, 1) * 2 - 1
                sign_y = random.randint(0, 1) * 2 - 1
                click_tail_x,click_tail_y = self.click_path_generator.generate_path_from_sequence(tail_sequence_x, tail_sequence_y, sign_x, sign_y)
                x_pos = mapped_x_val
                y_pos = mapped_y_val
                # script_logger.log(click_tail_x,click_tail_y)
                for click_tail_index in range(0, n_events - 1):
                    x_delta = click_tail_x[click_tail_index]
                    y_delta = click_tail_y[click_tail_index]
                    coord_commands = []
                    if x_delta != 0:
                        x_pos += x_delta
                        coord_commands.append(self.commands["x_command_func"](x_pos))
                    if y_delta != 0:
                        y_pos += y_delta
                        coord_commands.append(self.commands["y_command_func"](y_pos))
                    if len(coord_commands) > 0:
                        click_command += ['('] + coord_commands + [self.commands["action_terminate_command"], ') && ']
            else:
                pass
            # subprocess.run([self.adb_path, 'shell', 'input', 'tap', x, y])
            # need to verify that tap will still work with only x as header (maybe try replaying some of the x header clicks)
            self.last_y = y
            self.last_x = x
            footer_commands = ['(',
                               self.commands["abs_mt_pressure_up"],
                               self.commands["tracking_id_mouseup"],
                               self.commands["action_terminate_command"],
                               ')']
            click_command += footer_commands
        elif self.device_profile.startswith('windows-bluestacks'):
            #yes x and y is flipped for some reason in bluestacks
            if self.device_profile == 'windows-bluestacks-8GB':
                mapped_x_val = int(((self.height - y) / self.height) * self.ymax)
                mapped_y_val = int((x / self.width) * self.xmax)
            else:
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
                print(mapped_x_val, mapped_y_val, x, y, self.width, self.height, self.xmax, self.ymax)
            init_click_commands = [
                self.commands["x_command_func"](mapped_x_val),
                self.commands["y_command_func"](mapped_y_val),
                self.commands["syn_mt_report"],
                self.commands["action_terminate_command"]
            ]
            # init_click_commands = [commandlet for command in init_click_commands for commandlet in command.split(' ')]
            # script_logger.log(init_click_commands)
            # exit(0)
            # subprocess.run(init_click_commands, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            click_command = ['('] + init_click_commands + [') && ']
            # exit(0)
            n_events = np.random.geometric(p=0.739)
            if important:
                n_events = 1
            if n_events > 1:
                tail_type = np.random.choice(['x', 'y', 'm'], p=[0.4526, 0.21, 0.3374])
                tail_sequence_x = []
                tail_sequence_y = []
                if tail_type == 'm':
                    action_to_index = {
                        'x': 0,
                        'xy': 1,
                        'y': 2
                    }
                    transition_matrix = np.array([[0.13333333, 0.14285714, 0.36],
                                                  [0.46666667, 0.5, 0.44],
                                                  [0.4, 0.35714286, 0.2]])
                    last_action = np.random.choice(['x', 'xy', 'y'], p=[2 / 18, 13 / 18, 3 / 18])
                    if last_action == 'x' or last_action == 'xy':
                        tail_sequence_x.append(last_action)
                        if last_action == 'x':
                            tail_sequence_y.append(0)
                    if last_action == 'y' or last_action == 'xy':
                        tail_sequence_y.append(last_action)
                        if last_action == 'y':
                            tail_sequence_x.append(0)
                    # click_command += ['(', ]
                    for tail_event in range(1, n_events - 1):
                        event_action = np.random.choice(['x', 'xy', 'y'],
                                                        p=transition_matrix[:, action_to_index[last_action]])
                        # gen_event_sequence.append(event_action)
                        last_action = event_action
                        if last_action == 'x' or last_action == 'xy':
                            tail_sequence_x.append(last_action)
                            if last_action == 'x':
                                tail_sequence_y.append(0)
                        if last_action == 'y' or last_action == 'xy':
                            tail_sequence_y.append(last_action)
                            if last_action == 'y':
                                tail_sequence_x.append(0)
                elif tail_type == 'x':
                    tail_sequence_x += ['x'] * (n_events - 2)
                    tail_end = np.random.choice(['x', 'xy'], p=[42 / 43, 1 / 43])
                    tail_sequence_x += [tail_end]
                    tail_sequence_y += [0] * (n_events - 2)
                    if tail_end == 'xy':
                        tail_sequence_y += [tail_end]
                    else:
                        tail_sequence_y += [0]
                elif tail_type == 'y':
                    tail_sequence_y += ['y'] * (n_events - 2)
                    tail_end = np.random.choice(['y', 'xy'], p=[20 / 21, 1 / 21])
                    tail_sequence_y += [tail_end]
                    tail_sequence_x += [0] * (n_events - 2)
                    if tail_end == 'xy':
                        tail_sequence_x += [tail_end]
                    else:
                        tail_sequence_x += [0]
                    # examine distribution of distances for different tail types (in particular 0 distance moves)
                sign_x = random.randint(0, 1) * 2 - 1
                sign_y = random.randint(0, 1) * 2 - 1
                click_tail_x, click_tail_y = self.click_path_generator.generate_path_from_sequence(tail_sequence_x,
                                                                                                   tail_sequence_y,
                                                                                                   sign_x, sign_y)
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
                               ')']
            click_command += footer_commands
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
            shell_process.communicate((''.join(click_command)).encode('utf-8'))
        )
        # script_logger.log((''.join(click_command)).encode('utf-8'))
        self.event_counter += 1

    def click_and_drag(self, source_x, source_y, target_x, target_y):
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click and drag returning')
            return

        if self.device_profile == 'mac-avd':
            frac_source_x = (source_x / self.width)
            frac_source_y = (source_y / self.height)
            frac_target_x = (target_x / self.width)
            frac_target_y = (target_y / self.height)

            delta_x, delta_y = self.click_path_generator.generate_click_path(frac_source_x, frac_source_y, frac_target_x, frac_target_y)
            n_events = len(delta_x)
            mapped_source_x = int(frac_source_x * self.xmax)
            mapped_source_y = int(frac_source_y * self.ymax)



            init_click_commands = [
                self.commands["tracking_id_mousedown"],
                self.commands["touch_major_func"](),
                self.commands["abs_mt_pressure_down"],
                self.commands["x_command_func"](mapped_source_x),
                self.commands["y_command_func"](mapped_source_y),
                self.commands["action_terminate_command"]
            ]

            command_string = init_click_commands
            x_pos = mapped_source_x
            y_pos = mapped_source_y
            # script_logger.log(click_tail_x,click_tail_y)
            for delta_index in range(0, n_events):
                x_delta = delta_x[delta_index]
                y_delta = delta_y[delta_index]
                coord_commands = []
                if x_delta != 0:
                    x_pos += x_delta
                    coord_commands.append(self.commands["x_command_func"](x_pos))
                if y_delta != 0:
                    y_pos += y_delta
                    coord_commands.append(self.commands["y_command_func"](y_pos))
                if len(coord_commands) > 0:
                    command_string += coord_commands + [self.commands["action_terminate_command"], 'sleep 0.001;' if random.random() < 0 else '']

            footer_commands = [
                               self.commands["abs_mt_pressure_up"],
                               self.commands["tracking_id_mouseup"],
                               self.commands["action_terminate_command"],
                               ]
            command_string += footer_commands
        elif self.device_profile.startswith('windows-bluestacks'):
            # yes x and y are flipped on purpouse
            if self.device_profile == 'windows-bluestacks-8GB':
                frac_source_x = ((self.height - source_y) / self.height)
                frac_source_y = (source_x / self.width)
                frac_target_x = ((self.height - target_y) / self.height)
                frac_target_y = (target_x / self.width)
            else:
                frac_source_x = (source_x / self.width)
                frac_target_x = (target_x / self.width)
                frac_source_y = (source_y / self.height)
                frac_target_y = (target_y / self.height)
            # script_logger.log('({},{}),({},{})'.format(frac_source_x, frac_source_y, frac_target_x, frac_target_y))
            delta_x, delta_y = self.click_path_generator.generate_click_path(frac_source_x, frac_source_y,
                                                                             frac_target_x, frac_target_y)
            n_events = len(delta_x)
            mapped_source_x = int(frac_source_x * self.xmax)
            mapped_source_y = int(frac_source_y * self.ymax)

            # script_logger.log(mapped_source_x)
            # script_logger.log(mapped_source_y)
            # script_logger.log(sum(delta_x), delta_x)
            # script_logger.log(sum(delta_y), delta_y)
            # exit(0)

            init_click_commands = [

            ]

            command_string = init_click_commands
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
                    command_string += coord_commands + [self.commands["syn_mt_report"],
                                                        self.commands["action_terminate_command"],
                                                        'sleep 0.001;' if random.random() < 0 else '']

            footer_commands = [
                self.commands["syn_mt_report"],
                self.commands["action_terminate_command"]
            ]
            command_string += footer_commands
        shell_process = subprocess.Popen([
            self.adb_path,
            '-s',
            self.full_ip,
            'shell'
        ], stdin=subprocess.PIPE)
        shell_process.communicate((''.join(command_string)).encode('utf-8'))
        # script_logger.log((''.join(command_string)).encode('utf-8'))
        self.event_counter += 1

    def handle_action(self, action, state, context, run_queue, lazy_eval=False):
        #initialize
        if action["actionName"] == "ADBConfigurationAction":
            status, state, context = self.configure_adb(action, state, context)
            return action, status, state, context, run_queue, []
        else:
            self.init_system()

        #execute action
        if action["actionName"] == "detectObject":
            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)

            if screencap_im_bgr is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.screenshot()

            if script_logger.get_log_level() == 'info':
                input_image_relative_path = 'detectObject-inputImage.png'
                cv2.imwrite(script_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
                script_logger.get_action_log().set_pre_file(
                    'image',
                    input_image_relative_path
                )

            if lazy_eval:
                return DetectObjectHelper.handle_detect_object, (
                    action,
                    screencap_im_bgr,
                    state,
                    context,
                    run_queue,
                    match_point,
                    check_image_scale,
                    self.props['scriptMode'],
                    True
                )
            else:
                action, status, state, context, run_queue, update_queue = DetectObjectHelper.handle_detect_object(
                    action,
                    screencap_im_bgr,
                    state,
                    context,
                    run_queue,
                    match_point=match_point,
                    check_image_scale=check_image_scale,
                    script_mode=self.props['scriptMode'],
                )
                return action, status, state, context, run_queue, update_queue
        elif action["actionName"] == "clickAction":
            action["actionData"]["clickCount"] = int(action["actionData"]["clickCount"])
            var_name = action["actionData"]["inputExpression"]
            point_choice,point_list,state,context = ClickActionHelper.get_point_choice(
                action, var_name, state, context,
                self.width, self.height
            )
            delays = []
            if action["actionData"]["delayState"] == "active":
                if action["actionData"]["distType"] == 'normal':
                    mean = action["actionData"]["mean"]
                    stddev = action["actionData"]["stddev"]
                    mins = (np.repeat(action["actionData"]["min"], action["actionData"]["clickCount"]) - mean) / stddev
                    maxes = (np.repeat(action["actionData"]["max"], action["actionData"]["clickCount"]) - mean) / stddev
                    delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev) if action["actionData"][
                                                                                       "clickCount"] > 1 else [
                        truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)]

            ClickActionHelper.draw_click(
                self.screenshot(), point_choice, point_list
            )
            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1])
                time.sleep(delays[click_count])

            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []

        elif action["actionName"] == "shellScript":
            if self.host_os is not None:
                state = self.host_os.run_shell_script(action, state)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "dragLocationSource":
            point_choice, point_list, state, context = ClickActionHelper.get_point_choice(
                action, action['actionData']['inputExpression'], state, context,
                self.width, self.height
            )
            context["dragLocationSource"] = point_choice
            ClickActionHelper.draw_click(self.screenshot(), point_choice, point_list)
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "dragLocationTarget":
            source_point = context["dragLocationSource"]
            target_point, point_list, state, context = ClickActionHelper.get_point_choice(
                action, action['actionData']['inputExpression'], state, context,
                self.width, self.height
            )
            drag_log = 'Dragging from {} to {}'.format(
                str(source_point),
                str(target_point)
            )
            script_logger.log(drag_log)
            self.click_and_drag(source_point[0], source_point[1], target_point[0], target_point[1])
            ClickActionHelper.draw_click(self.screenshot(), target_point, point_list)
            script_logger.get_action_log().add_supporting_file(
                'text',
                'drag-log.txt',
                drag_log
            )
            del context["dragLocationSource"]
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "colorCompareAction":
            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(
                action, state, output_type='matched_pixels'
            )
            if screencap_im_bgr is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.screenshot()

            if script_logger.get_log_level() == 'info':
                input_image_relative_path = 'detectObject-inputImage.png'
                cv2.imwrite(script_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
                script_logger.get_action_log().set_pre_file(
                    'image',
                    input_image_relative_path
                )

            color_score = ColorCompareHelper.handle_color_compare(screencap_im_bgr, action, state)
            if color_score > float(action['actionData']['threshold']):
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction successful. Color Score of {} was above threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction failed. Color Score of {} was below threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                return action, ScriptExecutionState.FAILURE, state, context, run_queue, []

        elif action["actionName"] == "searchPatternStartAction":
            # context = self.search_pattern_helper.generate_pattern(action, context, log_folder, self.props['dir_path'])
            # script_logger.log(state)
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "searchPatternContinueAction":
            # search_pattern_id = action["actionData"]["searchPatternID"]
            # raw_source_pt, raw_target_pt, displacement, context = self.search_pattern_helper.execute_pattern(search_pattern_id, context)
            # search_pattern_obj = context["search_patterns"][search_pattern_id]
            # step_index = search_pattern_obj["step_index"]
            # fitted_patterns = self.search_pattern_helper.fit_pattern_to_frame(self.width, self.height, search_pattern_obj["draggable_area"], [(raw_source_pt, raw_target_pt)])
            #
            # def apply_draggable_area_mask(img):
            #     return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))
            #
            # def create_and_save_screencap(self_ref, savename):
            #     img_unmasked_bgr = self.screenshot()
            #     img_masked_bgr = apply_draggable_area_mask(img_unmasked_bgr)
            #     cv2.imwrite(
            #         savename,
            #         img_masked_bgr
            #     )
            #     return img_masked_bgr
            #
            # def read_and_apply_mask(img_path):
            #     return apply_draggable_area_mask(cv2.imread(img_path))
            #
            # log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1)
            # def get_longest_path(search_string):
            #     search_result = remove_forward_slashes(glob.glob(search_string))
            #     if len(search_result) > 1:
            #         search_path_lens = list(map(len, search_result))
            #         max_search_path_len = max(search_path_lens)
            #         max_search_path = search_result[search_path_lens.index(max_search_path_len)]
            #     else:
            #         max_search_path = search_result[0]
            #     return max_search_path
            #
            # def record_movement(search_pattern_obj, x_displacement, y_displacement):
            #     curr_x,curr_y = search_pattern_obj["actual_current_point"]
            #     base_displacement_is_x = x_displacement > y_displacement
            #     slope = y_displacement / x_displacement
            #     if base_displacement_is_x:
            #         base_5_curr_x = curr_x // 5
            #         base_5_displaced_x = (curr_x + x_displacement) // 5
            #         displacement_range = range(base_5_curr_x, base_5_displaced_x, int(math.copysign(1, base_5_displaced_x - base_5_curr_x)))
            #         displacement_func = lambda displacement_leg: (slope * (displacement_leg - x_displacement) + y_displacement) // 5
            #     else:
            #         base_5_curr_y = curr_y // 5
            #         base_5_displaced_y = (curr_y + y_displacement) // 5
            #         displacement_range = range(base_5_curr_y, base_5_displaced_y,
            #                                    int(math.copysign(1, base_5_displaced_y - base_5_curr_y)))
            #         displacement_func = lambda displacement_leg: (((displacement_leg - y_displacement) / slope) + x_displacement) // 5
            #     for displacement_leg in displacement_range:
            #         displacement_leg_dependant = displacement_func(displacement_leg)
            #         locations = [
            #             (displacement_leg * 5, displacement_leg_dependant * 5),
            #             (displacement_leg * 5, displacement_leg_dependant * 5 + 1),
            #             (displacement_leg * 5, displacement_leg_dependant * 5 - 1)
            #         ] if base_displacement_is_x else [
            #             (displacement_leg_dependant * 5, displacement_leg * 5),
            #             (displacement_leg_dependant * 5 + 1, displacement_leg * 5),
            #             (displacement_leg_dependant * 5 - 1, displacement_leg * 5),
            #         ]
            #         for location in locations:
            #             if location not in search_pattern_obj["area_map"]:
            #                 search_pattern_obj["area_map"][
            #                     location
            #                 ] = {
            #                     "x": location[0],
            #                     "y": location[1],
            #                     "val": 255
            #                 }
            #             else:
            #                 search_pattern_obj["area_map"][
            #                     location
            #                 ]["val"] = max(
            #                     search_pattern_obj["area_map"][
            #                         location
            #                     ]["val"] - 60, 60)
            # def remove_forward_slashes(slash_list):
            #     return list(map(lambda slash_path: slash_path.replace('\\', '/'), list(slash_list)))
            # if search_pattern_obj["stitcher_status"] != "STITCHER_OK" and step_index > 0:
            #     prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1))
            #     prev_post_img_path_split = prev_post_img_path.split('/')
            #     pre_img_name = prev_post_img_path_split[-1]
            #     pre_img_path = prev_post_img_path
            #     pre_img = read_and_apply_mask(pre_img_path)
            # else:
            #     pre_img_name = str(step_index) + \
            #         '-' + str(raw_source_pt[0]) + '-' + str(raw_source_pt[1]) + '-search-step-init.png'
            #     pre_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + pre_img_name
            #     script_logger.log('pre_path', pre_img_name, ':', raw_source_pt, ':', step_index)
            #     pre_img = create_and_save_screencap(
            #         self, pre_img_path
            #     )
            #
            # for fitted_pattern in fitted_patterns:
            #     (fitted_source_pt, fitted_target_pt) = fitted_pattern
            #     if self.width > self.height:
            #         search_unit_scale = self.height
            #     else:
            #         search_unit_scale = self.width
            #     src_x = fitted_source_pt[0] * search_unit_scale
            #     src_y = fitted_source_pt[1] * search_unit_scale
            #     tgt_x = fitted_target_pt[0] * search_unit_scale
            #     tgt_y = fitted_target_pt[1] * search_unit_scale
            #     script_logger.log('desired move: (', tgt_x - src_x,',', tgt_y - src_y, ')')
            #     self.click_and_drag(src_x, src_y, tgt_x, tgt_y)
            #     time.sleep(0.25)
            # post_img_name = str(step_index) + '-' +\
            #     str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-complete.png'
            # post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + post_img_name
            # script_logger.log('post_img_path', post_img_path, ':', raw_target_pt, ':', step_index)
            # post_img = create_and_save_screencap(
            #     self, post_img_path
            # )
            # stitch_attempts = 0
            # stitch_imgs = [pre_img, post_img]
            # stitching_complete = False
            # retaken_post_img_name = None
            # retaken_post_img_path = None
            # while not stitching_complete:
            #     script_logger.log('len : stitch imgs', len(stitch_imgs), pre_img.shape, post_img.shape)
            #     err_code, result_im = search_pattern_obj["stitcher"].stitch(stitch_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
            #     draggable_area_path = search_pattern_obj["draggable_area_path"]
            #
            #     if err_code == cv2.STITCHER_OK:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_OK"
            #         search_pattern_obj["stitch"] = result_im
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/' + str(step_index) + '-pano.png', result_im)
            #         # script_logger.log(subprocess.run([self.image_stitch_calculator_path,
            #         #                       pre_img_path, post_img_path, '-m',
            #         #                       draggable_area_path, draggable_area_path],
            #         #                       capture_output=True,shell=False).stdout)
            #         break
            #     elif err_code == cv2.STITCHER_ERR_NEED_MORE_IMGS:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_ERR_NEED_MORE_IMGS"
            #         retaken_post_img_name = str(step_index) + '-' + \
            #                                 str(raw_target_pt[0]) + '-' + str(
            #             raw_target_pt[1]) + '-retaken-search-step-complete.png'
            #         retaken_post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + retaken_post_img_name
            #         if stitch_attempts > 1:
            #             script_logger.log('need more imgs: ', len(stitch_imgs))
            #             search_pattern_obj["step_index"] -= 1
            #             shutil.move(pre_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
            #             shutil.move(post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
            #             shutil.move(retaken_post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
            #             break
            #         retaken_post_img = create_and_save_screencap(
            #             self, retaken_post_img_path
            #         )
            #
            #         stop_index = max(0, step_index - 1)
            #         start_index = max(0, step_index - 4)
            #         glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
            #         script_logger.log('glob_patterns', glob_patterns)
            #         stitch_imgs = remove_forward_slashes(
            #             itertools.chain.from_iterable(
            #                 (glob.glob(
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                         glob_pattern) + '*-complete.png'
            #                 ) + glob.glob(
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                         glob_pattern
            #                     ) + '*-init.png'
            #                 )) for glob_pattern in glob_patterns
            #             )
            #         )
            #         script_logger.log('stitch_ims ', stitch_imgs)
            #         if step_index > 0:
            #             prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(stop_index) + '*-complete.png')
            #             script_logger.log('prev_post_img_path', prev_post_img_path)
            #             stitch_imgs.remove(prev_post_img_path)
            #             new_step_imgs = [pre_img, read_and_apply_mask(prev_post_img_path), retaken_post_img]
            #         else:
            #             new_step_imgs = [pre_img, retaken_post_img]
            #         stitch_imgs = new_step_imgs + (list(map(read_and_apply_mask, stitch_imgs)) if stop_index > 0 else [])
            #         # script_logger.log('post stitch_ims: ', stitch_imgs)
            #         stitch_attempts += 1
            #     else:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_ERR"
            #         search_pattern_obj["step_index"] -= 1
            #         shutil.move(pre_img_path,
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
            #         shutil.move(post_img_path,
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
            #         if retaken_post_img_path is not None and retaken_post_img_name is not None:
            #             shutil.move(retaken_post_img_path,
            #                         log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
            #         script_logger.log('special error! ' + err_code)
            #         break
            #
            # context["search_patterns"][search_pattern_id] = search_pattern_obj
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "searchPatternEndAction":
            # search_pattern_id = action["actionData"]["searchPatternID"]
            # if context["parent_action"] is not None and \
            #     context["parent_action"]["actionName"] == "searchPatternContinueAction" and \
            #     context["parent_action"]["actionData"]["searchPatternID"] == search_pattern_id and \
            #     not context["search_patterns"][search_pattern_id]["stitcher_status"] == "stitching_finished":
            #     # TODO haven't decided what the stiching_finished status should be yet (ie should always just return)
            #     return ScriptExecutionState.RETURN, state, context
            #
            # step_index = context["search_patterns"][search_pattern_id]["step_index"]
            # search_pattern_obj = context["search_patterns"][search_pattern_id]
            # def apply_draggable_area_mask(img):
            #     return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))
            # def read_and_apply_mask(img_path):
            #     return apply_draggable_area_mask(cv2.imread(img_path))
            # def generate_greater_pano(start_index, stop_index):
            #     glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
            #     greater_pano_paths = remove_forward_slashes(
            #         itertools.chain.from_iterable(
            #             glob.glob(
            #                 log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                     glob_pattern
            #                 ) + '*-complete.png'
            #             ) + glob.glob(
            #                 log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                     glob_pattern
            #                 ) + '*-init.png'
            #             ) for glob_pattern in glob_patterns
            #         )
            #     )
            #     greater_pano_imgs = list(map(read_and_apply_mask, greater_pano_paths))
            #     err_code, result_im = search_pattern_obj["stitcher"].stitch(greater_pano_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
            #     if err_code == cv2.STITCHER_OK:
            #         script_logger.log('generating full panorama...')
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/full-pano.png', result_im)
            #         # script_logger.log(subprocess.run([self.image_stitch_calculator_path] + \
            #         #                      greater_pano_paths + ['-m'] + \
            #         #                      [draggable_area_path] * len(greater_pano_paths),
            #         #                      capture_output=True, shell=False).stdout)
            #         pass
            #     else:
            #         script_logger.log('failed to greater pano: ', err_code)
            # generate_greater_pano(0, step_index)
            #
            # del context["search_patterns"][action["actionData"]["searchPatternID"]]
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        #TODO: deprecated
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                # script_logger.log(np.array(pyautogui.screenshot()).shape)
                # exit(0)
                log_image = self.screenshot()
                cv2.imwrite(script_logger.get_log_path_prefix() + '-logImage.png', log_image)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                script_logger.log('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        elif action["actionName"] == "timeAction":
            state[action["actionData"]["outputVarName"]] = datetime.datetime.now()
            # self.state[action["actionData"]["outputVarName"]] = expression
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(
                self, action, state, context
            )
            return action, status, state, context, run_queue, []
        else:
            script_logger.log("action uninplemented on adb " + action["actionName"])
            exit(0)

@staticmethod
def set_adb_args(device_key):
    adb_args = None
    with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
        devices_config = json.load(devices_config_file)
        if device_key in devices_config:
            adb_args = devices_config[device_key]
        else:
            script_logger.log('ADB HOST CONTROLLER: device config for ', device_key, ' not found! ')
    script_logger.log('ADB HOST CONTROLLER: loading args', adb_args)
    return adb_args

@staticmethod
def parse_inputs(process_adb_host, inputs):
    device_action = inputs[2]
    if device_action == 'check_status':
        status = process_adb_host.get_status()
        script_logger.log('device {} returned status {}'.format(
            process_adb_host.device_name,
            status
        ))
        return {
            "data": status
        }
    elif device_action == 'screen_capture':
        if process_adb_host.get_status() == 'offline':
            return {

            }
        try:
            process_adb_host.init_system()
            screenshot = process_adb_host.screenshot()
        except subprocess.TimeoutExpired as t:
            script_logger.log('ADB CONTROLLER: timeout while capturing screenshot', t)
            return {
                
            }
        _, buffer = cv2.imencode('.jpg', screenshot)
        byte_array = buffer.tobytes()
        base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
        return {
            "data": base64_encoded_string
        }
    elif device_action == "click":
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        process_adb_host.get_screen_orientation()
        process_adb_host.click(int(float(inputs[3])), int(float(inputs[4])))
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        process_adb_host.get_screen_orientation()
        process_adb_host.click_and_drag(int(float(inputs[3])), int(float(inputs[4])), int(float(inputs[5])), int(float(inputs[6])))
        return {
            "data" : "success"
        }
    elif device_action == "send_keys":
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        for c in inputs[3]:
            process_adb_host.press(c)
        return {
            "data": "success"
        }



async def read_input():
    script_logger.log("ADB CONTROLLER PROCESS: listening for input")
    process_adb_host = None
    device_key = None
    while True:
        input_line = await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = shlex.split(input_line)
        script_logger.log('ADB CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[1]
        elif device_key != inputs[1]:
            script_logger.log('ADB CONTROLLER: device key mismatch ', device_key, inputs[1])
            continue
        if process_adb_host is None:
            script_logger.set_log_file_path('./logs/{}-adb-host-controller-{}-process.txt'.format(formatted_today, device_key.replace(':', '-')))
            script_logger.set_log_header('')
            script_logger.log('ADB CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            script_logger.log('ADB CONTROLLER PROCESS: processing inputs ', inputs)
                # process_file.write(json.dumps(adb_args) + '\n')
            adb_args = set_adb_args(inputs[1])
            process_adb_host = adb_host({
                "dir_path": "./",
                "width" : None,
                "height" : None
            }, None, adb_args)
        if len(inputs) > 2:
            script_logger.log('<--{}-->'.format(inputs[0]) + json.dumps(parse_inputs(process_adb_host, inputs)) + '<--{}-->'.format(inputs[0]), file=DummyFile(), flush=True)
            script_logger.log('ADB CONTROLLER: Response sent for {}'.format(inputs[0]), flush=True)

async def adb_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    os.makedirs('./logs', exist_ok=True)
    script_logger.set_log_file_path('./logs/' + formatted_today + '-adb-host-controller-main.txt')
    script_logger.set_log_header('')


    asyncio.run(adb_controller_main())
