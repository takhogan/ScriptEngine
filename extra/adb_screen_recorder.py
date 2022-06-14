import cv2
import subprocess

import pyautogui
from PIL import Image
from io import BytesIO
import time
import numpy as np
import tkinter as tk
import os,select,sys
import scipy.misc
import threading

class ScreenRecorderApp:
    def __init__(self):
        self.app = tk.Tk()
        self.app.geometry("200x200")
        self.app_state = {
            "record_pc_button_active": False,
            "record_adb_button_active": False,
            "record_button_active": False
        }
        self.record_pc_button = tk.Button(
            self.app,
            text="PC",
            command=self.on_button_pressed_generator('record_pc_button'),
            bg='#e8e8e8'
        )
        self.record_adb_button = tk.Button(
            self.app,
            text="adb",
            command=self.on_button_pressed_generator('record_adb_button'),
            bg='#e8e8e8'
        )
        self.record_button = tk.Button(
            self.app,
            text="Record",
            command=self.on_button_pressed_generator('record_button'),
            bg='#e8e8e8'
        )

        self.buttons = {
            "record_pc_button": self.record_pc_button,
            "record_adb_button": self.record_adb_button,
            "record_button": self.record_button
        }

        self.record_pc_button.pack()
        self.record_adb_button.pack()
        self.record_button.pack()

        self.status_message = tk.Message(self.app, text="")

        self.recorder = ScreenRecorder()

        self.app.mainloop()


    def apply_button_styles(self):
        for button_key in self.buttons:
            if self.app_state[button_key + '_active']:
                self.buttons[button_key]['bg'] = '#575757'
            else:
                self.buttons[button_key]['bg'] = '#e8e8e8'

    def handle_state(self):
        if self.app_state["record_pc_button_active"] and self.app_state["record_adb_button_active"]:
            self.status_message["text"] = "You can only choose one recording source"
        elif not self.app_state["record_pc_button_active"] and not self.app_state["record_adb_button_active"]:
            self.status_message["text"] = "Please choose a recording source"
        else:
            self.status_message["text"] = ""
            if self.app_state["record_button_active"]:
                self.recorder.start_recording('pc' if self.app_state["record_pc_button_active"] else 'adb' if self.app_state["record_adb_button_active"] else '')
            else:
                self.recorder.stop_recording()

        self.apply_button_styles()



    def on_button_pressed_generator(self, pressed_button_key):
        def on_button_pressed():
            if self.app_state[pressed_button_key + '_active']:
                self.app_state[pressed_button_key + '_active'] = False
            else:
                self.app_state[pressed_button_key + '_active'] = True
            self.handle_state()

        return on_button_pressed

# self.adb_path = 'adb'
#         self.adb_ip = '127.0.0.1:5555'
#         self.recording_started = False
#         self.recording_type = recording_type
#
#
#         devices_output = bytes.decode(subprocess.run(self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')
#         emualator_active = (
#                 'emulator' in
#                 bytes.decode(subprocess.run(
#                     self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')) \
#             if not 'started' in devices_output else 'emulator' in devices_output
#         if not emualator_active:
#             subprocess.run(self.adb_path + ' connect ' + self.adb_ip, cwd="/", shell=True)
#         source_im = np.array(Image.open(BytesIO(subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True).stdout)))
#         self.width = source_im.shape[1]
#         self.height = source_im.shape[0]

class ScreenRecorder:
    def __init__(self):
        self.recording_started = False
        self.recording_type = None
        self.recording_thread = None

    def start_recording(self, recording_type):
        self.recording_type = recording_type
        if not self.recording_started:
            self.recording_thread = RecordingThread(self.recording_type)
            self.recording_thread.start()
            self.recording_started = True

    def stop_recording(self):
        if self.recording_started:
            self.recording_thread.end_recording()
            self.recording_thread.join()
            self.recording_started = False

class RecordingThread(threading.Thread):
    def __init__(self, recording_mode):
        threading.Thread.__init__(self)
        self.recording_mode = recording_mode
        self.record = True
        self.height,self.width,_ = np.array(pyautogui.screenshot()).shape

    def run(self):
        recording_codec = 'mp42'
        out_writer = cv2.VideoWriter("./data/output.mp4", cv2.VideoWriter_fourcc(*recording_codec), 8.0,
                                     (self.width, self.height))
        print('recording...')
        while self.record:
            time.sleep(0.1)
            if self.recording_mode == 'adb':
                input_im = np.array(Image.open(BytesIO(
                    subprocess.run('adb exec-out screencap -p', cwd="/", shell=True,
                                   capture_output=True).stdout)))
            elif self.recording_mode == 'pc':
                input_im = np.array(pyautogui.screenshot())
            input_im_bgr = cv2.cvtColor(input_im, cv2.COLOR_RGB2BGR)
            out_writer.write(input_im_bgr)
        print('recording complete.')
        out_writer.release()
        cv2.destroyAllWindows()
        print('recording saved.')

    def end_recording(self):
        self.record = False

if __name__=='__main__':
    screen_recorder = ScreenRecorderApp()