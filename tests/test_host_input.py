"""Typing on Windows goes through pydirectinput, one press per character, with
Shift held around the characters a US keyboard types with Shift; and the ADB
device's host-keyboard keys go through the same module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers import host_input


class FakeDirectInput:
    """pydirectinput's key functions, recording what they were asked to send."""

    # The names this test types, with their US scan codes; the real map has
    # about 230.
    KEYBOARD_MAPPING = dict(zip(
        list('1234567890-=') + ['backspace', 'tab'] + list('qwertyuiop[]') + ['enter', 'ctrl']
        + list('asdfghjkl;\'`') + ['shift'] + list('\\zxcvbnm,./'),
        range(0x02, 0x36),
    ))
    KEYBOARD_MAPPING.update({' ': 0x39, 'space': 0x39, '\n': 0x1C, '\t': 0x0F, 'f5': 0x3F})

    def __init__(self, sent=True):
        self.events = []
        self.sent = sent

    def press(self, key, **kwargs):
        assert kwargs == {'_pause': False}
        self.events.append(('press', key))
        return self.sent

    def keyDown(self, key, **kwargs):
        self.events.append(('down', key))
        return True

    def keyUp(self, key, **kwargs):
        self.events.append(('up', key))
        return True

    def unicode_press(self, key, **kwargs):
        self.events.append(('unicode', key))
        return True

    def hotkey(self, *keys):
        self.events.append(('hotkey', keys))


class FakeUser32:
    """The user32 calls the dead-key check makes, for one keyboard layout.
    `dead` holds (scan code, shifted) for the layout's dead keys."""

    def __init__(self, layout, dead=()):
        self.layout = layout
        self.dead = set(dead)
        self.lookups = []

    def GetForegroundWindow(self):
        return 0x1234

    def GetWindowThreadProcessId(self, hwnd, process_id):
        assert hwnd == 0x1234
        return 77

    def GetKeyboardLayout(self, thread_id):
        assert thread_id == 77
        return self.layout

    def MapVirtualKeyExW(self, code, map_type, layout):
        assert map_type == host_input._MAPVK_VSC_TO_VK and layout == self.layout
        return 0x100 + code  # any virtual key; ToUnicodeEx gets the scan code too

    def ToUnicodeEx(self, vk, scancode, key_state, buffer, size, flags, layout):
        assert flags == host_input._TOUNICODE_KEEP_STATE and layout == self.layout
        if vk == host_input._VK_SPACE:
            return 1
        assert vk == 0x100 + scancode
        shifted = bool(key_state[host_input._VK_SHIFT] & 0x80)
        self.lookups.append((scancode, shifted))
        return -1 if (scancode, shifted) in self.dead else 1


# US-International (00020409): ' and " on one key, ` and ~ on another, ^ on 6.
US_INTERNATIONAL_DEAD = {(0x28, False), (0x28, True), (0x29, False), (0x29, True), (0x07, True)}
US_INTERNATIONAL = 0x4090409 | 0x20000
US = 0x4090409


@pytest.fixture(autouse=True)
def no_typing_pause(monkeypatch):
    monkeypatch.setattr(host_input.time, 'sleep', lambda s: None)


@pytest.fixture(autouse=True)
def layout(monkeypatch):
    """No layout by default (off Windows, no key is dead); a test sets one with
    layout(FakeUser32(...))."""
    monkeypatch.setattr(host_input, '_dead_key_cache', {})
    monkeypatch.setattr(host_input, '_user32', None)

    def use(user32):
        monkeypatch.setattr(host_input, '_user32', user32)
        return user32
    return use


def type_text(text):
    fake = FakeDirectInput()
    for char in text:
        assert host_input.press_key(char, module=fake) is True
    return fake.events


def test_lower_case_and_digits_are_one_press_each_without_shift():
    assert type_text('az09') == [('press', 'a'), ('press', 'z'), ('press', '0'), ('press', '9')]


def test_capitals_hold_shift_around_the_lower_case_key():
    assert type_text('Aa Zz') == [
        ('down', 'shift'), ('press', 'a'), ('up', 'shift'),
        ('press', 'a'),
        ('press', ' '),
        ('down', 'shift'), ('press', 'z'), ('up', 'shift'),
        ('press', 'z'),
    ]


