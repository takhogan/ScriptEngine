from .device_manager import DeviceManager
from pikvm_lib import PiKVMWebsocket,PiKVM


class PikvmDeviceManager(DeviceManager):
    def __init__(self, hostname, username, password):
        self.websocket = PiKVMWebsocket(hostname, username, password)
        self.instance = PiKVM(hostname, username, password)

    def start_device(self):
        return self.instance.set_atx_power(action="on")
    
    def stop_device(self):
        return self.instance.set_atx_power(action="off")
    
    def screenshot(self):
        return self.instance.get_streamer_image()
    
    def keyDown(self, key):
        return self.websocket.send_key(key)
    
    def keyUp(self):
        return super().keyUp()
    
    def keyPress(self, key):
        return self.websocket.send_key_press(key)
    
    def hotkey(self):
        return super().hotkey()
    
    def mouse_down(self):
        return super().mouse_down()
    
    def mouse_up(self):
        return super().mouse_up()
    
    def smooth_move(self):
        return super().smooth_move()
    
    def click(self):
        return super().click()
    
    def click_and_drag(self):
        return super().click_and_drag()
    
    def scroll(self):
        return super().scroll()
    
