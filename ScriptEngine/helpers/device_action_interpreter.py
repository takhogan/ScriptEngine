from pyautogui import KEYBOARD_KEYS 
import time

from .random_variable_helper import RandomVariableHelper
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.script_engine_utils import state_eval
from .user_secrets_helper import SecureSecret
script_logger = ScriptLogger()

KEYBOARD_KEYS = set(KEYBOARD_KEYS)



class DeviceActionInterpreter:
    def __init__(self, dummy_mode=False):
        pass

    @staticmethod
    def parse_keyboard_action(device_controller, keyboard_action, state, context):
        is_hot_key = ("isHotKey" in keyboard_action["actionData"] and
                      (keyboard_action["actionData"]["isHotKey"] == 'true' or
                       keyboard_action["actionData"]["isHotKey"] == True))
        pre_log_1 = 'KeyboardActionType: {}'.format(keyboard_action["actionData"]["keyboardActionType"])
        script_logger.log(pre_log_1)
        pre_log_2 = 'KeyboardExpression: {}'.format(keyboard_action["actionData"]["keyboardExpression"])
        script_logger.log(pre_log_2)
        pre_log_3 = 'KeyboardActionIsHotKey {}'.format(str(is_hot_key))
        script_logger.log(pre_log_3)
        pre_log_4 = ''
        typed_chars_log = 'Typed Characters: '
        script_logger.get_action_log().add_post_file(
            'text',
            'keyboardAction-log.txt',
            pre_log_1 + '\n' + pre_log_2 + '\n' + pre_log_3 + '\n' + \
            (pre_log_4 + '\n' if is_hot_key else '')
        )
        target_system = keyboard_action["actionData"]["targetSystem"]
        dummy_mode = device_controller.get_device_attribute(target_system, 'dummy_mode')
        is_secret = False

        if dummy_mode:
            script_logger.log('DeviceActionIntepreter: script running in dummy mode, returning from keyboard action')
            return
        if is_hot_key:
            pre_log_4 = 'HotKeyKeys {}'.format(
                keyboard_action["actionData"]["keyboardExpression"].strip().split(",")
            )
            script_logger.log(pre_log_4)
            if keyboard_action["actionData"]["keyboardActionType"] == "keyPress":
                hot_key_keys = (
                    keyboard_action["actionData"]["keyboardExpression"].strip()
                ).split(",")
                hot_key_func = device_controller.get_device_action(target_system, 'hotkey')
                hot_key_func(hot_key_keys)
                typed_chars_log += ' '.join(hot_key_keys)
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                hotKeyKeys = keyboard_action["actionData"]["keyboardExpression"].split(",")
                key_down_func = device_controller.get_device_action(target_system, 'keyDown')
                for hotKeyKey in hotKeyKeys:
                    key_down_func(hotKeyKey)
                typed_chars_log += ' '.join(hotKeyKeys)
                delay_val = RandomVariableHelper.get_rv_val(keyboard_action["actionData"])[0]
                script_logger.log('Sleeping for {} seconds'.format(delay_val))
                time.sleep(delay_val)
                key_up_func = device_controller.get_device_action(target_system, 'keyUp')
                for hotKeyKey in reversed(hotKeyKeys):
                    key_up_func(hotKeyKey)
        else:
            is_escaped_char = False
            escaped_char = ''
            keyPressKeys = []
            for char_index, expression_char in enumerate(str(keyboard_action["actionData"]["keyboardExpression"])):
                if is_escaped_char:
                    if expression_char == '}':
                        is_escaped_char = False
                        if escaped_char in KEYBOARD_KEYS:
                            keyPressKeys.append(escaped_char)
                        else:
                            eval_expression = str(state_eval(escaped_char, {}, state))
                            is_secret = isinstance(eval_expression, SecureSecret)
                            if is_secret:
                                eval_expression = eval_expression.get_value()
                            for eval_expression_char in eval_expression:
                                keyPressKeys.append(eval_expression_char)
                        escaped_char = ''
                    else:
                        escaped_char += expression_char
                elif expression_char == '{':
                    is_escaped_char = True
                else:
                    keyPressKeys.append(expression_char)
            if keyboard_action["actionData"]["keyboardActionType"] == "keyPress":
                press_func = device_controller.get_device_action(target_system, 'press')
                for keyPressKey in keyPressKeys:
                    press_func(keyPressKey)
                    if not is_secret:
                        typed_chars_log += keyPressKey + ' '
                    else:
                        typed_chars_log += '* '
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                key_down_func = device_controller.get_device_action(target_system, 'keyDown')
                for keyPressKey in keyPressKeys:
                    key_down_func(keyPressKey)
                    if not is_secret:
                        typed_chars_log += keyPressKey + ' '
                    else:
                        typed_chars_log += '* '
                delay_val = RandomVariableHelper.get_rv_val(keyboard_action["actionData"])[0]
                script_logger.log('Sleeping for {} seconds'.format(delay_val))
                time.sleep(delay_val)
                key_up_func = device_controller.get_device_action(target_system, 'keyUp')
                for keyPressKey in keyPressKeys:
                    key_up_func(keyPressKey)
        script_logger.log(typed_chars_log)
        script_logger.get_action_log().append_post_file(
            'text',
            'keyboardAction-log.txt',
            typed_chars_log
        )
        return ScriptExecutionState.SUCCESS, state, context