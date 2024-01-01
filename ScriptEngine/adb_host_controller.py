import asyncio
import base64
import threading
import datetime
import queue
import subprocess
import select
import json
import platform
import shlex

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
from script_engine_utils import get_glob_digit_regex_string, is_null, masked_mse
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

class adb_host:
    def __init__(self, props, host_os, adb_args):
        print('Configuring ADB with default parameters')
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
        # print(self.adb_path)
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

        #default configuration
        try:
            status, _, _ = self.configure_adb({
                'actionData' : {
                    'adbPath' : "'adb'",
                    'emulatorType' : '"' + adb_args['type'] + '"',
                    'emulatorPath' : "'C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe'",
                    'deviceName' : '"' + adb_args['devicename'] + '"',
                    'windowName' : '"' + adb_args['name'] + '"',
                    'adbPort' : '"' + adb_args['port'] + '"'
                }
            }, {}, {})
        except Exception as e:
            print('ADB HOST CONTROLLER: exception', e)
            status = ScriptExecutionState.FAILURE
        if status == ScriptExecutionState.FAILURE:
            print('ADB HOST CONTROLLER: adb configuration failed')
            exit(1)


    def configure_adb(self, configurationAction, state, context):
        state_copy = state.copy()
        emulator_type = eval(configurationAction['actionData']['emulatorType'], state_copy)

        if emulator_type != 'bluestacks':
            print('emulator type not supported!')
            return ScriptExecutionState.FAILURE, state, context

        self.emulator_type = emulator_type
        state['EMULATOR_TYPE'] = emulator_type

        adb_path = eval(configurationAction['actionData']["adbPath"], state_copy)
        self.adb_path = adb_path
        state['ADB_PATH'] = adb_path

        emulator_path = eval(configurationAction['actionData']["emulatorPath"], state_copy)
        self.emulator_path = emulator_path
        state['EMULATOR_PATH'] = emulator_path

        device_name = eval(configurationAction['actionData']["deviceName"], state_copy)
        self.device_name = device_name
        state['DEVICE_NAME'] = device_name

        init_bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
        instance_window_name = init_bluestacks_config['bst.instance.{}.display_name'.format(
            self.device_name
        )]
        print('ADB CONTROLLER: detected window name {} for device {}'.format(
            instance_window_name,
            self.device_name
        ))
        self.window_name = instance_window_name
        state['WINDOW_NAME'] = instance_window_name

        adb_port = str(eval(configurationAction['actionData']['adbPort'], state_copy))
        self.auto_detect_adb_port = (adb_port == 'auto')
        if self.auto_detect_adb_port:
            og_port = adb_port
            bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
            self.adb_port = bluestacks_config['bst.instance.{}.status.adb_port'.format(
                self.device_name
            )]
            print('ADB CONTROLLER: changed adb port from {} to auto detected port {}'.format(
                og_port,
                self.adb_port
            ))
        else:
            self.adb_port = adb_port
        state['ADB_PORT'] = self.adb_port
        self.full_ip = self.adb_ip + ':' + self.adb_port
        state['AUTO_DETECT_ADB_PORT'] = self.auto_detect_adb_port

        self.status = 'initialized'
        print('Configured ADB: ',
              'adb_path', adb_path,
              'emulator_path', emulator_path,
              'device_name', device_name,
              'window_name', instance_window_name,
              'adb_port', adb_port,
              'auto_detect_adb_port', self.auto_detect_adb_port)
        return ScriptExecutionState.SUCCESS, state, context

    def start_device(self):
        # check if window is open
        if self.emulator_type == 'bluestacks':
            start_device_command = subprocess.Popen('"{}" --instance "{}"'.format(
                self.emulator_path,
                self.device_name
            ), cwd="/", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print('ADB CONTROLLER: started device', self.device_name, 'PID:', start_device_command.pid)
        else:
            print('ADB CONTROLLER: emulator type ', self.emulator_type, ' not supported')

    def stop_device(self):
        if platform.system() == 'Windows':
            if self.emulator_type == 'bluestacks':
                init_bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
                instance_window_name = init_bluestacks_config['bst.instance.{}.display_name'.format(
                    self.device_name
                )]
                print('ADB CONTROLLER: detected window name {} for device {}'.format(
                    instance_window_name,
                    self.device_name
                ))
                self.window_name = instance_window_name
                stop_device_command = subprocess.run('taskkill /fi "WINDOWTITLE eq {}" /IM "HD-Player.exe" /F'.format(
                    self.window_name
                ), cwd="/", shell=True, capture_output=True, timeout=15)
                print('ADB CONTROLLER: stopped device', self.device_name, 'with result',
                      stop_device_command.returncode, stop_device_command)
            else:
                print('ADB CONTROLLER: emulator type ', self.emulator_type, ' not supported')

    def get_status(self):
        devices_output = self.get_device_list_output()
        if not self.full_ip in devices_output:
            self.run_connect_command()
            time.sleep(3)
            devices_output = self.get_device_list_output()
        emulator_active = (
                (self.full_ip in devices_output) and 'offline' not in devices_output
        )
        if emulator_active:
            return 'online'
        else:
            return 'offline'

    def init_system(self, reinitialize=False):
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
                    print('ADB CONTROLLER: detected window name {} for device {}'.format(
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
                        print('ADB CONTROLLER: window {} not found, sleeping for 5 seconds'.format(instance_window_name))
                        time.sleep(5)
                        window_attempts += 1
                        if window_attempts > max_window_attempts:
                            print('ADB CONTROLLER: window {} not found and exceeded max attempts'.format(instance_window_name))
                            exit(478)
                    bluestacks_config = ConfigObj('C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf', file_error=True)
                    og_port = self.adb_port
                    self.adb_port = bluestacks_config['bst.instance.{}.status.adb_port'.format(
                        self.device_name
                    )]
                    print('ADB CONTROLLER: changed adb port from {} to auto detected port {}'.format(
                        og_port,
                        self.adb_port
                    ))
                    self.full_ip = self.adb_ip + ':' + self.adb_port
                    # state['ADB_PORT'] = self.adb_port
            print('ADB CONTROLLER: initializing/reinitializing adb')
            print('ADB PATH : ', self.adb_path)


            devices_output = self.get_device_list_output()
            print('ADB CONTROLLER: listing devices')
            if not self.full_ip in devices_output:
                self.run_connect_command()
                time.sleep(3)
                devices_output = self.get_device_list_output()

            run_kill_command = lambda: subprocess.run(self.adb_path + ' kill-server', cwd="/", shell=True, timeout=30)
            run_start_command = lambda: subprocess.run(self.adb_path + ' start-server', cwd="/", shell=True, timeout=30)

            def restart_adb():
                print('ADB CONTROLLER restarting adb server')
                run_kill_command()
                run_start_command()
                time.sleep(3)
                print('ADB CONTROLLER: connecting to adb device')
                self.run_connect_command()
                time.sleep(3)


            emulator_active = (
                (self.full_ip in devices_output) and 'offline' not in devices_output
            )

            if not emulator_active:
                print('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                    (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    print('ADB CONTROLLER: adb connection timed out ')
                    exit(478)
                else:
                    adb_attempts += 1
                print('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
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
                print('ADB CONTROLLER: Scrrencap Failed, trying again in 30 seconds, get_im_command: ', get_im_command)
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                        (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            if not emulator_active:
                print('ADB CONTROLLER: problem found in devices output : ', devices_output)
                restart_adb()
                devices_output = self.get_device_list_output()
                emulator_active = (
                        (self.full_ip in devices_output) and 'offline' not in devices_output
                )

            while not emulator_active:
                if adb_attempts > max_adb_attempts:
                    print('ADB CONTROLLER: adb connection timed out ')
                    exit(478)
                else:
                    adb_attempts += 1
                print('ADB CONTROLLER: problem found in devices output : ', devices_output, 'waiting 30 seconds')
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
                    print('ADB CONTROLLER: Screencap failed, get_im_command: ', get_im_command)
                    exit(478)
            self.width = source_im.shape[1]
            self.height = source_im.shape[0]

            self.set_commands()

            print('ADB CONTROLLER: adb configuration successful ', self.full_ip, devices_output)
        if is_null(self.props['width']):
            self.props['width'] = self.width
        if is_null(self.props['height']):
            self.props['height'] = self.height

        # self.set_bluestacks_device()

        self.status = 'ready'
        return source_im

    def run_connect_command(self):
        return subprocess.run(
            self.adb_path + ' connect ' + self.full_ip, cwd="/", shell=True, timeout=30
        )

    def get_device_list_output(self):
        device_list = subprocess.run(
            self.adb_path + ' devices ',
            cwd="/", shell=True, capture_output=True, timeout=15
        )
        return bytes.decode(device_list.stdout, 'utf-8')

    @staticmethod
    def enqueue_output(out, queue):
        for line in iter(out.readline, b''):
            queue.put(line)
        out.close()

    def set_commands(self, timeout=1):
        # Run the adb getevent command
        process = subprocess.Popen(['adb', 'shell','getevent', '-p'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   bufsize=1)

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
                    if "BlueStacks Virtual Touch" in line:
                        # Extract the device path from the previous 'add device' line
                        device_path = output[-2].split()[3].strip(':')
                        break
                    device_line = False  # Reset for the next device

        # Ensure the subprocess is terminated
        process.terminate()
        process.wait()
        if device_path:
            print('ADB CONTROLLER:', 'configured input device ', device_path)
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
        print('ADB CONTROLLER', 'taking screenshot')
        get_im_command = subprocess.run(
            self.adb_path + ' -s {} exec-out screencap -p'.format(self.full_ip),
            cwd="/",
            shell=True,
            capture_output=True,
            timeout=15
        )
        bytes_im = BytesIO(get_im_command.stdout)
        try:
            source_im = Image.open(bytes_im)
        except UnidentifiedImageError:
            print('get_im_command: ', get_im_command)
            source_im = self.init_system(reinitialize=True)
            if source_im is None:
                exit(478)
        return cv2.cvtColor(np.array(source_im), cv2.COLOR_RGB2BGR)

    def keyUp(self, key):
        print('adb keypress and hold unimplemented!')
        pyautogui.keyUp(key)

    def keyDown(self, key):
        print('adb keypress and hold unimplemented!')
        pyautogui.keyDown(key)

    def press(self, key):
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
        print('adb hotkey unimplemented!')
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
            # print(init_click_commands)
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
                # print(click_tail_x,click_tail_y)
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
                mapped_x_val = int((x / self.width) * self.xmax)
                mapped_y_val = int((y / self.height) * self.ymax)
            init_click_commands = [
                self.commands["x_command_func"](mapped_x_val),
                self.commands["y_command_func"](mapped_y_val),
                self.commands["syn_mt_report"],
                self.commands["action_terminate_command"]
            ]
            # init_click_commands = [commandlet for command in init_click_commands for commandlet in command.split(' ')]
            # print(init_click_commands)
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
                # print(click_tail_x,click_tail_y)
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
        print('ADB CONTROLLER : sending click command ',''.join(click_command), shell_process.communicate((''.join(click_command)).encode('utf-8')))
        # print((''.join(click_command)).encode('utf-8'))
        self.event_counter += 1

    def click_and_drag(self, source_x, source_y, target_x, target_y):

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
            # print(click_tail_x,click_tail_y)
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
            # print('({},{}),({},{})'.format(frac_source_x, frac_source_y, frac_target_x, frac_target_y))
            delta_x, delta_y = self.click_path_generator.generate_click_path(frac_source_x, frac_source_y,
                                                                             frac_target_x, frac_target_y)
            n_events = len(delta_x)
            mapped_source_x = int(frac_source_x * self.xmax)
            mapped_source_y = int(frac_source_y * self.ymax)

            # print(mapped_source_x)
            # print(mapped_source_y)
            # print(sum(delta_x), delta_x)
            # print(sum(delta_y), delta_y)
            # exit(0)

            init_click_commands = [

            ]

            command_string = init_click_commands
            x_pos = mapped_source_x
            y_pos = mapped_source_y
            # print(click_tail_x,click_tail_y)
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
        # print((''.join(command_string)).encode('utf-8'))
        self.event_counter += 1

    def handle_action(self, action, state, context, run_queue, log_level, log_folder, lazy_eval=False):
        logs_path = log_folder + str(context['script_counter']).zfill(5) + '-' + action["actionName"] + '-' + str(action["actionGroup"]) + '-'


        #initialize
        if action["actionName"] == "ADBConfigurationAction":
            status, state, context = self.configure_adb(action, state, context)
            return action, status, state, context, run_queue, []
        else:
            self.init_system()

        #execute action
        if action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/

            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)

            if screencap_im_bgr is None:
                print('detectObject-' + str(action["actionGroup"]) + ' taking screenshot')
                screencap_im_bgr = self.screenshot()

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
                    log_level,
                    logs_path,
                    self.props['dir_path'],
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
                    log_level=log_level,
                    logs_path=logs_path,
                    dir_path=self.props['dir_path']
                )
                return action, status, state, context, run_queue, update_queue
        elif action["actionName"] == "clickAction":
            # if '__builtins__' in state:
            #     print('deleting builtins')
            #     del state['__builtins__']
            # print('pre clickaction state ', state)
            var_name = action["actionData"]["inputExpression"]
            point_choice,state,context = ClickActionHelper.get_point_choice(action, var_name, state, context, self.width, self.height)
            # if '__builtins__' in state:
            #     print('deleting builtins')
            #     del state['__builtins__']
            # print('post clickaction state ', state)
            # point_choice = (
            # point_choice[0] * self.width / self.props['width'], point_choice[1] * self.height / self.props['height'])
            print('clickAction-' + str(action["actionGroup"]), ' input: ', var_name, ' output : ', point_choice)
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

            ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path, log_level)
            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1])
                time.sleep(delays[click_count])

            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []

        elif action["actionName"] == "shellScript":
            if self.host_os is not None:
                state = self.host_os.run_script(action, state)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []

        elif action["actionName"] == "conditionalStatement":
            if eval(action["actionData"]["condition"], state):
                print('condition success!')
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                print('condition failure!')
                return action, ScriptExecutionState.FAILURE, state, context, run_queue, []
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() == '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state)))
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "dragLocationSource":
            source_point = random.choice(action["actionData"]["pointList"])
            print('dragLocationSource : input expression : ', action["actionData"]["inputExpression"])
            drag_input = action["actionData"]["inputExpression"]
            if drag_input is not None and len(drag_input) > 0:
                source_point = eval(action["actionData"]["inputExpression"], state)
                print('dragLocationSource : reading input expression ', action["actionData"]["inputExpression"])
            context["dragLocationSource"] = source_point
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "dragLocationTarget":
            source_point = context["dragLocationSource"]
            target_point = random.choice(action["actionData"]["pointList"])
            drag_input = action["actionData"]["inputExpression"]
            if drag_input is not None and len(drag_input) > 0:
                print('dragLocationTarget : input expression : ', action["actionData"]["inputExpression"])
                target_point = eval(action["actionData"]["inputExpression"], state)
            print('dragLocationTarget: dragging from ', source_point, ' to ', target_point)
            self.click_and_drag(source_point[0], source_point[1], target_point[0], target_point[1])
            del context["dragLocationSource"]
            # print(source_point)
            # print(target_point)
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "searchPatternStartAction":
            context = self.search_pattern_helper.generate_pattern(action, context, log_folder, self.props['dir_path'])
            # print(state)
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
            #     print('pre_path', pre_img_name, ':', raw_source_pt, ':', step_index)
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
            #     print('desired move: (', tgt_x - src_x,',', tgt_y - src_y, ')')
            #     self.click_and_drag(src_x, src_y, tgt_x, tgt_y)
            #     time.sleep(0.25)
            # post_img_name = str(step_index) + '-' +\
            #     str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-complete.png'
            # post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + post_img_name
            # print('post_img_path', post_img_path, ':', raw_target_pt, ':', step_index)
            # post_img = create_and_save_screencap(
            #     self, post_img_path
            # )
            # stitch_attempts = 0
            # stitch_imgs = [pre_img, post_img]
            # stitching_complete = False
            # retaken_post_img_name = None
            # retaken_post_img_path = None
            # while not stitching_complete:
            #     print('len : stitch imgs', len(stitch_imgs), pre_img.shape, post_img.shape)
            #     err_code, result_im = search_pattern_obj["stitcher"].stitch(stitch_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
            #     draggable_area_path = search_pattern_obj["draggable_area_path"]
            #
            #     if err_code == cv2.STITCHER_OK:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_OK"
            #         search_pattern_obj["stitch"] = result_im
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/' + str(step_index) + '-pano.png', result_im)
            #         # print(subprocess.run([self.image_stitch_calculator_path,
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
            #             print('need more imgs: ', len(stitch_imgs))
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
            #         print('glob_patterns', glob_patterns)
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
            #         print('stitch_ims ', stitch_imgs)
            #         if step_index > 0:
            #             prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(stop_index) + '*-complete.png')
            #             print('prev_post_img_path', prev_post_img_path)
            #             stitch_imgs.remove(prev_post_img_path)
            #             new_step_imgs = [pre_img, read_and_apply_mask(prev_post_img_path), retaken_post_img]
            #         else:
            #             new_step_imgs = [pre_img, retaken_post_img]
            #         stitch_imgs = new_step_imgs + (list(map(read_and_apply_mask, stitch_imgs)) if stop_index > 0 else [])
            #         # print('post stitch_ims: ', stitch_imgs)
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
            #         print('special error! ' + err_code)
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
            #         print('generating full panorama...')
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/full-pano.png', result_im)
            #         # print(subprocess.run([self.image_stitch_calculator_path] + \
            #         #                      greater_pano_paths + ['-m'] + \
            #         #                      [draggable_area_path] * len(greater_pano_paths),
            #         #                      capture_output=True, shell=False).stdout)
            #         pass
            #     else:
            #         print('failed to greater pano: ', err_code)
            # generate_greater_pano(0, step_index)
            #
            # del context["search_patterns"][action["actionData"]["searchPatternID"]]
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                # print(np.array(pyautogui.screenshot()).shape)
                # exit(0)
                log_image = self.screenshot()
                cv2.imwrite(logs_path + '-logImage.png', log_image)
                return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
            else:
                print('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        elif action["actionName"] == "timeAction":
            state[action["actionData"]["outputVarName"]] = datetime.datetime.now()
            # self.state[action["actionData"]["outputVarName"]] = expression
            return action, ScriptExecutionState.SUCCESS, state, context, run_queue, []
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(self, action, state, context)
            return action, status, state, context, run_queue, []
        else:
            print("action uninplemented on adb " + action["actionName"])
            exit(0)

@staticmethod
def set_adb_args(device_key):
    adb_args = None
    with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
        devices_config = json.load(devices_config_file)
        if device_key in devices_config:
            adb_args = devices_config[device_key]
        else:
            print('ADB HOST CONTROLLER: device config for ', device_key, ' not found! ')
    print('ADB HOST CONTROLLER: loading args', adb_args)
    return adb_args

@staticmethod
def parse_inputs(process_adb_host, inputs):
    device_action = inputs[1]
    if device_action == 'check_status':
        return {
            "data": process_adb_host.get_status()
        }
    elif device_action == 'screen_capture':
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        screenshot = process_adb_host.screenshot()
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
        process_adb_host.click(inputs[2], inputs[3])
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        process_adb_host.click_and_drag(inputs[2], inputs[3], inputs[4], inputs[5])
        return {
            "data" : "success"
        }
    elif device_action == "send_keys":
        if process_adb_host.get_status() == 'offline':
            return {

            }
        process_adb_host.init_system()
        for c in inputs[2]:
            process_adb_host.press(c)
        return {
            "data": "success"
        }


PROCESS_DELIMITER = '<--DEVICE-RESPONSE-->'

async def read_input():
    print("ADB CONTROLLER PROCESS: listening for input")
    process_adb_host = None
    device_key = None
    while True:
        input_line = await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = shlex.split(input_line)
        print('ADB CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[0]
        elif device_key != inputs[0]:
            print('ADB CONTROLLER: device key mismatch ', device_key, inputs[0])
            continue
        if process_adb_host is None:
            print('ADB CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            with open('adb-host-controller-{}-process.txt'.format(device_key.replace(':', '-')), 'w') as process_file:
                process_file.write(str(datetime.datetime.now()) + '\n')
                # process_file.write(json.dumps(adb_args) + '\n')
            adb_args = set_adb_args(inputs[0])
            process_adb_host = adb_host({
                "dir_path": "./",
                "width" : None,
                "height" : None
            }, None, adb_args)
        if len(inputs) > 1:
            print(PROCESS_DELIMITER + json.dumps(parse_inputs(process_adb_host, inputs)) + PROCESS_DELIMITER)

async def adb_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    asyncio.run(adb_controller_main())
