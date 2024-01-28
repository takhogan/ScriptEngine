
from script_loader import parse_zip
from script_executor import ScriptExecutor
import cv2
import numpy as np
import pyautogui
import concurrent.futures
import sys
import time
import psutil
import json

sys.path.append("..")
from image_matcher import ImageMatcher
from device_manager import DeviceManager
from parallelized_script_executor import ParallelizedScriptExecutor
import datetime
from dateutil import tz



def do_template_match(action, og_time):
    if action['actionName'] != 'detectObject':
        return None
    screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
    screencap_im_bgr = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
    use_color = True
    use_mask = True
    screencap_mask_gray = action["actionData"]["positiveExamples"][0]["mask_single_channel"]
    # script_logger.log('matching ', action['actionGroup'], time.time() - og_time)
    logs_path = './logs'
    image_matcher = ImageMatcher()
    match_result = image_matcher.template_match(
        action,
        screencap_im_bgr,
        screencap_search_bgr,
        action["actionData"]["positiveExamples"][0]["mask_single_channel"],
        action["actionData"]["positiveExamples"][0]["outputMask"],
        action["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
        action['actionData']['detectorName'],
        logs_path,
        'train',
        None,
        log_level='info',
        check_image_scale=False,
        output_cropping=action["actionData"]["maskLocation"] if
        (action["actionData"]["maskLocation"] != 'null' and
         "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
         ) else None,
        threshold=float(action["actionData"]["threshold"]),
        use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
    )
    return match_result

def test_parallel(script_executor, script_object, parallel=True):

    screenshot = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
    for actionRow in script_object['actionRows']:
        for action in actionRow['actions']:
            action['actionData']['screencap_im_bgr'] = screenshot
    time_1 = time.time()
    script_logger.log('time: ', time_1)

    actionRow = script_object['actionRows'][0]
    if parallel:
        parallel_indices = []
        parallel_actions = []
        for parallel_index in range(0, len(actionRow['actions'])):
            parallel_action = script_executor.handle_action(actionRow['actions'][parallel_index], lazy_eval=True)
            parallel_actions.append([parallel_index, parallel_action])
            parallel_indices.append(parallel_index)
        parallel_executor = ParallelizedScriptExecutor()
        parallel_executor.parallelized_execute(parallel_actions, 0, len(parallel_actions) - 1)

        # script_executor.actions = actionRow['actions']
        # script_executor.execute_actions()
    else:
        for action in actionRow['actions']:
            script_executor.device_manager.python_host.handle_action(
                action,
                script_executor.state,
                script_executor.context,
                script_executor.run_queue,
                script_executor.log_level,
                script_executor.log_folder
            )
    script_logger.log('final ', time.time() - time_1)

if __name__ == '__main__':
    script_name = 'Mac_DetectObjectSingle'
    script_object = parse_zip(script_name)
    times = 5
    adb_args = {}
    device_manager = DeviceManager(script_name, script_object['props'], adb_args)

    script_id = 1
    start_time = datetime.datetime.now()
    start_time_str = start_time.strftime('%Y-%m-%d %H-%M-%S')
    script_logger.log(start_time, start_time_str)
    timeout = (start_time + datetime.timedelta(minutes=30)).replace(tzinfo=tz.tzlocal())
    log_level = 'info-text'
    constants = {}
    script_executor = ScriptExecutor(
        script_object,
        timeout,
        script_name,
        start_time_str,
        script_id,
        device_manager,
        log_level=log_level,
        state=constants,
        start_time=start_time_str
    )

    running_script = {
        "script_id" : script_id,
        "script_name": script_name,
        "status": "pending",
        "script_duration" : '0h30m',
        "start_time_str" : start_time_str,
        "end_time_str" : timeout.strftime('%Y-%m-%d %H-%M-%S'),
        "log_level" : log_level,
        "notification_level" : None,
        "args" : {},
        "parallel" : True,
        "script_log_folder" : None
    }

    running_scripts = []
    running_scripts.append(running_script)
    RUNNING_SCRIPTS_PATH = './tmp/running_scripts.json'

    with open(RUNNING_SCRIPTS_PATH, 'w') as runng_scripts_file:
        json.dump(running_scripts, runng_scripts_file)
    script_executor.run()
    # for i in range(0, times):
        # sequential ~19.5 s
        # parallel ~8.6 s
        # test_parallel(script_executor, script_object, parallel=True)
        #10.36, 11, 11.8, 10.9
