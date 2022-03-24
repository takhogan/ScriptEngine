import subprocess
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
import random
import time
import sys
from scipy.stats import truncnorm
import os

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from click_path_generator import ClickPathGenerator
from image_matcher import ImageMatcher
from search_pattern_helper import SearchPatternHelper

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

    def init_system(self):
        if self.width is None or self.height is None:
            devices_output = bytes.decode(
                subprocess.run(self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')
            emualator_active = (
                    'emulator' in
                    bytes.decode(subprocess.run(
                        self.adb_path + ' devices ', cwd="/", shell=True, capture_output=True).stdout, 'utf-8')) \
                if not 'started' in devices_output else 'emulator' in devices_output
            if not emualator_active:
                print('connecting to')
                subprocess.run(self.adb_path + ' connect ' + self.adb_ip, cwd="/", shell=True)
            source_im = np.array(Image.open(BytesIO(
                subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True).stdout)))
            self.width = source_im.shape[1]
            self.height = source_im.shape[0]
            print(self.width, self.height)

    def screenshot(self):
        return Image.open(BytesIO(subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True).stdout))

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
        elif self.device_profile == 'windows-bluestacks':
            #yes x and y is flipped for some reason in bluestacks
            mapped_x_val = int(((self.height - y) / self.height) * self.ymax)
            mapped_y_val = int((x / self.width) * self.xmax)
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
        print((''.join(click_command)).encode('utf-8'))
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
        elif self.device_profile == 'windows-bluestacks':
            # yes x and y are flipped on purpouse
            frac_source_x = ((self.height - source_y) / self.height)
            frac_source_y = (source_x / self.width)
            frac_target_x = ((self.height - target_y) / self.height)
            frac_target_y = (target_x / self.width)
            if (frac_source_x < 0 or frac_source_y < 0 or frac_target_x < 0 or frac_target_y < 0):
                print(self.width, self.height)
                print(source_x, source_y)
                print(target_x, target_y)
                exit(0)
            else:
                return
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
        print((''.join(command_string)).encode('utf-8'))
        self.event_counter += 1

    def handle_action(self, action, state, props, log_level, log_folder):
        logs_path = log_folder + str(state['script_counter']) + '-'
        time.sleep(0.25)
        if action["actionName"] == "declareScene":
            print('taking screenshot')
            output = self.screenshot()
            screencap_im = output
            screencap_im = cv2.cvtColor(np.array(screencap_im), cv2.COLOR_RGB2BGR)
            screencap_mask = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(action['actionData']['img'])
            print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            print(screencap_im.shape)
            print(screencap_mask.shape)
            screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)
            screencap_compare = cv2.imread(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])

            ssim_coeff = ssim(screencap_masked, screencap_compare, multichannel=True)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-masked.png', screencap_masked)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-compare.png', screencap_compare)
            if ssim_coeff > 0.8:
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state

        elif action["actionName"] == "detectObject":
            # https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
            # https://learnopencv.com/image-resizing-with-opencv/
            screencap_im_rgb = self.screenshot()
            # print('imshape: ', np.array(screencap_im_rgb).shape, ' width: ', self.props['width'], ' height: ', self.props['height'])
            if self.props['width'] is None or self.props['height'] is None:
                screencap_im = screencap_im_rgb
            else:
                screencap_im = cv2.resize(np.array(screencap_im_rgb), (self.props['width'], self.props['height']),
                                          interpolation=cv2.INTER_LINEAR)
            screencap_im = cv2.cvtColor(screencap_im.copy(), cv2.COLOR_BGRA2BGR)
            screencap_mask = cv2.imread(
                self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
            # print(props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            # print(screencap_im.shape)
            # print(screencap_mask.shape)
            # exit(0)

            screencap_search = cv2.imread(
                self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
            screencap_search_bgr = cv2.cvtColor(screencap_search.copy(), cv2.COLOR_RGB2BGR)
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search)
            if self.props["scriptMode"] == "train":
                cv2.imwrite(logs_path + 'search_img.png', screencap_search)
            matches = self.image_matcher.template_match(screencap_im, screencap_mask, screencap_search_bgr,
                                                        action['actionData']['detectorName'], logs_path, self.props["scriptMode"],threshold=action["actionData"]["threshold"])
            if len(matches) > 0:
                print(matches)
                state[action['actionData']['outputVarName']] = matches
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state

        elif action["actionName"] == "clickAction":
            point_choice = random.choice(action["actionData"]["pointList"]) if action["actionData"]["pointList"] else (
            None, None)
            if action["actionData"]["inputExpression"] is not None and len(action["actionData"]["inputExpression"]) > 0:
                input_points = eval(action["actionData"]["inputExpression"], state)
                if len(input_points) > 0:
                    # potentially for loop here
                    input_points = input_points[0]
                    if input_points["input_type"] == "rectangle":
                        width_coord = random.random() * input_points["width"]
                        height_coord = random.random() * input_points['height']
                        point_choice = (input_points["point"][0] + width_coord, input_points["point"][1] + height_coord)
            point_choice = (
            point_choice[0] * self.width / self.props['width'], point_choice[1] * self.height / self.props['height'])
            print(point_choice)
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

            for click_count in range(0, action["actionData"]["clickCount"]):
                self.click(point_choice[0], point_choice[1])
                time.sleep(delays[click_count])

            return ScriptExecutionState.SUCCESS, state

        elif action["actionName"] == "shellScript":
            if self.host_os is not None:
                return ScriptExecutionState.SUCCESS, self.host_os.run_script(action, state)

        elif action["actionName"] == "conditionalStatement":
            if eval(action["actionData"]["condition"], state):
                print('condition success!')
                return ScriptExecutionState.SUCCESS, state
            else:
                print('condition failure!')
                return ScriptExecutionState.FAILURE, state
        elif action["actionName"] == "sleepStatement":
            time.sleep(float(eval(action["actionData"]["sleepTime"], state)))
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "dragLocationSource":
            source_point = random.choice(action["actionData"]["pointList"])
            print(action["actionData"]["inputExpression"])
            if not action["actionData"]["inputExpression"] == "null" and action["actionData"]["inputExpression"] is not None:
                source_point = eval(action["actionData"]["inputExpression"], state)
            state["dragLocationSource"] = source_point
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "dragLocationTarget":
            source_point = state["dragLocationSource"]
            target_point = random.choice(action["actionData"]["pointList"])
            if not action["actionData"]["inputExpression"] == "null" and action["actionData"]["inputExpression"] is not None:
                target_point = eval(action["actionData"]["inputExpression"], state)
            self.click_and_drag(source_point[0], source_point[1], target_point[0], target_point[1])
            del state["dragLocationSource"]
            # print(source_point)
            # print(target_point)
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "searchPatternStartAction":
            state = self.search_pattern_helper.generate_pattern(action, state, log_folder, self.props['dir_path'])
            # print(state)
            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "searchPatternContinueAction":
            search_pattern_id = action["actionData"]["searchPatternID"]
            search_pattern_obj = state["search_patterns"][search_pattern_id]
            raw_source_pt, raw_target_pt, displacement, state = self.search_pattern_helper.execute_pattern(search_pattern_id, state)
            fitted_patterns = self.search_pattern_helper.fit_pattern_to_frame(self.width, self.height, search_pattern_obj["draggable_area"], [(raw_source_pt, raw_target_pt)])

            cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/' + str(search_pattern_obj["step_index"]) + '-' + str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-init.png', np.array(self.screenshot()))
            for fitted_pattern in fitted_patterns:
                (fitted_source_pt, fitted_target_pt) = fitted_pattern
                if self.width > self.height:
                    search_unit_scale = self.height
                else:
                    search_unit_scale = self.width
                self.click_and_drag(fitted_source_pt[0] * search_unit_scale,
                                    fitted_source_pt[1] * search_unit_scale,
                                    fitted_target_pt[0] * search_unit_scale,
                                    fitted_target_pt[1] * search_unit_scale)
                time.sleep(0.25)
            cv2.imwrite(
                log_folder + 'search_patterns/' + search_pattern_id + '/' + str(search_pattern_obj["step_index"]) + '-' +
                str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-complete.png', np.array(self.screenshot()))

            return ScriptExecutionState.SUCCESS, state
        elif action["actionName"] == "searchPatternEndAction":
            del state[action["actionData"]["patternID"]]
            return ScriptExecutionState.SUCCESS, state
        else:
            print("action uninplemented on adb " + action["actionName"])
            exit(0)


if __name__ == '__main__':
    avd = adb_host({
    "videoDims": None,
    "windowBounds": None,
    "emulatorPath": "/Users/Tak/Library/Android/sdk/emulator/emulator",
    "adbPath": "adb",
    "deviceName": "Pixel_2_API_30",
    "targetSystem": "adb",
    "scriptName": "SearchScriptBasic",
    "width": 540,
    "height": 960,
    "scriptMode": "train"
    }, '', '127.0.0.1:5555')
    avd.init_system()
    for i in range(0, 10):
        avd.click_and_drag(100, 100, 400, 400)
    exit(0)
    # print(avd.screenshot())
    cv2.imshow('capture', np.array(Image.open(BytesIO(avd.screenshot().stdout))))
    cv2.waitKey(0)
    # avd.click(752, 1935)
    # avd.click_and_drag(50, 50, 752, 1935)
    #.returncode = 1 (if err)