def test_shifted_symbols_hold_shift_around_their_unshifted_key():
    assert type_text('1!2@3#4$ _+?:') == [
        ('press', '1'), ('down', 'shift'), ('press', '1'), ('up', 'shift'),
        ('press', '2'), ('down', 'shift'), ('press', '2'), ('up', 'shift'),
        ('press', '3'), ('down', 'shift'), ('press', '3'), ('up', 'shift'),
        ('press', '4'), ('down', 'shift'), ('press', '4'), ('up', 'shift'),
        ('press', ' '),
        ('down', 'shift'), ('press', '-'), ('up', 'shift'),
        ('down', 'shift'), ('press', '='), ('up', 'shift'),
        ('down', 'shift'), ('press', '/'), ('up', 'shift'),
        ('down', 'shift'), ('press', ';'), ('up', 'shift'),
    ]


def test_every_shifted_key_has_an_unshifted_key_pydirectinput_maps():
    assert len(host_input.SHIFTED_KEYS) == 47
    for base in host_input.SHIFTED_KEYS.values():
        assert base in FakeDirectInput.KEYBOARD_MAPPING
        assert base not in host_input.SHIFTED_KEYS


def test_every_typed_character_is_exactly_one_press():
    text = 'Aa Bb Zz 1!2@3#4$ _+?:'
    presses = [event for event in type_text(text) if event[0] == 'press']
    assert len(presses) == len(text)


def test_shift_is_released_when_the_press_fails():
    fake = FakeDirectInput()

    def broken_press(key, **kwargs):
        raise OSError('SendInput failed')
    fake.press = broken_press
    with pytest.raises(OSError):
        host_input.press_key('A', module=fake)
    assert fake.events == [('down', 'shift'), ('up', 'shift')]


def test_key_names_are_lower_cased_and_carriage_return_is_enter():
    fake = FakeDirectInput()
    for key in ('enter', 'Enter', 'F5', '\r', '\n', '\t'):
        host_input.press_key(key, module=fake)
    assert fake.events == [
        ('press', 'enter'), ('press', 'enter'), ('press', 'f5'),
        ('press', 'enter'), ('press', '\n'), ('press', '\t'),
    ]


def test_a_character_off_the_us_keyboard_is_sent_as_unicode():
    assert type_text('é') == [('unicode', 'é')]


def test_an_unknown_key_name_sends_nothing_and_says_so():
    fake = FakeDirectInput()
    assert host_input.press_key('hanja', module=fake) is False
    assert fake.events == []


def test_a_press_windows_refused_is_reported():
    fake = FakeDirectInput(sent=False)
    assert host_input.press_key('a', module=fake) is False


def test_each_press_waits_as_long_as_pyautogui_did(monkeypatch):
    slept = []
    monkeypatch.setattr(host_input.time, 'sleep', slept.append)
    host_input.press_key('A', module=FakeDirectInput())
    assert slept == [0.1]


def test_off_windows_pyautogui_presses_the_key_as_before(monkeypatch):
    pressed = []
    monkeypatch.setattr(host_input.pyautogui, 'press', pressed.append)
    assert host_input.press_key('A', module=host_input.pyautogui) is True
    assert pressed == ['A']


# --- dead keys ----------------------------------------------------------------

def test_each_dead_key_of_us_international_is_followed_by_space(layout):
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    assert type_text("'") == [('press', "'"), ('press', 'space')]
    assert type_text('"') == [('down', 'shift'), ('press', "'"), ('up', 'shift'), ('press', 'space')]
    assert type_text('`') == [('press', '`'), ('press', 'space')]
    assert type_text('~') == [('down', 'shift'), ('press', '`'), ('up', 'shift'), ('press', 'space')]
    assert type_text('^') == [('down', 'shift'), ('press', '6'), ('up', 'shift'), ('press', 'space')]


def test_the_letter_after_a_dead_key_is_typed_by_itself(layout):
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    assert type_text("'a ~n") == [
        ('press', "'"), ('press', 'space'), ('press', 'a'),
        ('press', ' '),
        ('down', 'shift'), ('press', '`'), ('up', 'shift'), ('press', 'space'), ('press', 'n'),
    ]


def test_a_dead_key_before_a_space_still_gets_its_own_space(layout):
    # ' then Space types ' alone, so the text's own space needs a second one.
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    assert type_text("' x") == [
        ('press', "'"), ('press', 'space'), ('press', ' '), ('press', 'x'),
    ]


