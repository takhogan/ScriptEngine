import base64
import datetime
import math
import subprocess

import shutil
from PIL import Image
from PIL import UnidentifiedImageError
from io import BytesIO
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
import random
import time
import sys
from scipy.stats import truncnorm
from script_engine_utils import get_glob_digit_regex_string, is_null, masked_mse
from os import path
import os
import glob
import itertools
import pyautogui

sys.path.append("..")
from script_execution_state import ScriptExecutionState
from click_path_generator import ClickPathGenerator
from image_matcher import ImageMatcher
from search_pattern_helper import SearchPatternHelper
from click_action_helper import ClickActionHelper
from detect_scene_helper import DetectSceneHelper
from detect_object_helper import DetectObjectHelper
from forward_detect_peek_helper import ForwardDetectPeekHelper

KEYBOARD_KEYS = set(pyautogui.KEYBOARD_KEYS)

class adb_host:
    def __init__(self, props, host_os, adb_ip):
        self.device_profile = 'windows-bluestacks'
        self.host_os = host_os
        self.image_matcher = ImageMatcher()
        self.search_pattern_helper = SearchPatternHelper()
        self.adb_path = props["adbPath"]
        self.emulator_path = props["emulatorPath"]
        self.device_name = props["deviceName"]
        self.props = props
        self.adb_ip = adb_ip
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
        self.sendevent_command = 'sendevent /dev/input/event5 {} {} {};'
        self.commands = {
            "tracking_id_mousedown": self.sendevent_command.format(3, int('39', 16), 0),
            "touch_major_func": lambda: self.sendevent_command.format(3, int('30', 16), self.event_counter),
            "abs_mt_pressure_down" : self.sendevent_command.format(3, int('3a', 16), int('81', 16)),
            "x_command_func" : lambda x_val: self.sendevent_command.format(3, int('35',16), x_val),
            "y_command_func" : lambda y_val: self.sendevent_command.format(3, int('36',16), y_val),
            "action_terminate_command" : self.sendevent_command.format(0, 0, 0),
            "abs_mt_pressure_up" : self.sendevent_command.format(3, int('3a', 16), 0),
            "tracking_id_mouseup" : self.sendevent_command.format(3, int('39', 16), '-1'),
            "syn_mt_report" : self.sendevent_command.format(0, 2, 0)
        }
        self.props['scriptMode'] = 'train'



    def init_system(self, reinitialize=False):
        source_im = None
        if reinitialize or self.width is None or self.height is None:
            get_device_list = lambda: subprocess.run(self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True)
            devices_output = bytes.decode(get_device_list().stdout, 'utf-8')
            if not 'started' in devices_output:
                devices_output = bytes.decode(get_device_list().stdout, 'utf-8')
            run_kill_command = lambda: subprocess.run(self.adb_path + ' kill-server', cwd="/", shell=True)
            if 'offline' in devices_output:
                run_kill_command()
                get_device_list()
            if 'emulator' in devices_output and '127.0.0.1:5555' in devices_output:
                run_kill_command()
                get_device_list()
            emualator_active = (
                'emulator' in devices_output or
                '127.0.0.1:5555' in devices_output
            )
            run_connect_command = lambda: subprocess.run(self.adb_path + ' connect ' + self.adb_ip, cwd="/", shell=True)
            if not emualator_active:
                print('connecting to')
                run_connect_command()


            get_im_command = subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True)
            bytes_im = BytesIO(get_im_command.stdout)
            try:
                source_im = np.array(Image.open(bytes_im))
            except UnidentifiedImageError:
                print('get_im_command: ', get_im_command)
                exit(1)
            self.width = source_im.shape[1]
            self.height = source_im.shape[0]
        if is_null(self.props['width']):
            self.props['width'] = self.width
        if is_null(self.props['height']):
            self.props['height'] = self.height
        return source_im

    def screenshot(self):
        get_im_command = subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True,
                                        capture_output=True)
        bytes_im = BytesIO(get_im_command.stdout)
        try:
            source_im = Image.open(bytes_im)
        except UnidentifiedImageError:
            print('get_im_command: ', get_im_command)
            source_im = self.init_system(reinitialize=True)
            if source_im is None:
                exit(1)
        return cv2.cvtColor(np.array(source_im), cv2.COLOR_RGB2BGR)

    def save_screenshot(self, save_name):
        pass

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
        shell_process = subprocess.Popen(['adb', 'shell'], stdin=subprocess.PIPE)
        shell_process.communicate((''.join(click_command)).encode('utf-8'))
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
        shell_process = subprocess.Popen([self.adb_path, 'shell'],
                                         stdin=subprocess.PIPE)
        shell_process.communicate((''.join(command_string)).encode('utf-8'))
        # print((''.join(command_string)).encode('utf-8'))
        self.event_counter += 1

    def handle_action(self, action, state, context, log_level, log_folder):
        logs_path = log_folder + str(context['script_counter']) + '-'
        # if action["actionName"] == "declareScene":
        #     forward_peek_result = ForwardDetectPeekHelper.load_forward_peek_result(action, state, context)
        #     if forward_peek_result is not None:
        #         return forward_peek_result
        #
        #     # screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
        #     screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, None)
        #     if screencap_im_bgr is None:
        #         screencap_im_bgr = self.screenshot()
        #     print('detectorAttributes', action['actionData']['detectorAttributes'])
        #     matches,ssim_coeff = DetectSceneHelper.get_match(
        #         action,
        #         screencap_im_bgr.copy(),
        #         action["actionData"]["positiveExamples"][0]["img"],
        #         action["actionData"]["positiveExamples"][0]["mask"],
        #         action["actionData"]["positiveExamples"][0]["mask_single_channel"],
        #         self.props["dir_path"],
        #         logs_path,
        #         output_cropping=action["actionData"]["maskLocation"] if
        #         (action["actionData"]["maskLocation"] != 'null' and
        #          "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
        #          ) else None,
        #     )
        #     if ssim_coeff > action["actionData"]["threshold"]:
        #         state[action["actionData"]["outputVarName"]] = matches
        #         action_result = ScriptExecutionState.SUCCESS
        #     else:
        #         action_result = ScriptExecutionState.FAILURE
        #     action, context = ForwardDetectPeekHelper.save_forward_peek_results(action, {}, action_result, context)
        #     return action_result, state, context

        if action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/
            forward_peek_result = ForwardDetectPeekHelper.load_forward_peek_result(action, state, context)
            if forward_peek_result is not None:
                return forward_peek_result

            screencap_im_bgr, match_point = DetectObjectHelper.get_detect_area(action, state)
            # print('get_detect_result', match_point, screencap_im_bgr.shape if screencap_im_bgr is not None else 'none')
            check_image_scale = screencap_im_bgr is None
            screencap_im_bgr = ForwardDetectPeekHelper.load_screencap_im_bgr(action, screencap_im_bgr)
            if screencap_im_bgr is None:
                screencap_im_bgr = self.screenshot()
            # print('post transform: ', screencap_im_bgr.shape)

            screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + str(action['actionGroup']) + '-search_img.png', screencap_search_bgr)
            is_detect_object_first_match = (action['actionData']['detectActionType'] == 'detectObject' and action['actionData']['matchMode'] == 'firstMatch')

            if is_detect_object_first_match or\
                action['actionData']['detectActionType'] == 'detectScene':
                matches,ssim_coeff = DetectSceneHelper.get_match(
                    action,
                    screencap_im_bgr.copy(),
                    action["actionData"]["positiveExamples"][0]["sceneimg"],
                    action["actionData"]["positiveExamples"][0]["scenemask"],
                    action["actionData"]["positiveExamples"][0]["scenemask_single_channel"],
                    action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                    action["actionData"]["positiveExamples"][0]["outputMask"],
                    self.props["dir_path"],
                    logs_path,
                    output_cropping=action["actionData"]["maskLocation"] if
                    (action["actionData"]["maskLocation"] != 'null' and
                     "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                    ) else None
                )
                if ssim_coeff < float(action["actionData"]["threshold"]):
                    matches = []

            if (action['actionData']['detectActionType'] == 'detectObject' and action['actionData']['matchMode'] == 'bestMatch') or \
                    (is_detect_object_first_match and len(matches) == 0):
                matches = self.image_matcher.template_match(
                    action,
                    screencap_im_bgr,
                    screencap_search_bgr,
                    action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                    action["actionData"]["positiveExamples"][0]["outputMask"],
                    action["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
                    action['actionData']['detectorName'],
                    logs_path,
                    self.props["scriptMode"],
                    match_point,
                    check_image_scale=check_image_scale,
                    output_cropping=action["actionData"]["maskLocation"] if
                    (action["actionData"]["maskLocation"] != 'null' and
                     "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                     ) else None,
                    threshold=float(action["actionData"]["threshold"]),
                    use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
                )


            # exit(0)
            if len(matches) > 0:
                state, context, update_dict = DetectObjectHelper.append_to_run_queue(
                    action, state, context, matches,
                    action['actionData']['detect_run_type'] if 'detect_run_type' in action['actionData'] else 'normal'
                )
                action_result = ScriptExecutionState.SUCCESS
            else:
                update_dict = {}
                action_result = ScriptExecutionState.FAILURE
            action, context = ForwardDetectPeekHelper.save_forward_peek_results(action, update_dict, action_result, context)
            return action_result, state, context

        elif action["actionName"] == "clickAction":
            var_name = action["actionData"]["inputExpression"]
            point_choice,state,context = ClickActionHelper.get_point_choice(action, var_name, state, context)
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

            ClickActionHelper.draw_click(self.screenshot(), point_choice, logs_path)
            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1])
                time.sleep(delays[click_count])


            return ScriptExecutionState.SUCCESS, state, context

        elif action["actionName"] == "shellScript":
            if self.host_os is not None:
                state = self.host_os.run_script(action, state)
                return ScriptExecutionState.SUCCESS, state, context

        elif action["actionName"] == "conditionalStatement":
            if eval(action["actionData"]["condition"], state):
                print('condition success!')
                return ScriptExecutionState.SUCCESS, state, context
            else:
                print('condition failure!')
                return ScriptExecutionState.FAILURE, state, context
        elif action["actionName"] == "sleepStatement":
            if str(action["actionData"]["inputExpression"]).strip() == '':
                time.sleep(float(eval(str(action["actionData"]["inputExpression"]), state)))
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "dragLocationSource":
            source_point = random.choice(action["actionData"]["pointList"])
            print(action["actionData"]["inputExpression"])
            if not action["actionData"]["inputExpression"] == "null" and action["actionData"]["inputExpression"] is not None:
                source_point = eval(action["actionData"]["inputExpression"], state)
                print('dragLocationSource : reading input expression ', action["actionData"]["inputExpression"])
            context["dragLocationSource"] = source_point
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "dragLocationTarget":
            source_point = context["dragLocationSource"]
            target_point = random.choice(action["actionData"]["pointList"])
            if not action["actionData"]["inputExpression"] == "null" and action["actionData"]["inputExpression"] is not None:
                print('dragLocationTarget : reading input expression ', action["actionData"]["inputExpression"])
                target_point = eval(action["actionData"]["inputExpression"], state)
            print('dragLocationTarget: dragging from ', source_point, ' to ', target_point)
            self.click_and_drag(source_point[0], source_point[1], target_point[0], target_point[1])
            del context["dragLocationSource"]
            # print(source_point)
            # print(target_point)
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "searchPatternStartAction":
            context = self.search_pattern_helper.generate_pattern(action, context, log_folder, self.props['dir_path'])
            # print(state)
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "searchPatternContinueAction":
            search_pattern_id = action["actionData"]["searchPatternID"]
            raw_source_pt, raw_target_pt, displacement, context = self.search_pattern_helper.execute_pattern(search_pattern_id, context)
            search_pattern_obj = context["search_patterns"][search_pattern_id]
            step_index = search_pattern_obj["step_index"]
            fitted_patterns = self.search_pattern_helper.fit_pattern_to_frame(self.width, self.height, search_pattern_obj["draggable_area"], [(raw_source_pt, raw_target_pt)])

            # print(search_pattern_obj["draggable_area"].shape)
            # print(cv2.cvtColor(np.array(self.screenshot()), cv2.COLOR_BGR2RGB).shape)
            # exit(0)
            def apply_draggable_area_mask(img):
                return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))

            def create_and_save_screencap(self_ref, savename):
                img_unmasked_bgr = self.screenshot()
                img_masked_bgr = apply_draggable_area_mask(img_unmasked_bgr)
                cv2.imwrite(
                    savename,
                    img_masked_bgr
                )
                return img_masked_bgr

            def read_and_apply_mask(img_path):
                return apply_draggable_area_mask(cv2.imread(img_path))

            log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1)
            def get_longest_path(search_string):
                search_result = remove_forward_slashes(glob.glob(search_string))
                if len(search_result) > 1:
                    search_path_lens = list(map(len, search_result))
                    max_search_path_len = max(search_path_lens)
                    max_search_path = search_result[search_path_lens.index(max_search_path_len)]
                else:
                    max_search_path = search_result[0]
                return max_search_path

            def record_movement(search_pattern_obj, x_displacement, y_displacement):
                curr_x,curr_y = search_pattern_obj["actual_current_point"]
                base_displacement_is_x = x_displacement > y_displacement
                slope = y_displacement / x_displacement
                if base_displacement_is_x:
                    base_5_curr_x = curr_x // 5
                    base_5_displaced_x = (curr_x + x_displacement) // 5
                    displacement_range = range(base_5_curr_x, base_5_displaced_x, int(math.copysign(1, base_5_displaced_x - base_5_curr_x)))
                    displacement_func = lambda displacement_leg: (slope * (displacement_leg - x_displacement) + y_displacement) // 5
                else:
                    base_5_curr_y = curr_y // 5
                    base_5_displaced_y = (curr_y + y_displacement) // 5
                    displacement_range = range(base_5_curr_y, base_5_displaced_y,
                                               int(math.copysign(1, base_5_displaced_y - base_5_curr_y)))
                    displacement_func = lambda displacement_leg: (((displacement_leg - y_displacement) / slope) + x_displacement) // 5
                for displacement_leg in displacement_range:
                    displacement_leg_dependant = displacement_func(displacement_leg)
                    locations = [
                        (displacement_leg * 5, displacement_leg_dependant * 5),
                        (displacement_leg * 5, displacement_leg_dependant * 5 + 1),
                        (displacement_leg * 5, displacement_leg_dependant * 5 - 1)
                    ] if base_displacement_is_x else [
                        (displacement_leg_dependant * 5, displacement_leg * 5),
                        (displacement_leg_dependant * 5 + 1, displacement_leg * 5),
                        (displacement_leg_dependant * 5 - 1, displacement_leg * 5),
                    ]
                    for location in locations:
                        if location not in search_pattern_obj["area_map"]:
                            search_pattern_obj["area_map"][
                                location
                            ] = {
                                "x": location[0],
                                "y": location[1],
                                "val": 255
                            }
                        else:
                            search_pattern_obj["area_map"][
                                location
                            ]["val"] = max(
                                search_pattern_obj["area_map"][
                                    location
                                ]["val"] - 60, 60)
            def remove_forward_slashes(slash_list):
                return list(map(lambda slash_path: slash_path.replace('\\', '/'), list(slash_list)))
            if search_pattern_obj["stitcher_status"] != "STITCHER_OK" and step_index > 0:
                prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1))
                prev_post_img_path_split = prev_post_img_path.split('/')
                pre_img_name = prev_post_img_path_split[-1]
                pre_img_path = prev_post_img_path
                pre_img = read_and_apply_mask(pre_img_path)
            else:
                pre_img_name = str(step_index) + \
                    '-' + str(raw_source_pt[0]) + '-' + str(raw_source_pt[1]) + '-search-step-init.png'
                pre_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + pre_img_name
                print('pre_path', pre_img_name, ':', raw_source_pt, ':', step_index)
                pre_img = create_and_save_screencap(
                    self, pre_img_path
                )

            for fitted_pattern in fitted_patterns:
                (fitted_source_pt, fitted_target_pt) = fitted_pattern
                if self.width > self.height:
                    search_unit_scale = self.height
                else:
                    search_unit_scale = self.width
                src_x = fitted_source_pt[0] * search_unit_scale
                src_y = fitted_source_pt[1] * search_unit_scale
                tgt_x = fitted_target_pt[0] * search_unit_scale
                tgt_y = fitted_target_pt[1] * search_unit_scale
                print('desired move: (', tgt_x - src_x,',', tgt_y - src_y, ')')
                self.click_and_drag(src_x, src_y, tgt_x, tgt_y)
                time.sleep(0.25)
            post_img_name = str(step_index) + '-' +\
                str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-complete.png'
            post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + post_img_name
            print('post_img_path', post_img_path, ':', raw_target_pt, ':', step_index)
            post_img = create_and_save_screencap(
                self, post_img_path
            )
            stitch_attempts = 0
            stitch_imgs = [pre_img, post_img]
            stitching_complete = False
            retaken_post_img_name = None
            retaken_post_img_path = None
            while not stitching_complete:
                print('len : stitch imgs', len(stitch_imgs), pre_img.shape, post_img.shape)
                err_code, result_im = search_pattern_obj["stitcher"].stitch(stitch_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
                draggable_area_path = search_pattern_obj["draggable_area_path"]

                if err_code == cv2.STITCHER_OK:
                    search_pattern_obj["stitcher_status"] = "STITCHER_OK"
                    search_pattern_obj["stitch"] = result_im
                    cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/' + str(step_index) + '-pano.png', result_im)
                    # print(subprocess.run([self.image_stitch_calculator_path,
                    #                       pre_img_path, post_img_path, '-m',
                    #                       draggable_area_path, draggable_area_path],
                    #                       capture_output=True,shell=False).stdout)
                    break
                elif err_code == cv2.STITCHER_ERR_NEED_MORE_IMGS:
                    search_pattern_obj["stitcher_status"] = "STITCHER_ERR_NEED_MORE_IMGS"
                    retaken_post_img_name = str(step_index) + '-' + \
                                            str(raw_target_pt[0]) + '-' + str(
                        raw_target_pt[1]) + '-retaken-search-step-complete.png'
                    retaken_post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + retaken_post_img_name
                    if stitch_attempts > 1:
                        print('need more imgs: ', len(stitch_imgs))
                        search_pattern_obj["step_index"] -= 1
                        shutil.move(pre_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
                        shutil.move(post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
                        shutil.move(retaken_post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
                        break
                    retaken_post_img = create_and_save_screencap(
                        self, retaken_post_img_path
                    )

                    stop_index = max(0, step_index - 1)
                    start_index = max(0, step_index - 4)
                    glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
                    print('glob_patterns', glob_patterns)
                    stitch_imgs = remove_forward_slashes(
                        itertools.chain.from_iterable(
                            (glob.glob(
                                log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
                                    glob_pattern) + '*-complete.png'
                            ) + glob.glob(
                                log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
                                    glob_pattern
                                ) + '*-init.png'
                            )) for glob_pattern in glob_patterns
                        )
                    )
                    print('stitch_ims ', stitch_imgs)
                    if step_index > 0:
                        prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(stop_index) + '*-complete.png')
                        print('prev_post_img_path', prev_post_img_path)
                        stitch_imgs.remove(prev_post_img_path)
                        new_step_imgs = [pre_img, read_and_apply_mask(prev_post_img_path), retaken_post_img]
                    else:
                        new_step_imgs = [pre_img, retaken_post_img]
                    stitch_imgs = new_step_imgs + (list(map(read_and_apply_mask, stitch_imgs)) if stop_index > 0 else [])
                    # print('post stitch_ims: ', stitch_imgs)
                    stitch_attempts += 1
                else:
                    search_pattern_obj["stitcher_status"] = "STITCHER_ERR"
                    search_pattern_obj["step_index"] -= 1
                    shutil.move(pre_img_path,
                                log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
                    shutil.move(post_img_path,
                                log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
                    if retaken_post_img_path is not None and retaken_post_img_name is not None:
                        shutil.move(retaken_post_img_path,
                                    log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
                    print('special error! ' + err_code)
                    break

            context["search_patterns"][search_pattern_id] = search_pattern_obj
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "searchPatternEndAction":
            search_pattern_id = action["actionData"]["searchPatternID"]
            if context["parent_action"] is not None and \
                context["parent_action"]["actionName"] == "searchPatternContinueAction" and \
                context["parent_action"]["actionData"]["searchPatternID"] == search_pattern_id and \
                not context["search_patterns"][search_pattern_id]["stitcher_status"] == "stitching_finished":
                # TODO haven't decided what the stiching_finished status should be yet (ie should always just return)
                return ScriptExecutionState.RETURN, state, context

            step_index = context["search_patterns"][search_pattern_id]["step_index"]
            search_pattern_obj = context["search_patterns"][search_pattern_id]
            def apply_draggable_area_mask(img):
                return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))
            def read_and_apply_mask(img_path):
                return apply_draggable_area_mask(cv2.imread(img_path))
            def generate_greater_pano(start_index, stop_index):
                glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
                greater_pano_paths = remove_forward_slashes(
                    itertools.chain.from_iterable(
                        glob.glob(
                            log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
                                glob_pattern
                            ) + '*-complete.png'
                        ) + glob.glob(
                            log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
                                glob_pattern
                            ) + '*-init.png'
                        ) for glob_pattern in glob_patterns
                    )
                )
                greater_pano_imgs = list(map(read_and_apply_mask, greater_pano_paths))
                err_code, result_im = search_pattern_obj["stitcher"].stitch(greater_pano_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
                if err_code == cv2.STITCHER_OK:
                    print('generating full panorama...')
                    cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/full-pano.png', result_im)
                    # print(subprocess.run([self.image_stitch_calculator_path] + \
                    #                      greater_pano_paths + ['-m'] + \
                    #                      [draggable_area_path] * len(greater_pano_paths),
                    #                      capture_output=True, shell=False).stdout)
                    pass
                else:
                    print('failed to greater pano: ', err_code)
            generate_greater_pano(0, step_index)

            del context["search_patterns"][action["actionData"]["searchPatternID"]]
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                # print(np.array(pyautogui.screenshot()).shape)
                # exit(0)
                log_image = self.screenshot()
                cv2.imwrite(logs_path + '-logImage.png', log_image)
                return ScriptExecutionState.SUCCESS, state, context
            else:
                print('log type unimplemented ' + action["actionData"]["logType"])
                exit(0)
        elif action["actionName"] == "timeAction":
            state[action["actionData"]["outputVarName"]] = datetime.datetime.now()
            # self.state[action["actionData"]["outputVarName"]] = expression
            return ScriptExecutionState.SUCCESS, state, context
        elif action["actionName"] == "keyboardAction":
            return self.host_os.handle_action(action, state, context, log_level, log_folder)
        else:
            print("action uninplemented on adb " + action["actionName"])
            exit(0)


if __name__ == '__main__':
    adb_host = adb_host({
        "videoDims": "null",
        "windowBounds": "null",
        "emulatorPath": "/Users/Tak/Library/Android/sdk/emulator/emulator",
        "adbPath": "adb",
        "deviceName": "Pixel_2_API_30",
        "targetSystem": "none",
        "scriptName": "Windows_BlueStacks_Open",
        "width": 1920,
        "height": 1080,
        "scriptMode": "train",
        "deploymentTarget": "http://10.147.17.223:3849",
        "deploymentToLibrary": "true"
    }, None, '127.0.0.1:5555')
    adb_host.init_system()
    adb_host.click(633, 858)
    # (633.3333333333333, 858.6666666666666),
    exit(0)
