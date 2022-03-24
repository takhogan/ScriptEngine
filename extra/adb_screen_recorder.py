import cv2
import subprocess
from PIL import Image
from io import BytesIO
import time
import numpy as np
import os,select,sys
import scipy.misc

class adb_screen_recorder:
    def __init__(self, adb_path, adb_ip):
        self.adb_path = adb_path
        devices_output = bytes.decode(subprocess.run(self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')
        emualator_active = (
                'emulator' in
                bytes.decode(subprocess.run(
                    self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')) \
            if not 'started' in devices_output else 'emulator' in devices_output
        if not emualator_active:
            subprocess.run(self.adb_path + ' connect ' + adb_ip, cwd="/", shell=True)
        source_im = np.array(Image.open(BytesIO(subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True).stdout)))
        self.width = source_im.shape[1]
        self.height = source_im.shape[0]

    def record(self, mode):
        if mode == 'screencapture':
            pass
        elif mode == 'screenshot':
            out_writer = cv2.VideoWriter("output.mp4", cv2.VideoWriter_fourcc(*'mp42'), 4.0, (self.width, self.height))
            print('recording...')
            video_writer_active = True
            while video_writer_active:
                try:
                    time.sleep(0.25)
                    input_im = np.array(Image.open(BytesIO(subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True).stdout)))
                    input_im_rgb = cv2.cvtColor(input_im, cv2.COLOR_BGR2RGB)
                    out_writer.write(input_im_rgb)
                except KeyboardInterrupt:
                    video_writer_active = False
            print('recording complete.')
            out_writer.release()
            cv2.destroyAllWindows()

            # except KeyboardInterrupt:
                # pass
        else:
            print('mode not implemented ' + mode)


if __name__=='__main__':
    recorder = adb_screen_recorder('adb', '127.0.0.1:5555')
    recorder.record(mode='screenshot')