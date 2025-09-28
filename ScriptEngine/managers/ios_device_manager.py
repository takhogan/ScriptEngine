
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

from pymobiledevice3.tunneld.api import async_get_tunneld_devices
from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot

from ..clients.sudo_client import SudoClient
import asyncio
import time

from pymobiledevice3.tunneld.api import async_get_tunneld_devices
from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
from .device_manager import DeviceManager

class IOSDeviceManager(DeviceManager):
    def __init__(self, sudo_client: SudoClient):
        """Initialize connection to iOS device through tunnel"""
        # sudo_client.run_as_root("pymobiledevice3 remote tunneld")
        # time.sleep(10)

        # Use asyncio.run() to handle the await
        rsds = asyncio.run(async_get_tunneld_devices())
        
        print("Connected devices:", rsds)
        if not rsds:
            raise RuntimeError("No iOS devices found")
            
        device = rsds[0]
        print("Device info:", device.product_version, type(device))
        self.lockdown = device
        # self.connection = device.start_lockdown_developer_service('com.apple.mobile.screenshotr')
        # for entry in OsTraceService(device).syslog():
        #     print(entry)

    def take_screenshot(self):
        """Takes a screenshot of the iOS device and returns the PNG data"""
        dvt = DvtSecureSocketProxyService(lockdown=self.lockdown)
        screenshot_data = Screenshot(dvt)
        return screenshot_data
    
    def start_application(self, application_path):
        """Start an application on iOS device - not implemented"""
        print(f"IOSDeviceManager: start_application not implemented for iOS - {application_path}")
        pass
    
    def stop_application(self, application_name):
        """Stop an application on iOS device - not implemented"""
        print(f"IOSDeviceManager: stop_application not implemented for iOS - {application_name}")
        pass

if __name__ == "__main__":
    with SudoClient() as sudo_client:
        ios_client = IOSDeviceManager(sudo_client)
        screenshot_data = ios_client.take_screenshot()
        screenshot_data.get_screenshot()