"""Keyboard and mouse input on the machine the engine runs on.

On Windows every key and click goes through pydirectinput_rgx, which sends
scan codes with SendInput. pyautogui sends virtual-key codes through
keybd_event, and some targets read those twice: in the Citrix Workspace viewer
every typed character arrived doubled. Other platforms keep pyautogui.
Screenshots never come from here.

See https://github.com/reggx/pydirectinput_rgx
"""
import platform
import time

import pyautogui

IS_WINDOWS = platform.system() == 'Windows'

if IS_WINDOWS:
    import pydirectinput as input_module  # type: ignore[import-not-found]
else:
    input_module = pyautogui

# What pyautogui slept after every press (pyautogui.PAUSE), kept so typing on
# Windows goes at the speed it always has. pydirectinput's own pause is 0.01 s.
TYPED_KEY_PAUSE_S = 0.1

# The characters typed with Shift held on a US keyboard, and the key under each.
# pydirectinput maps these too, but only shifts them when asked (auto_shift)
# and then releases Shift before the key; holding Shift here keeps the order a
# person types in: Shift down, key down, key up, Shift up.
SHIFTED_KEYS = dict(zip(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ~!@#$%^&*()_+{}|:"<>?',
    'abcdefghijklmnopqrstuvwxyz`1234567890-=[]\\;\',./',
))

# Characters pyautogui typed that pydirectinput has no name for.
KEY_ALIASES = {'\r': 'enter'}


def press_key(key, module=None):
    """Press and release one key: a single character, or a key name such as
    'enter' or 'f5'. Answers whether it was sent. Never logs the key: a
    character may be part of a secret."""
    module = input_module if module is None else module
    if module is pyautogui:
        pyautogui.press(key)
        return True
    sent = _press_scancode_key(module, key)
    time.sleep(TYPED_KEY_PAUSE_S)
    return sent


def _press_scancode_key(module, key):
    key = KEY_ALIASES.get(key, key)
    if len(key) > 1:
        key = key.lower()
    base_key = SHIFTED_KEYS.get(key)
    if base_key is not None:
        module.keyDown('shift', _pause=False)
        try:
            return bool(module.press(base_key, _pause=False))
        finally:
            module.keyUp('shift', _pause=False)
    if key in module.KEYBOARD_MAPPING:
        return bool(module.press(key, _pause=False))
    if len(key) == 1:
        # Not on a US keyboard (an accented letter, say): send the character
        # itself. A remote viewer may not pass these on.
        return bool(module.unicode_press(key, _pause=False))
    return False
