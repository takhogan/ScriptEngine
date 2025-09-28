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
    def parse_keyboard_action(device_controller, keyboard_action, state, context, device_params=None):
        action_type = keyboard_action["actionData"]["keyboardActionType"]
        keyboard_expression = keyboard_action["actionData"]["keyboardExpression"]
        
        # Log action information
        script_logger.log(f'KeyboardActionType: {action_type}')
        script_logger.log(f'KeyboardExpression: {keyboard_expression}')
        
        typed_chars_log = 'Typed Characters: '
        script_logger.get_action_log().add_post_file(
            'text',
            'keyboardAction-log.txt',
            f'KeyboardActionType: {action_type}\nKeyboardExpression: {keyboard_expression}\n'
        )
        
        target_system = keyboard_action["actionData"]["targetSystem"]
        dummy_mode = device_controller.get_device_attribute(target_system, 'dummy_mode', device_params)
        is_secret = False

        if dummy_mode:
            script_logger.log('DeviceActionIntepreter: script running in dummy mode, returning from keyboard action')
            return
            
        if action_type == "hotkey":
            hot_key_keys = []
            raw_keys = keyboard_expression.strip().split(",")
            
            for key in raw_keys:
                # Remove braces if present: {key} → key
                clean_key = key.strip()
                if clean_key.startswith('{') and clean_key.endswith('}'):
                    clean_key = clean_key[1:-1]
                if clean_key:  # Only add non-empty keys
                    hot_key_keys.append(clean_key)
            
            script_logger.log(f'HotKeyKeys {hot_key_keys}')
            
            hot_key_func = device_controller.get_device_action(target_system, 'hotkey', device_params)
            hot_key_func(*hot_key_keys)
            typed_chars_log += ' '.join(hot_key_keys)
            
        elif action_type == "keyDown":
            keys,is_secret = DeviceActionInterpreter.process_expression(keyboard_expression, state)
            key_down_func = device_controller.get_device_action(target_system, 'key_down', device_params)
            
            for key in keys:
                key_down_func(key)
                typed_chars_log += ('* ' if is_secret else key + ' ')

        elif action_type == "keyUp":
            keys,is_secret = DeviceActionInterpreter.process_expression(keyboard_expression, state)
            key_up_func = device_controller.get_device_action(target_system, 'key_up', device_params)
            
            for key in keys:
                key_up_func(key)
                typed_chars_log += ('* ' if is_secret else key + ' ')

        elif action_type == "keyPress":
            keys,is_secret = DeviceActionInterpreter.process_expression(keyboard_expression, state)
            press_func = device_controller.get_device_action(target_system, 'key_press', device_params)
            for key in keys:
                press_func(key)
                typed_chars_log += ('* ' if is_secret else key + ' ')
        
        script_logger.log(typed_chars_log)
        script_logger.get_action_log().append_post_file(
            'text',
            'keyboardAction-log.txt',
            typed_chars_log
        )
        return ScriptExecutionState.SUCCESS, state, context
        
    @staticmethod
    def process_expression(expression, state):
        """Process a keyboard expression, handling escaped characters and variables."""
        is_escaped_char = False
        escaped_char = ''
        keys = []
        is_secret = False
        
        for char_index, expression_char in enumerate(str(expression)):
            if is_escaped_char:
                if expression_char == '}':
                    is_escaped_char = False
                    if escaped_char in KEYBOARD_KEYS:
                        keys.append(escaped_char)
                    else:
                        eval_expression = state_eval(escaped_char, {}, state)
                        is_secret = isinstance(eval_expression, SecureSecret)
                        if is_secret:
                            eval_expression = eval_expression.get_value()
                        else:
                            eval_expression = str(eval_expression)
                        
                        for eval_expression_char in eval_expression:
                            keys.append(eval_expression_char)
                    escaped_char = ''
                else:
                    escaped_char += expression_char
            elif expression_char == '{':
                is_escaped_char = True
            else:
                keys.append(expression_char)
                
        return keys, is_secret