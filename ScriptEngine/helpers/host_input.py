"""Keyboard and mouse input on the machine the engine runs on.

On Windows every key and click goes through pydirectinput_rgx, which sends
scan codes with SendInput. pyautogui sends virtual-key codes through
keybd_event, and some targets read those twice: in the Citrix Workspace viewer
every typed character arrived doubled. Other platforms keep pyautogui.
Screenshots never come from here.

Scan codes go through the keyboard layout of the window that has the focus.
Where that layout has dead keys (US-International and many European layouts:
' " ` ~ ^ on US-International), a dead key waits for the next key and
combines with it: ' then a types á. So a character whose key is dead in the
active layout is followed by a Space, the layout's own way to type the
character itself. The layout checked is this machine's, for the foreground
window. A remote viewer (Citrix, RDP) that passes scan codes on has them read
by the remote session's layout: the fix holds there only while the two
layouts agree on dead keys, which they do when the viewer syncs the client
layout to the session (Citrix's keyboard layout sync).

See https://github.com/reggx/pydirectinput_rgx
"""
import ctypes
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

# What follows a dead key to type the character itself: in Windows layouts a
# dead key then Space gives the character alone, with no space.
DEAD_KEY_RELEASE = 'space'

# winuser.h
_MAPVK_VSC_TO_VK = 1
_VK_SHIFT = 0x10
_VK_SPACE = 0x20
_TOUNICODE_KEEP_STATE = 0x4  # Windows 10 1607+: leave the keyboard state as is


def _load_user32():
    """user32 with the signatures the dead-key check calls, or None off
    Windows."""
    if not IS_WINDOWS:
        return None
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HKL)
    user32.MapVirtualKeyExW.restype = wintypes.UINT
    user32.ToUnicodeEx.argtypes = (
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_ubyte),
        wintypes.LPWSTR, ctypes.c_int, wintypes.UINT, wintypes.HKL,
    )
    user32.ToUnicodeEx.restype = ctypes.c_int
    return user32


try:
    _user32 = _load_user32()
except Exception:  # an unusual Windows: type as if no key were dead
    _user32 = None

# (layout, scan code, shifted) -> whether that key is dead in that layout.
_dead_key_cache = {}


def _active_keyboard_layout():
    """The keyboard layout (HKL) of the thread that owns the foreground window:
    the one that turns the scan codes sent next into characters. With no
    foreground window, this thread's layout."""
    thread_id = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    return _user32.GetKeyboardLayout(thread_id)


def _is_dead_key(scancode, shifted):
    """Whether the key at `scancode`, with Shift held when `shifted`, is a dead
    key in the active keyboard layout. False off Windows, for a key the layout
    does not map, and whenever Windows cannot say."""
    if _user32 is None or not isinstance(scancode, int) or not 0 < scancode < 0x80:
        return False
    try:
        layout = _active_keyboard_layout()
        cache_key = (layout, scancode, shifted)
        if cache_key not in _dead_key_cache:
            _dead_key_cache[cache_key] = _layout_key_is_dead(layout, scancode, shifted)
        return _dead_key_cache[cache_key]
    except Exception:
        return False


def _layout_key_is_dead(layout, scancode, shifted):
    vk = _user32.MapVirtualKeyExW(scancode, _MAPVK_VSC_TO_VK, layout)
    if not vk:
        return False
    key_state = (ctypes.c_ubyte * 256)()
    if shifted:
        key_state[_VK_SHIFT] = 0x80
    buffer = ctypes.create_unicode_buffer(8)
    result = _user32.ToUnicodeEx(vk, scancode, key_state, buffer, len(buffer),
                                 _TOUNICODE_KEEP_STATE, layout)
    if result < 0:
        # Before Windows 10 1607 the dead key stays pending in this thread's
        # (not the target's) keyboard state: clear it with a Space.
        _user32.ToUnicodeEx(_VK_SPACE, 0x39, (ctypes.c_ubyte * 256)(), buffer,
                            len(buffer), _TOUNICODE_KEEP_STATE, layout)
        return True
    return False


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
            sent = bool(module.press(base_key, _pause=False))
        finally:
            module.keyUp('shift', _pause=False)
        return _release_dead_key(module, base_key, True, sent)
    if key in module.KEYBOARD_MAPPING:
        sent = bool(module.press(key, _pause=False))
        return _release_dead_key(module, key, False, sent) if len(key) == 1 else sent
    if len(key) == 1:
        # Not on a US keyboard (an accented letter, say): send the character
        # itself. A remote viewer may not pass these on.
        return bool(module.unicode_press(key, _pause=False))
    return False


def _release_dead_key(module, key, shifted, sent):
    """After a character's key: if that key is dead in the active layout, press
    Space so the character is typed by itself instead of combining with the
    next one. Answers whether the character went out."""
    if sent and _is_dead_key(module.KEYBOARD_MAPPING.get(key), shifted):
        return bool(module.press(DEAD_KEY_RELEASE, _pause=False))
    return sent
