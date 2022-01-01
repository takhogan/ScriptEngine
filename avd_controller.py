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


class AVD:
    def __init__(self, adb_path, emulator_path, device_name, host_os):
        self.host_os = host_os
        self.adb_path = adb_path
        self.emulator_path = emulator_path
        self.device_name = device_name
        self.width = 1080
        self.height = 720
        self.xmax = 32726
        self.ymax = 32726
        self.event_counter = 1
        #TODO CORRECT ABOVE
        self.distances_dist = {

        }
        pass

    def screenshot(self):
        return subprocess.run(self.adb_path + ' exec-out screencap -p', cwd="/", shell=True, capture_output=True)

    def click(self, x, y):
        sendevent_command = self.adb_path + ' shell sendevent /dev/input/event2 {} {} {};'
        # header commands
        tracking_id_mousedown = sendevent_command.format(3, 39, 0)
        touch_major = sendevent_command.format(3, 30, self.event_counter)
        abs_mt_pressure_down = sendevent_command.format(3, '3a', 81)
        # 1st point always the og x,y
        x_command = sendevent_command.format(3, 35, (x / self.width) * self.xmax)
        y_command = sendevent_command.format(3, 36, (y / self.height) * self.ymax)
        action_terminate_command = sendevent_command.format(0, 0, 0)
        init_click_commands = [tracking_id_mousedown, touch_major, abs_mt_pressure_down, x_command, y_command, action_terminate_command]
        init_click_commands = [commandlet for command in init_click_commands for commandlet in command.split(' ')]
        # print(init_click_commands)
        # exit(0)
        subprocess.run(init_click_commands, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(0.09)
        exit(0)
        n_events = np.random.geometric(p=0.739)
        if n_events > 1:
            tail_type = np.random.choice(['x', 'y', 'm'], p=[0.4526, 0.21, 0.3374])
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
                for tail_event in range(1, n_events):
                    event_action = np.random.choice(['x', 'xy', 'y'],
                                                    p=transition_matrix[:, action_to_index[last_action]])
                    # gen_event_sequence.append(event_action)
                    last_action = event_action
            elif tail_type == 'x':
                tail_end = np.random.choice(['x', 'xy'], p=[42 / 43, 1 / 43])
            elif tail_type == 'y':
                tail_end = np.random.choice(['y', 'xy'], p=[20 / 21, 1 / 21])
                # examine distribution of distances for different tail types (in particular 0 distance moves)
        else:
            pass
        # subprocess.run([self.adb_path, 'shell', 'input', 'tap', x, y])
        # need to verify that tap will still work with only x as header (maybe try replaying some of the x header clicks)
        self.last_y = y
        self.last_x = x
        abs_mt_pressure_up = sendevent_command.format(3, '3a', 0)
        tracking_id_mouseup = sendevent_command.format(3, 39, 'ffffffff')
        action_terminate_command = sendevent_command.format(0, 0, 0)

        pass

    def handle_action(self, action, state, props, log_level, log_folder):
        state["script_counter"] += 1
        logs_path = log_folder + str(state['script_counter']) + '-'
        if action["actionName"] == "declareScene":
            print('taking screenshot')
            output = self.screenshot()
            screencap_im = Image.open(BytesIO(output.stdout))
            screencap_im = cv2.cvtColor(np.array(screencap_im), cv2.COLOR_RGB2BGR)
            screencap_mask = cv2.imread(props['dir_path'] + '/' + action["actionData"]["mask"])
            print(props['dir_path'] + '/' + action["actionData"]["mask"])
            print(screencap_im.shape)
            print(screencap_mask.shape)
            screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)

            screencap_compare = cv2.imread(props['dir_path'] + '/' + action["actionData"]["img"])

            ssim_coeff = ssim(screencap_masked, screencap_compare, multichannel=True)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-masked.png', screencap_masked)
            cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-compare.png', screencap_compare)
            if ssim_coeff > 0.8:
                return ScriptExecutionState.SUCCESS, state
            else:
                return ScriptExecutionState.FAILURE, state

        elif action["actionName"] == "clickAction":
            print('clicking')
            click_point = random.choice(action["pointList"])
            self.tap(click_point[0], click_point[1])

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
    avd.click(50, 50)