def test_the_unshifted_key_under_a_shifted_dead_key_is_not_dead(layout):
    # On US-International ^ (Shift+6) is dead but 6 is not.
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    assert type_text('6^') == [
        ('press', '6'),
        ('down', 'shift'), ('press', '6'), ('up', 'shift'), ('press', 'space'),
    ]


def test_a_layout_without_dead_keys_types_them_as_one_press(layout):
    layout(FakeUser32(US))
    assert type_text('\'"`~^') == [
        ('press', "'"),
        ('down', 'shift'), ('press', "'"), ('up', 'shift'),
        ('press', '`'),
        ('down', 'shift'), ('press', '`'), ('up', 'shift'),
        ('down', 'shift'), ('press', '6'), ('up', 'shift'),
    ]


def test_the_probe_text_types_every_character_literally(layout):
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    text = "'a \"e ~n ^o `u ' x"
    events = type_text(text)
    presses = [event[1] for event in events if event[0] == 'press']
    assert presses.count('space') == 6
    assert len(presses) == len(text) + 6


def test_letters_digits_and_keys_names_are_never_dead_checked_twice(layout):
    user32 = layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    type_text("aa''")
    host_input.press_key('enter', module=FakeDirectInput())
    host_input.press_key('f5', module=FakeDirectInput())
    # One lookup per (layout, key, Shift); key names are not characters.
    assert user32.lookups == [(0x1E, False), (0x28, False)]


def test_switching_layout_is_seen_on_the_next_key(layout):
    user32 = layout(FakeUser32(US))
    assert type_text("'") == [('press', "'")]
    user32.layout = US_INTERNATIONAL
    user32.dead = US_INTERNATIONAL_DEAD
    assert type_text("'") == [('press', "'"), ('press', 'space')]


def test_no_space_follows_a_dead_key_that_was_not_sent(layout):
    layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))
    fake = FakeDirectInput(sent=False)
    assert host_input.press_key("'", module=fake) is False
    assert fake.events == [('press', "'")]


def test_a_failing_layout_check_types_as_if_no_key_were_dead(layout):
    user32 = layout(FakeUser32(US_INTERNATIONAL, US_INTERNATIONAL_DEAD))

    def broken(*args):
        raise OSError('no layout')
    user32.GetKeyboardLayout = broken
    assert type_text("'") == [('press', "'")]


# --- the devices --------------------------------------------------------------

def test_desktop_key_press_goes_through_the_input_module(monkeypatch):
    from ScriptEngine.managers import desktop_device_manager as ddm
    fake = FakeDirectInput()
    monkeypatch.setattr(host_input, 'input_module', fake)
    device = ddm.DesktopDeviceManager.__new__(ddm.DesktopDeviceManager)
    device.dummy_mode = False
    device._ensure_initialized_for_keyboard = lambda: None
    for char in 'P@':
        device.key_press(char)
    assert fake.events == [
        ('down', 'shift'), ('press', 'p'), ('up', 'shift'),
        ('down', 'shift'), ('press', '2'), ('up', 'shift'),
    ]


def test_desktop_key_press_failure_log_never_names_a_character(monkeypatch):
    from ScriptEngine.managers import desktop_device_manager as ddm
    logged = []
    monkeypatch.setattr(host_input, 'input_module', FakeDirectInput(sent=False))
    monkeypatch.setattr(ddm.script_logger, 'log', lambda *a, **k: logged.append(' '.join(map(str, a))))
    device = ddm.DesktopDeviceManager.__new__(ddm.DesktopDeviceManager)
    device.dummy_mode = False
    device._ensure_initialized_for_keyboard = lambda: None
    device.key_press('q')
    device.key_press('f5')
    assert logged == [
        'PythonHostController: a key press was not sent',
        'PythonHostController: a key press was not sent (f5)',
    ]


def test_adb_host_keys_go_through_the_input_module(monkeypatch):
    from ScriptEngine.managers import adb_device_manager as adm
    fake = FakeDirectInput()
    monkeypatch.setattr(host_input, 'input_module', fake)
    monkeypatch.setattr(adm.script_logger, 'log', lambda *a, **k: None)
    device = adm.ADBDeviceManager.__new__(adm.ADBDeviceManager)
    device.key_down('shift')
    device.key_up('shift')
    device.hotkey(['ctrl', 'c'])
    assert fake.events == [('down', 'shift'), ('up', 'shift'), ('hotkey', ('ctrl', 'c'))]
