from .device_manager import DeviceManager
from pikvm_lib import PiKVMWebsocket,PiKVM
import cv2
import numpy
from ScriptEngine.common.logging import script_logger


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
    
    def ensure_device_initialized(self):
        if self.width is None or self.height is None:
            if self.dummy_mode:
                self.width = self.input_source["width"]
                self.height = self.input_source["height"]
                script_logger.log('PiKVMDeviceManager: script in dummy mode, initialized to input source')
                return
            screenshot = self.screenshot()
            self.width = screenshot.shape[1]
            self.height = screenshot.shape[0]
    
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
        print(f"hotkey: {keys}")
        return self.instance.hotkey(*keys)
    
    def mouse_down(self, x, y, button="left"):
        self.smooth_move(x, y)
        return self.instance.send_mouse_event(button, "true")
    
    def mouse_up(self, x, y, button="left"):
        self.smooth_move(x, y)
        return self.instance.send_mouse_event(button, "false")
    
    def smooth_move(self, x, y):
        return self.instance.send_mouse_move_event(x, y)
    
    def click(self, x, y, button="left"):
        self.smooth_move(x, y)
        return self.instance.send_click(button)
    
    def click_and_drag(self, x1, y1, x2, y2):
        self.mouse_down(x1, y1)
        self.smooth_move(x2, y2)
        self.mouse_up(x2, y2)
    
    def scroll(self, delta):
        return self.instance.send_mouse_wheel_event(delta)
    
