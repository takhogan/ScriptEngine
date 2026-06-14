import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Unable to retrieve source for @torch.jit._overload function",
    category=UserWarning,
    module=r"torch\._jit_internal"
)
warnings.filterwarnings(
    "ignore",
    message=r"Neither CUDA nor MPS are available.*",
    category=UserWarning
)
warnings.filterwarnings(
    "ignore",
    message="Neither CUDA nor MPS are available - defaulting to CPU. Note: This module is much faster with a GPU.",
    category=UserWarning
)

import numpy as np
import cv2
import json
import time
import datetime
import os
import sys


from .helpers.detect_object_helper import DetectObjectHelper
from .helpers.random_variable_helper import RandomVariableHelper
from .helpers.match_merge_helper import MatchMergeHelper
from .helpers.image_to_text_action_helper import ImageToTextActionHelper
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.constants.script_engine_constants import *
from ScriptEngine.common.types import ScreenPlanImage, is_screenplan_image_result
from ScriptEngine.common.script_engine_utils import generate_context_switch_action, sanitize_statement_input, state_eval, state_exec
from ScriptEngine.common.logging.script_logger import ScriptLogger
from typing import Callable, Dict, List, Tuple
script_logger = ScriptLogger()


class SystemScriptActionExecutor:
    def __init__(self, base_script_name, props, io_executor, screen_plan_server_attached):
        self.base_script_name = base_script_name
        self.props = props
        self.io_executor = io_executor
        self.screen_plan_server_attached = screen_plan_server_attached
        if screen_plan_server_attached:
            from .helpers.messaging_helper import MessagingHelper
            self.messaging_helper = MessagingHelper()
            from .helpers.user_secrets_helper import UserSecretsHelper
            self.user_secrets_helper = UserSecretsHelper()
            from .helpers.calendar_action_helper import CalendarActionHelper
            self.calendar_action_helper = CalendarActionHelper()

        else:
            self.messaging_helper = None
            self.calendar_action_helper = None
        self.match_merge_helper = MatchMergeHelper()
        self.easy_ocr_reader = None

    def _resolve_tmp_file(self, file_name):
        """Locate a runtime jsonFileAction read target. Prefers `tmp/` (new
        layout); falls back to `scriptAssets/` for scripts that haven't been
        re-saved since the rename. Returns None if neither exists."""
        tmp_path = os.path.join(self.props['dir_path'], 'tmp', file_name)
        if os.path.exists(tmp_path):
            return tmp_path
        legacy_path = os.path.join(self.props['dir_path'], 'scriptAssets', file_name)
        if os.path.exists(legacy_path):
            return legacy_path
        return tmp_path

    def handle_action(self, action, state, context, run_queue) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List] | Tuple[Callable, Tuple]:
        # Initialize status to FAILURE as default (will be overridden by action handlers)
        status = ScriptExecutionState.ERROR
        
        if action["actionName"] == "shellScript":
            from .helpers.shell_script_helper import ShellScriptHelper
            state = ShellScriptHelper.run_shell_script(action, state)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "conditionalStatement":
            condition = action["actionData"]["condition"].replace("\n", " ").strip()
            statement_strip = sanitize_statement_input(condition, state)
            pre_log = 'condition: {} {}'.format(condition, statement_strip)
            script_logger.log(pre_log)
            
            if state_eval('(' + condition + ')',{}, state):
                post_log = 'condition successful'
                script_logger.log(post_log)
                status = ScriptExecutionState.SUCCESS
                result_text = 'condition successful'
            else:
                post_log = 'condition failure'
                script_logger.log(post_log)
                status = ScriptExecutionState.FAILURE
                result_text = 'condition failed'
            
            # Create summary with condition: truncate if too long
            condition_summary = condition
            if len(condition_summary) > 50:
                condition_summary = condition_summary[:47] + '...'
            script_logger.get_action_log().set_summary('{}: {}'.format(result_text, condition_summary))

            script_logger.get_action_log().add_post_file(
                'text',
                ('condition-success.txt' if status == ScriptExecutionState.SUCCESS else 'condition-failure.txt'),
                pre_log + '\n' + post_log
            )
        elif action["actionName"] == "variableAssignment":
            outputVarName = action["actionData"]["outputVarName"].strip()
            outputVarNameInState = outputVarName in state
            isSetIfNull = action["actionData"]["setIfNull"] == "true" or action["actionData"]["setIfNull"]
            post_file_name = 'variableAssignment-log.txt'
            pre_log = ('assignment configuration is set if null' if isSetIfNull else '')
            script_logger.get_action_log().add_post_file(
                'text',
                post_file_name,
                (pre_log + '\n' if pre_log != '' else '')
            )
            if isSetIfNull and outputVarNameInState and state[outputVarName] is not None:
                pre_log += ' and output variable {} was not null'.format(outputVarName)
                script_logger.log(pre_log)
                status = ScriptExecutionState.SUCCESS
                script_logger.get_action_log().set_summary('skipped ({} already set)'.format(outputVarName))
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    (pre_log + '\n' if pre_log != '' else '')
                )
            else:
                pre_log += ('and output variable {} was null'.format(outputVarName) if isSetIfNull else '')
                statement_strip = sanitize_statement_input(action["actionData"]["inputExpression"], state)

                mid_log = ('inputExpression : ' + action["actionData"]["inputExpression"])
                mid_log_2 = ('inputs: ' + str(statement_strip))
                script_logger.log(mid_log)
                script_logger.log(mid_log_2)
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    mid_log + '\n' + \
                    mid_log_2 + '\n'
                )


                expression = action["actionData"]["inputExpression"].replace("\n", " ")
                if action["actionData"]["inputParser"] == 'eval':
                    expression = state_eval(expression, {}, state)
                elif action["actionData"]["inputParser"] == "jsonload":
                    expression = json.loads(expression)
                late_mid_log = 'parse result: ' + str(expression)
                script_logger.log('parse result: ', expression)

                late_mid_log_2 = 'state variables :' + str(list(state))
                script_logger.log(late_mid_log_2)

                if '[' in outputVarName and ']' in outputVarName:
                    keys = outputVarName.split('[')  # Split the key string by '][' to get individual keys
                    # Evaluate variable names within the state dictionary
                    for i, k in enumerate(keys[1:]):
                        k = k.rstrip(']')
                        keys[i + 1] = state_eval(k, {}, state)

                    # Assign the value to the corresponding key within the state dictionary
                    current = state
                    for i in range(len(keys) - 1):
                        if keys[i] in current:
                            current = current[keys[i]]
                    current[keys[-1]] = expression
                else:
                    state[outputVarName] = expression
                post_log = 'setting ' + outputVarName + ' to ' + str(expression)
                script_logger.log(
                    ' setting ',
                    outputVarName,
                    ' to ',
                    expression
                )
                status = ScriptExecutionState.SUCCESS
                # Create summary: truncate value if too long
                value_str = str(expression)
                if len(value_str) > 50:
                    value_str = value_str[:47] + '...'
                script_logger.get_action_log().set_summary('set {} to {}'.format(outputVarName, value_str))
                script_logger.get_action_log().append_post_file(
                    'text',
                    post_file_name,
                    late_mid_log + '\n' + \
                    late_mid_log_2 + '\n' + \
                    post_log
                )

        elif action["actionName"] == "countToThresholdAction":
            counterVarName = action["actionData"]["counterVarName"].strip()
            counterThreshold = action["actionData"]["counterThreshold"].strip()
            incrementBy = action["actionData"]["incrementBy"].strip()
            thresholdType = action["actionData"].get("thresholdType", "counter").strip()
            
            # Check resetCounterAfterBreached attribute (unified for both counter and timer modes)
            resetCounterAfterBreached = action["actionData"].get("resetCounterAfterBreached", False)
            if isinstance(resetCounterAfterBreached, str):
                resetCounterAfterBreached = resetCounterAfterBreached.lower() == "true"

            threhold_stripped = sanitize_statement_input(counterThreshold, state)
            incrementby_stripped = sanitize_statement_input(incrementBy, state)
            pre_log = 'with counter name {}'.format(counterVarName) +\
                'threshold params {}'.format(threhold_stripped) +\
                'and incrementBy params {}'.format(incrementby_stripped) +\
                'threshold type {}'.format(thresholdType)
            script_logger.log(pre_log)

            if thresholdType == "timer":
                # Timer mode: check if thresholdSeconds has been breached
                timerVarName = counterVarName + "_timer_start"
                counterThresholdSeconds = action["actionData"].get("counterThresholdSeconds", "0").strip()
                threshold_seconds = float(state_eval(counterThresholdSeconds, {}, state))

                if timerVarName not in state:
                    # Start the timer
                    state[timerVarName] = time.time()
                    initial_timer_logs = 'Starting timer for {} at {}'.format(counterVarName, state[timerVarName])
                    script_logger.log(initial_timer_logs)
                    pre_log += '\n' + initial_timer_logs

                elapsed_time = time.time() - state[timerVarName]
                
                if elapsed_time < threshold_seconds:
                    post_log = 'For timer {}'.format(counterVarName) +\
                        'elapsed time of {:.2f}s'.format(elapsed_time) +\
                        'was less than threshold of {:.2f}s'.format(threshold_seconds) + '.' +\
                        'returning failure'
                    script_logger.log(post_log)
                    status = ScriptExecutionState.FAILURE
                    post_post_log = 'elapsed time is {:.2f}s'.format(elapsed_time)
                else:
                    post_log = 'For timer {}'.format(counterVarName) + \
                               'elapsed time of {:.2f}s'.format(elapsed_time) + \
                               'was greater than or equal to threshold of {:.2f}s'.format(threshold_seconds) + '.' + \
                               'returning success.'
                    script_logger.log(
                        'timer elapsed time of', elapsed_time, 'was greater than or equal to threshold of', threshold_seconds, '.',
                        'returning success'
                    )
                    post_post_log = ''
                    status = ScriptExecutionState.SUCCESS
                    
                    # Reset timer if resetCounterAfterBreached is True
                    if resetCounterAfterBreached:
                        del state[timerVarName]
                        reset_log = 'Timer {} reset after threshold breached'.format(counterVarName)
                        script_logger.log(reset_log)
                        post_post_log = reset_log
            else:
                initialValue = '0'
                if "initialValue" in action["actionData"]:
                    initialValue = action["actionData"]["initialValue"].strip()
                initial_value = state_eval(initialValue, {}, state)
                
                if not counterVarName in state:
                    initial_value_stripped = sanitize_statement_input(initialValue, state)

                    initial_value_logs = 'Setting initial value with initialValue params {}'.format(initial_value_stripped)
                    script_logger.log(initial_value_logs)
                    state[counterVarName] = initial_value

                    initial_value_post_logs = 'Evaluated initial value to {}'.format(initial_value)
                    script_logger.log(initial_value_post_logs)
                    pre_log += '\n' + initial_value_logs + '\n' + initial_value_post_logs

                counter_value = state_eval(counterVarName, {}, state)
                threshold_value = state_eval(counterThreshold, {}, state)
                if counter_value < threshold_value:
                    incrementby_value = state_eval(incrementBy, {}, state)
                    post_log = 'For counter {}'.format(counterVarName) +\
                        'counter value of {}'.format(counter_value) +\
                        'was less than threshold of {}'.format(threshold_value) + '.'+\
                        'incrementing by {}'.format(incrementby_value) +\
                        'and returning failure'
                    script_logger.log(
                        post_log
                    )
                    new_counter_value = counter_value + incrementby_value
                    state[counterVarName] = new_counter_value
                    status = ScriptExecutionState.FAILURE
                    post_post_log = 'new counter value is {}'.format(new_counter_value)
                    script_logger.log(
                        post_post_log
                    )
                else:
                    post_log = 'For counter {}'.format(counterVarName) + \
                               'counter value of {}'.format(counter_value) + \
                               'was greater than threshold of {}'.format(threshold_value) + '.' + \
                               'returning success.'
                    script_logger.log(
                        'counter value of', counter_value, 'was greater than threshold of', threshold_value, '.',
                        'returning success'
                    )
                    post_post_log = ''

                    status = ScriptExecutionState.SUCCESS
                    
                    # Reset counter if resetCounterAfterBreached is True
                    if resetCounterAfterBreached:
                        del state[counterVarName]
                        reset_log = 'Counter {} reset after threshold breached'.format(counterVarName)
                        script_logger.log(reset_log)
                        post_post_log = reset_log
            script_logger.get_action_log().add_post_file(
                'text',
                'counterVarName-log.txt',
                pre_log + '\n' +\
                post_log + '\n' +\
                post_post_log
            )
        elif action["actionName"] == "sleepStatement":
            input_expression = str(action["actionData"]["inputExpression"]).strip()
            pre_log = 'inputExpression: ' + input_expression
            script_logger.log(pre_log)
            sleep_length = 0
            if input_expression != '':
                sleep_length = float(state_eval(input_expression, {}, state))
                mid_log = 'evaluated inputExpression and sleeping for ' + str(sleep_length) + 's'
                script_logger.log(mid_log)
                script_logger.get_action_log().add_pre_file(
                    'text',
                    'sleepStatement-begin-{:.2f}'.format(sleep_length).replace('.', '_') + '.txt',
                    pre_log + '\n' + mid_log
                )
                time.sleep(sleep_length)
            # Create summary with proper singular/plural
            if sleep_length == 1:
                summary = 'slept 1 second'
            else:
                summary = 'slept {} seconds'.format(sleep_length)
            script_logger.get_action_log().set_summary(summary)
            script_logger.get_action_log().add_post_file(
                'text',
                'sleepStatement-end-{:.2f}'.format(sleep_length).replace('.', '_') + '.txt',
                'slept for {}s'.format(sleep_length)
            )
            status = ScriptExecutionState.SUCCESS
        #TODO: will be removed, should use regular variable assignment and the datetime module
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "randomVariable":
            rv_vals = RandomVariableHelper.get_rv_val(action["actionData"])
            state[action["actionData"]["outputVarName"]] = rv_vals[0]
            status = ScriptExecutionState.SUCCESS
            script_logger.log('created random values', rv_vals[0])
            script_logger.get_action_log().add_post_file(
                'text',
                'randomVariable-log.txt',
                'Created random values: ' + str(rv_vals[0])
            )
        #TODO: will be removed, need a new file io type action
        elif action["actionName"] == "jsonFileAction":
            if action["actionData"]["mode"] == "read":
                json_filepath = self._resolve_tmp_file(action["actionData"]["fileName"])
                if json_filepath is not None and os.path.exists(json_filepath):
                    with open(json_filepath, "r") as read_file:
                        state[action["actionData"]["varName"]] = json.load(read_file)
                else:
                    state[action["actionData"]["varName"]] = {}
                status = ScriptExecutionState.SUCCESS
            elif action["actionData"]["mode"] == "write":
                script_logger.log('writing file: ', state[action["actionData"]["varName"]])
                tmp_dir = os.path.join(self.props['dir_path'], 'tmp')
                os.makedirs(tmp_dir, exist_ok=True)
                with open(os.path.join(tmp_dir, action["actionData"]["fileName"]),
                          'w') as write_file:
                    json.dump(state[action["actionData"]["varName"]], write_file)
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.log('invalid mode: ', action)
                raise Exception('invalid mode: ' + action)
        elif action["actionName"] == "imageTransformationAction":
            # transformationType : 'blur' | 'binarize' | 'antialias' | 'resize' | 'erode' | 'dilate'
            if len(action['actionData']['inputExpression']) == 0:
                script_logger.log('Error: input expression was blank')
                raise Exception(action["actionName"] + ' input expression was blank')

            transform_im = state[action['actionData']['inputExpression']]['matched_area']
            pre_image_relative_path = 'imageTransformationAction-input.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + pre_image_relative_path, transform_im)
            script_logger.get_action_log().set_pre_file('image', pre_image_relative_path)

            if action["actionData"]["transformationType"] == "blur":
                if action["actionData"]["blurType"] == 'bilateralFilter':
                    transform_im = cv2.bilateralFilter(transform_im, int(action["actionData"]["blurKernelSize"]), 75, 75)
                elif action["actionData"]["blurType"] == 'medianBlur':
                    transform_im = cv2.medianBlur(transform_im, int(action["actionData"]["blurKernelSize"]))
                elif action["actionData"]["blurType"] == 'gaussianBlur':
                    transform_im = cv2.GaussianBlur(transform_im, (int(action["actionData"]["blurKernelSize"]), int(action["actionData"]["blurKernelSize"])), 0)
            elif action["actionData"]["transformationType"] == "binarize":
                is_color = len(transform_im.shape) != 2
                if is_color:
                    script_logger.log('converting to grayscale for binarize operation')
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                if action["actionData"]["binarizeType"] == 'regular':
                    script_logger.log('shape', transform_im.shape)
                    transform_im = cv2.threshold(
                        transform_im,
                        0,
                        255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )[1]
                elif action["actionData"]["binarizeType"] == 'adaptive':
                    transform_im = cv2.adaptiveThreshold(
                        transform_im,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        31,
                        2
                    )
                if is_color:
                    script_logger.log('converting grayscale back to color')
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)
            elif action["actionData"]["transformationType"] == "antialias":
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=1/float(action["actionData"]["antialiasScaleFactor"]),
                    fy=1/float(action["actionData"]["antialiasScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=float(action["actionData"]["antialiasScaleFactor"]),
                    fy=float(action["actionData"]["antialiasScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )

            elif action["actionData"]["transformationType"] == "resize":
                transform_im = cv2.resize(
                    transform_im, None,
                    fx=float(action["actionData"]["resizeScaleFactor"]),
                    fy=float(action["actionData"]["resizeScaleFactor"]),
                    interpolation=cv2.INTER_CUBIC
                )
            elif action["actionData"]["transformationType"] == "erode":
                kernel = np.ones((
                    int(action["actionData"]["erodeKernelSize"]),
                    int(action["actionData"]["erodeKernelSize"])
                ), np.uint8)
                transform_im = cv2.erode(transform_im, kernel, iterations=int(action["actionData"]["erodeIterations"]))
            elif action["actionData"]["transformationType"] == "dilate":
                kernel = np.ones((
                    int(action["actionData"]["erodeKernelSize"]),
                    int(action["actionData"]["erodeKernelSize"])
                ), np.uint8)
                transform_im = cv2.dilate(transform_im, kernel, iterations=int(action["actionData"]["erodeIterations"]))
            elif action["actionData"]["transformationType"] == "convertColor":
                if action["actionData"]["convertColorType"] == "BGRtoGrayScale":
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)
                elif action["actionData"]["convertColorType"] == "invert":
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_BGR2GRAY)
                    transform_im = cv2.bitwise_not(transform_im)
                    transform_im = cv2.cvtColor(transform_im, cv2.COLOR_GRAY2BGR)

            post_image_relative_path = 'imageTransformationAction-output.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + post_image_relative_path, transform_im)
            script_logger.get_action_log().set_post_file('image', post_image_relative_path)

            if len(action['actionData']['outputVarName']) > 0:
                state[action['actionData']['outputVarName']] = state[action['actionData']['inputExpression']].copy()
                state[action['actionData']['outputVarName']]['matched_area'] = transform_im
                state[action['actionData']['outputVarName']]['height'] = transform_im.shape[0]
                state[action['actionData']['outputVarName']]['width'] = transform_im.shape[1]
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "imageToTextAction":
            input_obj = DetectObjectHelper.get_detect_area(
                action, state
            )
            self.easy_ocr_reader = ImageToTextActionHelper.handle_image_to_text(
                action, input_obj, state, self.io_executor, self.easy_ocr_reader
            )
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "contextSwitchAction":
            success_states = context["success_states"] if "success_states" in context else None
            script_counter = context["script_counter"]
            script_timer = context["script_timer"]
            post_log = ''
            if action["actionData"]["state"] is not None:
                state = action["actionData"]["state"].copy()
            if action["actionData"]["context"] is not None:
                context = action["actionData"]["context"].copy()
            if 'state' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["state"].items():
                    state[key] = value
                input_state_log = 'Keys in input state: {}'.format(
                    str(list(action["actionData"]["update_dict"]["state"]))
                )
                post_log += input_state_log + '\n'
                script_logger.log(input_state_log)

            if 'context' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["context"].items():
                    context[key] = value
                input_context_log = 'Keys in input context: {}'.format(
                    str(list(action["actionData"]["update_dict"]["context"]))
                )
                post_log += input_context_log + '\n'
                script_logger.log(input_context_log)
            if success_states is not None:
                context["success_states"] = success_states
            context["script_counter"] = script_counter
            context["script_timer"] = script_timer
            status = ScriptExecutionState.SUCCESS
            iteration_log = 'Script Counter: {}'.format(
                str(context["script_counter"])
            ) + '\n' + 'Script Timer: {}'.format(
                str(context["script_timer"])
            )
            script_logger.log(iteration_log)
            post_log += iteration_log + '\n'
            script_logger.get_action_log().add_post_file(
                'text',
                'contextSwitchAction-log.txt',
                'System Created Action - Context Switch Action\n' + post_log
            )

        elif action["actionName"] == "sendMessageAction":
            if not self.screen_plan_server_attached:
                script_logger.log('unable to send message, screen plan server not active')
                status = ScriptExecutionState.FAILURE
                script_logger.get_action_log().set_summary('message send failed')
            else:
                message_data = state_eval(action["actionData"]["inputExpression"], {}, state)
                subject = state_eval(action["actionData"]["subject"], {}, state)
                pre_log = 'Sending message to ' + str(action["actionData"]["messagingChannelName"]) + ' with subject ' + str(subject)
                script_logger.log(pre_log)

                mid_log = 'Message Contents: ' + str(message_data)
                script_logger.log(mid_log)

                
                messaging_successful = self.messaging_helper.send_message({
                    "action" : "sendMessage",
                    "subject" : subject,
                    "messagingChannelName" : action["actionData"]["messagingChannelName"]
                }, message_data)

                if messaging_successful:
                    status = ScriptExecutionState.SUCCESS
                    post_log = 'Message Send Successful'
                else:
                    status = ScriptExecutionState.ERROR
                    post_log = 'Message Send Failed'
                script_logger.log(post_log)
                script_logger.get_action_log().add_pre_file(
                    'text',
                    'sendMessage-log.txt',
                    pre_log + '\n' + mid_log + '\n' + post_log
                )
                # Create summary: truncate message contents if too long
                message_str = str(message_data)
                if len(message_str) > 30:
                    message_str = message_str[:27] + '...'
                subject_str = str(subject)
                if len(subject_str) > 30:
                    subject_str = subject_str[:27] + '...'
                channel_str = str(action["actionData"]["messagingChannelName"])
                script_logger.get_action_log().set_summary("sent message with subject '{}' to channel {} with contents '{}'".format(subject_str, channel_str, message_str))
                
                thread_script_logger = script_logger.copy()
                self.io_executor.submit(
                    self.messaging_helper.create_and_save_log_image,
                    message_data,
                    thread_script_logger,
                    subject
                )
                
        elif action["actionName"] == "returnStatement":
            pre_log = 'Return Statement Type: {}'.format(action["actionData"]["returnStatementType"])
            script_logger.log(pre_log)

            mid_log = 'Desired Return Status: {}'.format(action["actionData"]["returnStatus"])
            script_logger.log(mid_log)
            status_name = 'undefined'
            if action["actionData"]["returnStatementType"] == 'exitIteration':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE_BRANCH
                    status_name = 'FINISHED_FAILURE_BRANCH'
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED_BRANCH
                    status_name = 'FINISHED_BRANCH'
                else:
                    raise Exception('invalid return status' + action["actionData"]["returnStatus"])
            elif action["actionData"]["returnStatementType"] == 'exitScript':
                if action["actionData"]["returnStatus"] == 'failure':
                    status = ScriptExecutionState.FINISHED_FAILURE
                    status_name = 'FINISHED_FAILURE'
                elif action["actionData"]["returnStatus"] == 'success':
                    status = ScriptExecutionState.FINISHED
                    status_name = 'FINISHED'
                else:
                    raise Exception('invalid return status' + action["actionData"]["returnStatus"])
            elif action["actionData"]["returnStatementType"] == 'exitProgram':
                post_log = 'Exiting Program'
                script_logger.log(post_log)
                script_logger.get_action_log().add_post_file(
                    'text',
                    'returnStatement-{}.txt'.format('exit-0'),
                    pre_log + '\n' + mid_log + '\n' + post_log
                )
                sys.exit(0)
            else:
                script_logger.log('return statement type not implemented', action["actionData"]["returnStatementType"])
                raise Exception('return statement type not implemented')
            post_log = 'Setting Status: {}'.format(status_name)
            script_logger.log(post_log)
            script_logger.get_action_log().add_post_file(
                'text',
                'returnStatement-{}.txt'.format(status_name),
                pre_log + '\n' + mid_log + '\n' + post_log
            )
        #TODO: will be removed, use returnStatement instead
        elif action["actionName"] == "exceptionAction":
            script_logger.log('exceptionAction-' + str(action["actionGroup"]), ' message: ', action["actionData"]["exceptionMessage"])
            if action["actionData"]["takeScreenshot"]:
                pass
            if action["actionData"]["exitProgram"]:
                script_logger.log('exiting program')
                sys.exit(0)
            status = ScriptExecutionState.FINISHED_FAILURE
            with open(script_logger.get_log_path_prefix() + '-return-failure.txt', 'w') as log_file:
                log_file.write('returning failure state')
        elif action["actionName"] == "forLoopAction":
            pre_log = 'Initializing Context Switch Actions for For Loop Action'
            first_loop = True
            script_logger.log(pre_log)
            in_variable = state_eval(action["actionData"]["inVariables"], {}, state)
            if (
                isinstance(in_variable, dict) and in_variable.get(DETECT_OBJECT_RESULT_MARKER)
            ) or isinstance(in_variable, ScreenPlanImage):
                error_msg = (
                    f"forLoopAction inVariables '{action['actionData']['inVariables']}' references a detectObject "
                    "result that was produced with maxMatches = 1. Set maxMatches > 1 or wrap the result in a list "
                    "before iterating."
                )
                script_logger.log(error_msg)
                raise ValueError(error_msg)

            mid_log_1 = 'inVariable: {} evaluated to: {}'.format(
                str(action["actionData"]["inVariables"]),
                str(in_variable)
            )

            script_logger.log(
                'inVariable:',
                action["actionData"]["inVariables"],
                'evaluated to:',
                in_variable
            )
            for_variable_list = action["actionData"]["forVariables"].split(',')

            mid_log_2 = 'forVariables: {} evaluated to: {}'.format(
                str(action["actionData"]["forVariables"]),
                str(for_variable_list)
            )

            script_logger.log(
                'forVariables:',
                action["actionData"]["forVariables"],
                'evaluated to:',
                for_variable_list
            )
            post_log = ''
            switch_actions = []
            for_iteration = 0
            for for_variables in in_variable:
                state_update_dict = {
                    var_name:for_variables[var_index] for var_index,var_name in enumerate(for_variable_list)
                } if len(for_variable_list) > 1 else {
                    for_variable_list[0]: for_variables
                }
                script_logger.log(
                    'for variables for iteration {}'.format(for_iteration),
                    for_variables
                )
                post_log += 'for variables for iteration {}: {}'.format(
                    for_iteration,
                    str(for_variables)
                )

                for_iteration += 1
                if first_loop:
                    state.update(state_update_dict)
                    first_loop = False
                    post_log += '\n' + 'copying for variables to current state for first loop'
                    continue
                post_log += '\n' + 'creating context switch action for iteration {}'.format(for_iteration)
                switch_action = generate_context_switch_action(action["childGroups"], None, None, {
                    "state": state_update_dict
                })
                switch_actions.append(switch_action)
            for switch_action in reversed(switch_actions):
                run_queue.append(switch_action)
            if first_loop:
                post_log += '\n' + 'inVariable was empty, skipping loop body'
                status = ScriptExecutionState.FINISHED_BRANCH
            else:
                status = ScriptExecutionState.SUCCESS
            script_logger.get_action_log().add_post_file(
                'text',
                'forLoopAction-log.txt',
                pre_log + '\n' + mid_log_1 + '\n' + mid_log_2 + '\n' + post_log
            )
        elif action["actionName"] == "codeBlock":
            pre_log = 'Running Code Block: \n{}'.format(action["actionData"]["codeBlock"])
            # statement_strip = sanitize_statement_input(action["actionData"]["codeBlock"], state_copy)
            script_logger.log(pre_log)
            code_block = action["actionData"]["codeBlock"]
            run_async = action["actionData"].get("async", False)

            def _do_code_block():
                state_exec(code_block, {}, state)
                # script_logger.get_action_log().add_post_file(
                #     'text',
                #     'codeBlock-log.txt',
                #     pre_log + '\n' + 'Code Block completed successfully'
                # )

            if run_async:
                self.io_executor.submit(_do_code_block)
            else:
                _do_code_block()
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "fileIOAction":
            pre_log = 'FileIOAction\n' + \
                (
                    'Writing to' if
                    action["actionData"]["fileActionType"] in ["w", "wb", "a"]
                    else 'Reading from'
                ) + ' file: ' + action["actionData"]["filePath"] + '\n'
            pre_log += 'Contents of type: ' + action["actionData"]["fileType"] +\
                       ' with mode ' + action["actionData"]["fileActionType"] + '\n'
            pre_log += 'Input expression: ' + action["actionData"]["inputExpression"] + '\n'
            pre_log += 'Writing inputs to variable: ' + action["actionData"]["outputVarName"]
            script_logger.get_action_log().add_pre_file('text', 'inputs.txt', pre_log)
            script_logger.log(pre_log)

            file_path = state_eval(action["actionData"]["filePath"], {}, state)
            output_var_name = action["actionData"]["outputVarName"]
            file_action_type = action["actionData"]["fileActionType"]
            file_type = action["actionData"]["fileType"]
            input_expression = action["actionData"]["inputExpression"]
            run_async = action["actionData"].get("async", False)

            def _do_file_io():
                file_properties = ''
                if file_action_type in ["w", "wb", "a"]:
                    input_value = state_eval(input_expression, {}, state)
                    if file_type == "image":
                        file_properties = 'shape: ' + str(input_value["matched_area"].shape)
                        cv2.imwrite(file_path, input_value["matched_area"])
                    elif file_type == "json":
                        file_properties = 'key: ' + str(list(input_value))
                        with open(file_path, file_action_type) as json_file:
                            json.dump(input_value, json_file)
                    elif file_type == "text":
                        file_properties = 'n characters:  ' + str(len(input_value))
                        with open(file_path, file_action_type) as text_file:
                            text_file.write(input_value)
                    state[output_var_name] = input_value
                elif file_action_type in ["r", "rb"]:
                    if file_type == "image":
                        image = cv2.imread(file_path)
                        state[output_var_name] = ScreenPlanImage(
                            input_type='shape',
                            point=(0, 0),
                            output_mask=np.full((image.shape[0], image.shape[1]), 255, dtype=np.uint8),
                            matched_area=image,
                            height=image.shape[0],
                            width=image.shape[1],
                            score=0.99999,
                            n_matches=1,
                            detect_object_result=True,
                        )
                        file_properties = 'shape: ' + str(state[output_var_name].matched_area.shape)
                    elif file_type == "json":
                        with open(file_path, file_action_type) as json_file:
                            state[output_var_name] = json.load(json_file)
                        file_properties = 'keys: ' + str(list(state[output_var_name]))
                    elif file_type == "text":
                        with open(file_path, file_action_type) as text_file:
                            state[output_var_name] = text_file.read()
                        file_properties = 'n characters:  ' + str(len(state[output_var_name]))
                post_log = (
                    'Wrote to' if file_action_type in ["w", "wb", "a"] else 'Read from'
                ) + file_path + '\n'
                post_log += 'Contents of type: ' + file_type + ' with mode ' + file_action_type + '\n'
                post_log += 'File properties: ' + file_properties + '\n'
                post_log += 'Input expression: ' + input_expression + '\n'
                post_log += 'Wrote inputs to variable: ' + output_var_name
                script_logger.get_action_log().add_post_file('text', 'post.txt', post_log)

            if run_async:
                self.io_executor.submit(_do_file_io)
            else:
                _do_file_io()
            status = ScriptExecutionState.SUCCESS
        #TODO : unsupported for now
        elif action["actionName"] == "databaseCRUD":
            if action["actionData"]["databaseType"] == "mongoDB":
                from pymongo import MongoClient 
                with open(SERVICE_CREDENTIALS_FILE_PATH, 'r') as service_credentials_file:
                    mongo_credentials = json.load(service_credentials_file)["mongoDB"]
                connection_string = "mongodb+srv://{}:{}@scriptenginecluster.44rpgo2.mongodb.net/?retryWrites=true&w=majority".format(
                    mongo_credentials["username"],
                    mongo_credentials["password"]
                )
                client = MongoClient(connection_string)
                script_logger.log(client)
                if len(action["actionData"]["collectionName"]) > 0:
                    collection_name = action["actionData"]["collectionName"]
                else:
                    collection_name = self.base_script_name
                collection = getattr(client, collection_name)

                if action["actionData"]["actionType"] == "insert":
                    if len(action["actionData"]["key"]) > 0:
                        new_item = {"key": action["actionData"]["key"],
                                    "value": state_eval(action["actionData"]["value"], {}, state)
                                    }
                    else:
                        new_item = state_eval(action["actionData"]["value"], {}, state.copy())
                    result = collection.insert_one(new_item)
                elif action["actionData"]["actionType"] == "update" or\
                        action["actionData"]["actionType"] == "upsert":
                    query = {"key": action["actionData"]["key"]}
                    update_item = {"$set": {"value": state_eval(action["actionData"]["value"], {}, state)}}
                    result = collection.update_one(
                        query,
                        update_item,
                        upsert=(action["actionData"]["actionType"] == "upsert")
                    )
                elif action["actionData"]["actionType"] == "delete":
                    query = {"key": action["actionData"]["key"]}
                    result = collection.delete_one(query)
                else:
                    result = 'action type not implemented'
                script_logger.log('db action result: ', result)
            elif action["actionData"]["databaseType"] == "oracle" or\
                action["actionData"]["databaseType"] == "mysql":
                pass
                # just need DB name
                # have the user input a SQL string to execute
                # to insert variables user SQL variable substitution
            else:
                script_logger.log("DB provider unimplemented")
                raise Exception(action["actionName"] + ' DB provider unimplemented')
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "matchMergeAction":
            status, state = self.match_merge_helper.handle_action(action, state)
        elif action["actionName"] == "userSecretManagementAction":
            if not self.screen_plan_server_attached:
                script_logger.log('unable to send message, screen plan server not active')
                status = ScriptExecutionState.FAILURE
            else:
                status, state = self.user_secrets_helper.handle_action(action, state)
        elif action["actionName"] == "calendarAction":
            if not self.screen_plan_server_attached:
                script_logger.log('unable to perform calendar action, screen plan server not active')
                status = ScriptExecutionState.FAILURE
            else:
                status, state = self.calendar_action_helper.handle_action(action, state)
        else:
            # If action name doesn't match any handler, log error and set status to FAILURE
            script_logger.log('ERROR: Unknown action name "{}" for action group {}'.format(action["actionName"], action.get("actionGroup", "unknown")))
            raise Exception('unknown action name: ' + action["actionName"])
        assert status != ScriptExecutionState.ERROR, 'action returned error status'

        return action, status, state, context, run_queue, []



if __name__ == '__main__':
    pass
