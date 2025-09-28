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

import sys
import datetime
import json
import os
import asyncio
import base64
import glob
import platform
import subprocess


import numpy as np
import pyautogui 
import cv2
from ScriptEngine.common.script_engine_utils import is_null, DummyFile

from ..helpers.click_path_generator import ClickPathGenerator
from ..helpers.device_action_interpreter import DeviceActionInterpreter

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from .device_manager import DeviceManager
import mss

script_logger = ScriptLogger()
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

class DesktopDeviceManager(DeviceManager):
    def __init__(self, props, input_source=None):
        script_logger.log('Initializing Python Host')
        self.width = None
        self.height = None
        self.click_width = None
        self.click_height = None
        self.props = props
        self.click_path_generator = None

        self.xmax = self.width
        self.ymax = self.height

        if input_source is not None:
            self.dummy_mode = True
            self.input_source = input_source
        else:
            self.dummy_mode = False
        
        self.scale_factor = 1
        self.app_mapping = self.list_applications()
        
        self.sct = mss.mss()
    
    def set_scale_factor(self, scale_factor):
        self.scale_factor = scale_factor

    def ensure_device_initialized(self):
        if self.width is None or self.height is None:
            if self.dummy_mode:
                self.width = self.input_source["width"]
                self.props['width'] = self.width
                self.height = self.input_source["height"]
                self.props['height'] = self.height
                script_logger.log('PythonHostController: script in dummy mode, initialized to input source')
                return
            script_logger.log('PythonHostController: Taking screenshot to initialize python host')
            host_dimensions = pyautogui.size()
            self.click_width = host_dimensions.width
            self.click_height = host_dimensions.height
            
            self.xmax = self.width
            self.ymax = self.height
            height, width, _ = np.array(pyautogui.screenshot()).shape
            self.width = width
            self.height = height
            if (not is_null(self.props['width']) and (self.props['width'] != width)) or \
                    (not is_null(self.props['height']) and self.props['height'] != height):
                script_logger.log('Warning: python host dims mismatch, expected : ', self.props['height'],
                                  self.props['width'],
                                  'observed :', height, width)
            if self.width != self.click_width or self.height != self.click_height:
                script_logger.log('Difference detected between screenshot dims and clickable dims, setting scale factor to {}'.format(self.click_width / self.width))
                self.scale_factor =  self.click_width / self.width
            self.props['width'] = width
            self.props['height'] = height
            self.click_path_generator = ClickPathGenerator(2, 3, self.width, self.height, 45, 0.4)
    
    def get_status(self):
        return "online"

    def screenshot(self):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning screenshot from input source')
            return self.input_source['screenshot']()
        
        img = np.array(self.sct.grab(self.sct.monitors[1]))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def key_up(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from keyUp')
        pyautogui.keyUp(key)

    def key_down(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from keyDown')
        pyautogui.keyDown(key)

    def key_press(self, key):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from press')
        pyautogui.press(key)

    def hotkey(self, keys):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from hotKey')
        pyautogui.hotkey(*keys)

    def mouse_up(self, x, y, button='left'):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from mouse_up')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('mouse_up: adjusted coords for pyautogui', x, y, flush=True)
        x = int(x * self.scale_factor)
        y = int(y * self.scale_factor)

        current_position = pyautogui.position()
        if current_position != (x, y):
            self.smooth_move(*current_position, x, y)
        pyautogui.mouseUp(x=x, y=y, button=button)


    def mouse_down(self, x, y, button='left'):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from mouse_down')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('mouse_down: adjusted coords for pyautogui', x, y, flush=True)
        x = int(x * self.scale_factor)
        y = int(y * self.scale_factor)

        current_position = pyautogui.position()
        if current_position != (x, y):
            self.smooth_move(*current_position, x, y)
        pyautogui.mouseDown(x=x, y=y, button=button)


    def scroll(self, x, y, distance):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('scroll: adjusted coords for pyautogui', x, y, flush=True)
        x = int(x * self.scale_factor)
        y = int(y * self.scale_factor)
        pyautogui.moveTo(x, y)
        pyautogui.scroll(distance)

    # if the dimensions of your source image are different from the dimensions of pyautogui
    # desktop device manager will not scale to coordinates for you
    # you need to identify what the scale factor is and do this yourself
    # desktop device manager will not be aware of what your source image is
    # however if the dimensions of screenshot and the dimensions of the space clickable is different
    # desktop device manager will automatically scale
    def click(self, x, y, button):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from click')
            return
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     x = (self.width / self.props['width']) * x
        #     y = (self.height / self.props['height']) * y
        #     script_logger.log('clickAction: adjusted coords for pyautogui', x, y, flush=True)
        
        x = int(x * self.scale_factor)
        y = int(y * self.scale_factor)
        
        pyautogui.click(x=x, y=y, button=button)

    def smooth_move(self, source_x, source_y, target_x, target_y, drag=False, button='left'):
        self.ensure_device_initialized()
        # if (self.width != self.props['width'] or self.height != self.props['height']):
        #     source_x = (self.width / self.props['width']) * source_x
        #     source_y = (self.height / self.props['height']) * source_y
        #     target_x = (self.width / self.props['width']) * target_x
        #     target_y = (self.height / self.props['height']) * target_y
        #     script_logger.log('smooth_move: adjusted coords for pyautogui', source_x, source_y, target_x, target_y, flush=True)
        source_x = int(source_x * self.scale_factor)
        source_y = int(source_y * self.scale_factor)
        target_x = int(target_x * self.scale_factor)
        target_y = int(target_y * self.scale_factor)
        
        frac_source_x = (source_x / self.click_width)
        frac_target_x = (target_x / self.click_width)
        frac_source_y = (source_y / self.click_height)
        frac_target_y = (target_y / self.click_height)
        delta_x, delta_y = self.click_path_generator.generate_click_path(
            frac_source_x, frac_source_y,
            frac_target_x, frac_target_y
        )
        if self.dummy_mode:
            script_logger.log('ADB CONTROLLER: script running in dummy mode, adb click and drag returning')
            return delta_x, delta_y

        traverse_x = source_x
        traverse_y = source_y
        for delta_pair in zip(delta_x, delta_y):
            if drag and sys.platform == 'darwin':
                pyautogui.dragTo(
                    traverse_x + delta_pair[0],
                    traverse_y + delta_pair[1],
                    button=button,
                    mouseDownUp=False
                )
            else:
                pyautogui.moveTo(traverse_x + delta_pair[0], traverse_y + delta_pair[1])
            traverse_x += delta_pair[0]
            traverse_y += delta_pair[1]
        return delta_x, delta_y

    def click_and_drag(self, source_x, source_y, target_x, target_y, mouse_down=True, mouse_up=True):
        self.ensure_device_initialized()
        script_logger.log('pyautogui size', pyautogui.size())
        script_logger.log(
            'moving from initial position {} to click and drag start {}'.format(
                str(pyautogui.position()), str((source_x, source_y))
            )
        )

        if mouse_down:
            self.mouse_down(source_x, source_y, button='left')
        delta_x, delta_y = self.smooth_move(source_x, source_y, target_x, target_y, drag=True, button='left')
        if mouse_up:
            self.mouse_up(target_x, target_y, button='left')
        return delta_x, delta_y
    
    def start_application(self, application_name):
        """
        Start an application on the desktop.
        On Mac: uses 'open' command
        On Windows: uses 'start' command
        """
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from start_application')
            return
        
        import subprocess
        import platform
        
        # Look up the application path from the mapping
        if application_name not in self.app_mapping:
            script_logger.log(f'Application "{application_name}" not found in app mapping')
            return
        
        application_path = self.app_mapping[application_name]
        
        try:
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', application_path], check=True)
                script_logger.log(f'Started application on Mac: {application_name} -> {application_path}')
            elif platform.system() == 'Windows':  # Windows
                subprocess.run(['start', '', application_path], shell=True, check=True)
                script_logger.log(f'Started application on Windows: {application_name} -> {application_path}')
            else:
                script_logger.log(f'Unsupported platform for start_application: {platform.system()}')
        except subprocess.CalledProcessError as e:
            script_logger.log(f'Failed to start application {application_name}: {e}')
        except Exception as e:
            script_logger.log(f'Error starting application {application_name}: {e}')
    
    def stop_application(self, application_name):
        """
        Stop an application on the desktop.
        On Mac: uses 'osascript' to quit applications gracefully
        On Windows: uses 'taskkill' command
        """
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from stop_application')
            return
        
        import subprocess
        import platform
        
        # Validate that the application exists in our mapping
        if application_name not in self.app_mapping:
            script_logger.log(f'Application "{application_name}" not found in app mapping')
            return
        
        try:
            if platform.system() == 'Darwin':  # macOS
                # Use osascript to quit the application gracefully
                applescript = f'tell application "{application_name}" to quit'
                subprocess.run(['osascript', '-e', applescript], check=True)
                script_logger.log(f'Stopped application on Mac: {application_name}')
            elif platform.system() == 'Windows':  # Windows
                subprocess.run(['taskkill', '/f', '/im', f'{application_name}.exe'], check=True)
                script_logger.log(f'Stopped application on Windows: {application_name}')
            else:
                script_logger.log(f'Unsupported platform for stop_application: {platform.system()}')
        except subprocess.CalledProcessError as e:
            script_logger.log(f'Failed to stop application {application_name}: {e}')
        except Exception as e:
            script_logger.log(f'Error stopping application {application_name}: {e}')
    
    def list_applications(self):
        """
        List installed applications on the desktop.
        On Mac: lists applications from ~/Applications and /Applications
        On Windows: lists applications from Start Menu shortcuts
        """
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('PythonHostController: script in dummy mode, returning from list_applications')
            return {}
        
        apps = {}
        
        try:
            if platform.system() == 'Darwin':  # macOS
                # List applications from user's Applications folder
                user_apps_path = os.path.expanduser('~/Applications')
                if os.path.exists(user_apps_path):
                    for app in os.listdir(user_apps_path):
                        if app.endswith('.app'):
                            app_name = os.path.splitext(app)[0]
                            apps[app_name] = os.path.join(user_apps_path, app)
                
                # List applications from system Applications folder
                system_apps_path = '/Applications'
                if os.path.exists(system_apps_path):
                    for app in os.listdir(system_apps_path):
                        if app.endswith('.app'):
                            app_name = os.path.splitext(app)[0]
                            apps[app_name] = os.path.join(system_apps_path, app)
                
                script_logger.log(f'Found {len(apps)} applications on macOS')
                
            elif platform.system() == 'Windows':  # Windows
                # Start Menu locations (system-wide + user)
                start_menu_paths = [
                    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
                    os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")
                ]
                
                for path in start_menu_paths:
                    if os.path.exists(path):
                        for lnk in glob.glob(path + r"\**\*.lnk", recursive=True):
                            name = os.path.splitext(os.path.basename(lnk))[0]
                            apps[name] = lnk
                
                script_logger.log(f'Found {len(apps)} applications on Windows')
                
            else:
                script_logger.log(f'Unsupported platform for list_applications: {platform.system()}')
                
        except Exception as e:
            script_logger.log(f'Error listing applications: {e}')
        
        return apps
    
    def start_device(self):
        return super().start_device()
    
    def stop_device(self):
        return super().stop_device()

    

def parse_inputs(process_host, inputs):
    device_action = inputs[2]
    if device_action == 'screen_capture':
        screenshot = process_host.screenshot()
        _, buffer = cv2.imencode('.jpg', screenshot)
        byte_array = buffer.tobytes()
        base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
        return {
            "data": base64_encoded_string
        }
    elif device_action == "click":
        process_host.ensure_device_initialized()
        script_logger.log('clicked location', inputs[3], inputs[4], flush=True)
        process_host.click(int(float(inputs[3])), int(float(inputs[4])), 'left')
        return {
            "data" : "success"
        }
    elif device_action == "click_and_drag":
        # process_host.click_and_drag(inputs[3], inputs[4], inputs[5], inputs[6])
        script_logger.log('click and drag not implemented on python host')
        process_host.ensure_device_initialized()
        return {
            "data" : "failure"
        }
    elif device_action == "send_keys":
        DeviceActionInterpreter.parse_keyboard_action(
            process_host, json.loads(inputs[3]), {}, {}
        )
        return {
            "data": "success"
        }



async def read_input():
    script_logger.log("PYTHON CONTROLLER PROCESS: listening for input")
    process_python_host = None
    device_key = None
    while True:
        input_line = await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = input_line.strip().split('###')
        inputs = inputs[0:2] + inputs[2].split(' ')
        script_logger.log('PYTHON CONTROLLER PROCESS: received inputs ', inputs)
        if device_key is None:
            device_key = inputs[1]
        elif device_key != inputs[1]:
            script_logger.log('PYTHON CONTROLLER: device key mismatch ', device_key, inputs[1])
            continue
        if process_python_host is None:
            script_logger.set_log_file_path('./logs/{}-python-host-controller-{}-process.txt'.format(formatted_today, device_key.replace(':', '-')))
            script_logger.log('PYTHON CONTROLLER PROCESS: starting process for device {}'.format(device_key))
            script_logger.log('PYTHON CONTROLLER PROCESS: processing inputs ', inputs)
            script_logger.set_log_header('{}-python-host-controller-{}-process'.format(formatted_today, device_key.replace(':', '-')))
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
            process_python_host = DesktopDeviceManager({
                "dir_path": "./",
                "width" : None,
                "height" : None,
                "scriptMode" : 'train'
            }, None)
        if len(inputs) > 1:
            try:
                script_logger.log('<--{}-->'.format(inputs[0]) + json.dumps(parse_inputs(process_python_host, inputs)) + '<--{}-->'.format(inputs[0]), file=DummyFile(), flush=True)
                script_logger.log('PYTHON CONTROLLER: Response sent for {}'.format(inputs[0]), flush=True)
            except pyautogui.FailSafeException as e:
                script_logger.log('PYTHON CONTROLLER PROCESS: fail safe exception triggered', e)

async def python_controller_main():
    await asyncio.gather(read_input())

if __name__ == '__main__':
    script_logger.set_log_file_path('./logs/{}-python-host-main.txt'.format(formatted_today))
    script_logger.set_log_header('{}-python-host-main-'.format(formatted_today))
    script_logger.set_log_folder('./logs/')
    os.makedirs('./logs', exist_ok=True)
    asyncio.run(python_controller_main())