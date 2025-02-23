
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

if __name__ == "__main__":
    with SudoClient() as sudo_client:
        ios_client = IOSDeviceManager(sudo_client)
        screenshot_data = ios_client.take_screenshot()
        screenshot_data.get_screenshot()