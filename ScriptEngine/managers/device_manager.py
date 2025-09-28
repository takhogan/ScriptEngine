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

from abc import ABC, abstractmethod


class DeviceManager(ABC):

    @abstractmethod
    def ensure_device_initialized(self):
        raise NotImplementedError(f"ensure_device_initialized not implemented for {self.__class__.__name__}")

    @abstractmethod
    def get_status(self):
        raise NotImplementedError(f"get_status not implemented for {self.__class__.__name__}")

    @abstractmethod
    def screenshot(self):
        raise NotImplementedError(f"screenshot not implemented for {self.__class__.__name__}")

    @abstractmethod
    def key_down(self):
        raise NotImplementedError(f"key_down not implemented for {self.__class__.__name__}")

    @abstractmethod
    def key_up(self):
        raise NotImplementedError(f"key_up not implemented for {self.__class__.__name__}")

    @abstractmethod
    def key_press(self):
        raise NotImplementedError(f"key press not implemented for {self.__class__.__name__}")

    @abstractmethod
    def hotkey(self):
        raise NotImplementedError(f"hotkey not implemented for {self.__class__.__name__}")

    @abstractmethod
    def mouse_down(self):
        raise NotImplementedError(f"mouse_down not implemented for {self.__class__.__name__}")

    @abstractmethod
    def mouse_up(self):
        raise NotImplementedError(f"mouse_up not implemented for {self.__class__.__name__}")

    @abstractmethod
    def smooth_move(self):
        raise NotImplementedError(f"mouse_move not implemented for {self.__class__.__name__}")

    @abstractmethod
    def click(self):
        raise NotImplementedError(f"click not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def click_and_drag(self):
        raise NotImplementedError(f"click_and_drag not implemented for {self.__class__.__name__}")

    @abstractmethod
    def scroll(self):
        raise NotImplementedError(f"scroll not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def start_device(self):
        raise NotImplementedError(f"start_device not implemented for {self.__class__.__name__}")

    @abstractmethod
    def stop_device(self):
        raise NotImplementedError(f"stop_device not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def start_application(self, application_path):
        raise NotImplementedError(f"start_application not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def stop_application(self, application_name):
        raise NotImplementedError(f"stop_application not implemented for {self.__class__.__name__}")