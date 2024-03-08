import pyautogui
import time
from rv_helper import RandomVariableHelper
from script_execution_state import ScriptExecutionState
from script_logger import ScriptLogger
from script_engine_utils import state_eval
script_logger = ScriptLogger()

KEYBOARD_KEYS = set(pyautogui.KEYBOARD_KEYS)


class DeviceActionInterpreter:
    def __init__(self):
        pass

    @staticmethod
    def parse_keyboard_action(device, keyboard_action, state, context):
        script_logger.log('keyboard-expression-' + str(keyboard_action["actionGroup"]), ' type: ',
              keyboard_action["actionData"]["keyboardActionType"], ' expression: ',
              keyboard_action["actionData"]["keyboardExpression"], ' isHotKey: ',
              keyboard_action["actionData"]["isHotKey"] == 'isHotKey',
              (
                  keyboard_action["actionData"]["keyboardExpression"].strip()
              ).split(",") if
              keyboard_action["actionData"]["isHotKey"] == 'isHotKey' else '')
        if keyboard_action["actionData"]["isHotKey"] == 'isHotKey':
            if keyboard_action["actionData"]["keyboardActionType"] == "keyPress":
                device.hotkey((
                    keyboard_action["actionData"]["keyboardExpression"].strip()
                ).split(","))
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                hotKeyKeys = keyboard_action["actionData"]["keyboardExpression"].split(",")
                for hotKeyKey in hotKeyKeys:
                    device.keyDown(hotKeyKey)
                time.sleep(RandomVariableHelper.get_rv_val(keyboard_action))
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
            elif keyboard_action["actionData"]["keyboardActionType"] == "keyPressAndHold":
                for keyPressKey in keyPressKeys:
                    device.keyDown(keyPressKey)
                time.sleep(RandomVariableHelper.get_rv_val(keyboard_action))
                for keyPressKey in keyPressKeys:
                    device.keyUp(keyPressKey)
        return ScriptExecutionState.SUCCESS, state, context