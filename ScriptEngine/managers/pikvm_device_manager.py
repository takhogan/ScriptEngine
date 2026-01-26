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

from .device_manager import DeviceManager
from typing import List

from pikvm_lib import PiKVM
import cv2
import numpy
import time
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.helpers.click_path_generator import ClickPathGenerator

script_logger = ScriptLogger()

class PiKVMDeviceManager(DeviceManager):
    def __init__(self, hostname, username, password, input_source=None):
        self.instance = PiKVM(hostname, username, password)
        if input_source is not None:
            self.input_source = input_source
            self.dummy_mode = True
        else:
            self.dummy_mode = False
        self.width = None
        self.height = None
        self.xmax = None
        self.ymax = None

    
    def ensure_device_initialized(self):
        if self.width is None or self.height is None:
            if self.dummy_mode:
                self.width = self.input_source["width"]
                self.height = self.input_source["height"]
                self.xmax = self.width
                self.ymax = self.height
                script_logger.log('PiKVMDeviceManager: script in dummy mode, initialized to input source')
                return
            screenshot = self.screenshot()
            self.width = screenshot.shape[1]
            self.height = screenshot.shape[0]
            self.xmax = self.width
            self.ymax = self.height
            self.click_path_generator = ClickPathGenerator(2, 3, self.width, self.height, 45, 0.4)

    
    def get_status(self):
        try:
            screenshot = self.screenshot()
            return "online"
        except Exception as e:
            script_logger.log('PiKVMDeviceManager: get_status', e)
            return "offline"

    def start_device(self):
        return self.instance.set_atx_power(action="on")
    
    def stop_device(self):
        return self.instance.set_atx_power(action="off")
    
    def screenshot(self):
        pil_image = self.instance.get_streamer_image()
        cv2_image = cv2.cvtColor(numpy.array(pil_image), cv2.COLOR_RGB2BGR)
        return cv2_image
    
    def key_down(self, key):
        
        return self.instance.keyDown(key)
    
    def key_up(self, key):
        return self.instance.keyUp(key)
    
    def key_press(self, key):
        return self.instance.press(key)
    
    def hotkey(self, *keys):
        return self.instance.hotkey(*keys)
    
    def mouse_down(self, x, y, button="left"):
        self.instance.send_mouse_move_event(x, y)
        return self.instance.send_mouse_event(button, "true")
    
    def mouse_up(self, x, y, button="left"):
        self.instance.send_mouse_move_event(x, y)
        return self.instance.send_mouse_event(button, "false")
    
    def smooth_move(self, source_x, source_y, target_x, target_y, drag=False,button="left"):
        frac_source_x = (source_x / self.width)
        frac_target_x = (target_x / self.width)
        frac_source_y = (source_y / self.height)
        frac_target_y = (target_y / self.height)
        delta_x, delta_y = self.click_path_generator.generate_click_path(
            frac_source_x, frac_source_y,
            frac_target_x, frac_target_y
        )
        if self.dummy_mode:
            script_logger.log('PiKVM CONTROLLER: script running in dummy mode, adb click and drag returning')
            return delta_x, delta_y

        traverse_x = source_x
        traverse_y = source_y
        for delta_pair in zip(delta_x, delta_y):
            self.instance.send_mouse_move_event(traverse_x + delta_pair[0], traverse_y + delta_pair[1])
            traverse_x += delta_pair[0]
            traverse_y += delta_pair[1]
        script_logger.log(f'PiKVM CONTROLLER: smooth move ${str(frac_source_x)}, ${str(frac_source_y)}, ${str(frac_target_x)}, ${str(frac_target_y)}=', )
        return delta_x, delta_y
    
    def click(self, x, y, button="left"):
        self.instance.send_mouse_move_event(x, y)
        return self.instance.send_click(button)
    
    def click_and_drag(self, x1, y1, x2, y2, mouse_down=True, mouse_up=True):
        if mouse_down:
            self.mouse_down(x1, y1)
        delta_x, delta_y = self.smooth_move(x1, y1, x2, y2)
        if mouse_up:
            self.mouse_up(x2, y2)
        return delta_x, delta_y
    
    def scroll(self, delta):
        return self.instance.send_mouse_wheel_event(delta)
    
    def list_applications(self) -> dict[str, str]:
        """List installed applications on PiKVM device - not implemented"""
        script_logger.log(f"PiKVMDeviceManager: list_applications not implemented for PiKVM")
        return {}
    
    def start_application(self, application_path : str, args : List[str] | None):
        """Start an application on PiKVM device - not implemented"""
        script_logger.log(f"PiKVMDeviceManager: start_application not implemented for PiKVM - {application_path}")
        pass
    
    def stop_application(self, application_name):
        """Stop an application on PiKVM device - not implemented"""
        script_logger.log(f"PiKVMDeviceManager: stop_application not implemented for PiKVM - {application_name}")
        pass
    
