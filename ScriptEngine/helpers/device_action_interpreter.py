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
        script_logger.log(f'KeyboardActionType: {action_type}', level='debug')
        script_logger.log(f'KeyboardExpression: {keyboard_expression}', level='debug')
        
        typed_chars_log = 'Typed Characters: '
        script_logger.get_action_log().add_post_file(
            'text',
            'keyboardAction-log.txt',
            f'KeyboardActionType: {action_type}\nKeyboardExpression: {keyboard_expression}\n'
        )
        
        target_system = keyboard_action["actionData"]["targetSystem"]
        dummy_mode = device_controller.get_device_attribute(target_system, 'dummy_mode', device_params)

        if dummy_mode:
            script_logger.log('DeviceActionIntepreter: script running in dummy mode, returning from keyboard action')
            return

        # What was sent, key by key, with when: a target in firmware (a
        # BitLocker PIN prompt, which a PiKVM shows no video of) drops keys
        # without any sign, so the timing is what there is to go on.
        key_events = []
        started = time.monotonic()

        def timed(op, shown_keys, send):
            sent_at = time.monotonic()
            send()
            key_events.append((sent_at - started, op, shown_keys, time.monotonic() - sent_at))

        hid_before = DeviceActionInterpreter.hid_state(device_controller, target_system, device_params)
            
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
            
            script_logger.log(f'HotKeyKeys {hot_key_keys}', level='debug')
            
            hot_key_func = device_controller.get_device_action(target_system, 'hotkey', device_params)
            timed('hotkey', '+'.join(hot_key_keys), lambda: hot_key_func(hot_key_keys))
            typed_chars_log += ' '.join(hot_key_keys)

        elif action_type in ("keyDown", "keyUp", "keyPress"):
            op, device_action = {
                "keyDown": ('down', 'key_down'),
                "keyUp": ('up', 'key_up'),
                "keyPress": ('press', 'key_press'),
            }[action_type]
            keys, secret_flags = DeviceActionInterpreter.process_expression(keyboard_expression, state)
            key_func = device_controller.get_device_action(target_system, device_action, device_params)

            for key, is_secret in zip(keys, secret_flags):
                shown = '*' if is_secret else key
                timed(op, shown, lambda key=key: key_func(key))
                typed_chars_log += shown + ' '

        hid_after = DeviceActionInterpreter.hid_state(device_controller, target_system, device_params)
        script_logger.log(typed_chars_log, level='debug')
        script_logger.get_action_log().append_post_file(
            'text',
            'keyboardAction-log.txt',
            typed_chars_log + '\n' + DeviceActionInterpreter.describe_key_events(key_events, hid_before, hid_after)
        )
        script_logger.get_action_log().set_summary(typed_chars_log.strip())
        return ScriptExecutionState.SUCCESS, state, context
        
    @staticmethod
    def hid_state(device_controller, target_system, device_params=None):
        """The device's report of its keyboard (a PiKVM's kvmd), or None for a
        device that has none to give."""
        try:
            read = device_controller.get_device_attribute(target_system, 'hid_state', device_params)
        except Exception:
            # Only a PiKVM has one; the keys are what matters, not this.
            return None
        try:
            return read()
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def describe_key_events(key_events, hid_before=None, hid_after=None):
        """The key events of one keyboard action as lines for its log: when each
        was sent, in seconds from the action's start, and how long sending it
        took (a PiKVM press holds the key and waits a gap). Sent is not
        received: nothing acknowledges a key."""
        lines = ['Key events (seconds from the start of the action; sent, not acknowledged by the target):']
        for at, op, shown, took in key_events:
            lines.append('  +{:.3f}s {} {} ({:.3f}s)'.format(at, op, shown, took))
        if not key_events:
            lines.append('  none')
        for label, hid in (('before', hid_before), ('after', hid_after)):
            if hid is not None:
                lines.append('Keyboard as the device reported it {}: {}'.format(label, DeviceActionInterpreter.describe_hid(hid)))
        return '\n'.join(lines) + '\n'

    @staticmethod
    def describe_hid(hid):
        if 'error' in hid:
            return 'could not be read ({})'.format(hid['error'])
        leds = hid.get('leds') or {}
        led_text = ', '.join('{} {}'.format(name, 'on' if on else 'off') for name, on in sorted(leds.items()))
        return 'keyboard {}{}'.format(
            'online' if hid.get('keyboard_online') else 'OFFLINE (the target has no USB keyboard from it: keys go nowhere)'
            if hid.get('keyboard_online') is False else 'state unknown',
            '; LEDs ' + led_text if led_text else ''
        )

    @staticmethod
    def process_expression(expression, state):
        """Process a keyboard expression, handling escaped characters and
        variables. Answers the keys and, for each key, whether it came from a
        secret, so a log can mask exactly those."""
        is_escaped_char = False
        escaped_char = ''
        keys = []
        secret_flags = []
        
        for char_index, expression_char in enumerate(str(expression)):
            if is_escaped_char:
                if expression_char == '}':
                    is_escaped_char = False
                    if escaped_char in KEYBOARD_KEYS:
                        keys.append(escaped_char)
                        secret_flags.append(False)
                    else:
                        eval_expression = state_eval(escaped_char, {}, state)
                        is_secret = isinstance(eval_expression, SecureSecret)
                        if is_secret:
                            eval_expression = eval_expression.get_value()
                        else:
                            eval_expression = str(eval_expression)

                        for eval_expression_char in eval_expression:
                            keys.append(eval_expression_char)
                            secret_flags.append(is_secret)
                    escaped_char = ''
                else:
                    escaped_char += expression_char
            elif expression_char == '{':
                is_escaped_char = True
            else:
                keys.append(expression_char)
                secret_flags.append(False)

        return keys, secret_flags