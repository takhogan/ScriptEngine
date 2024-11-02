import pyautogui
import time

from rv_helper import RandomVariableHelper
from script_execution_state import ScriptExecutionState
from script_logger import ScriptLogger
from script_engine_utils import state_eval
script_logger = ScriptLogger()

KEYBOARD_KEYS = set(pyautogui.KEYBOARD_KEYS)


class DeviceActionInterpreter:
    def __init__(self, dummy_mode=False):
        pass

    @staticmethod
    def parse_keyboard_action(device, keyboard_action, state, context):
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
        if device.dummy_mode:
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
                device.hotkey(hot_key_keys)
                typed_chars_log += ' '.join(hot_key_keys)
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                hotKeyKeys = keyboard_action["actionData"]["keyboardExpression"].split(",")
                for hotKeyKey in hotKeyKeys:
                    device.keyDown(hotKeyKey)
                typed_chars_log += ' '.join(hotKeyKeys)
                delay_val = RandomVariableHelper.get_rv_val(keyboard_action)[0]
                script_logger.log('Sleeping for {} seconds'.format(delay_val))
                time.sleep(delay_val)
                for hotKeyKey in reversed(hotKeyKeys):
                    device.keyUp(hotKeyKey)
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
                for keyPressKey in keyPressKeys:
                    device.press(keyPressKey)
                    typed_chars_log += keyPressKey + ' '
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                for keyPressKey in keyPressKeys:
                    device.keyDown(keyPressKey)
                    typed_chars_log += keyPressKey + ' '
                delay_val = RandomVariableHelper.get_rv_val(keyboard_action)[0]
                script_logger.log('Sleeping for {} seconds'.format(delay_val))
                time.sleep(delay_val)
                for keyPressKey in keyPressKeys:
                    device.keyUp(keyPressKey)
        script_logger.log(typed_chars_log)
        script_logger.get_action_log().append_post_file(
            'text',
            'keyboardAction-log.txt',
            typed_chars_log
        )
        return ScriptExecutionState.SUCCESS, state, context