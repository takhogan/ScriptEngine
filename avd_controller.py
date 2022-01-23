import subprocess
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
import random
import time
import sys

sys.path.append(".")
from script_execution_state import ScriptExecutionState
from click_path_generator import ClickPathGenerator

class AVD:
    def __init__(self, adb_path, emulator_path, device_name, host_os):
        self.host_os = host_os
        self.adb_path = adb_path
        self.emulator_path = emulator_path
        self.device_name = device_name
        self.width = 1080
        self.height = 2340
        self.xmax = 32726
        self.ymax = 32726
        self.click_path_generator = ClickPathGenerator(121.5, 68.25, self.xmax, self.ymax, 45, 0.4)
        self.event_counter = 1
        #TODO CORRECT ABOVE
        self.distances_dist = {

        }
        # set device here
        # print(self.adb_path)
        # exit(0)
        shell_process = subprocess.Popen([self.adb_path, 'shell'],stdin=subprocess.PIPE)
        device_name = shell_process.communicate(b"getevent -pl 2>&1 | sed -n '/^add/{h}/ABS_MT_TOUCH/{x;s/[^/]*//p}'")
        self.sendevent_command = 'sendevent /dev/input/event1 {} {} {};'
        self.commands = {
            "tracking_id_mousedown": self.sendevent_command.format(3, int('39', 16), 0),
            "touch_major_func": lambda: self.sendevent_command.format(3, int('30', 16), self.event_counter),
            "abs_mt_pressure_down" : self.sendevent_command.format(3, int('3a', 16), int('81', 16)),
            "x_command_func" : lambda x_val: self.sendevent_command.format(3, int('35',16), x_val),
            "y_command_func" : lambda y_val: self.sendevent_command.format(3, int('36',16), y_val),
            "action_terminate_command" : self.sendevent_command.format(0, 0, 0),
            "abs_mt_pressure_up" : self.sendevent_command.format(3, int('3a', 16), 0),
            "tracking_id_mouseup" : self.sendevent_command.format(3, int('39', 16), '-1'),

        }


        pass


    def screenshot(self):
        return subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True)

    def click(self, x, y, important=False):
        # 1st point always the og x,y
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
        shell_process = subprocess.Popen(['/Users/Tak/Library/Android/sdk/platform-tools/adb', 'shell'], stdin=subprocess.PIPE)
        shell_process.communicate((''.join(click_command)).encode('utf-8'))
        self.event_counter += 1

    def click_and_drag(self, source_x, source_y, target_x, target_y):
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
        shell_process = subprocess.Popen(['/Users/Tak/Library/Android/sdk/platform-tools/adb', 'shell'],
                                         stdin=subprocess.PIPE)
        shell_process.communicate((''.join(command_string)).encode('utf-8'))

        self.event_counter += 1

    def handle_action(self, action, state, props, log_level, log_folder):
        state["script_counter"] += 1
        logs_path = log_folder + str(state['script_counter']) + '-'
        if action["actionName"] == "declareScene":
            print('taking screenshot')
            output = self.screenshot()
            screencap_im = Image.open(BytesIO(output.stdout))
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

        elif action["actionName"] == "clickAction":
            print('clicking')
            click_point = random.choice(action["actionData"]["pointList"])
            self.click(click_point[0], click_point[1])

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
            time.sleep(int(action["actionData"]["sleepTime"]))
            return ScriptExecutionState.SUCCESS, state
        else:
            return ScriptExecutionState.FAILURE, state


if __name__ == '__main__':
    avd = AVD('/Users/Tak/Library/Android/sdk/platform-tools/adb', '', '', '')
    avd.click(752, 1935)
    # avd.click_and_drag(50, 50, 752, 1935)
