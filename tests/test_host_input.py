"""Typing on Windows goes through pydirectinput, one press per character, with
Shift held around the characters a US keyboard types with Shift."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers import host_input


class FakeDirectInput:
    """pydirectinput's key functions, recording what they were asked to send."""

    # The names this test types; the real map has about 230.
    KEYBOARD_MAPPING = {name: 0 for name in (
        list('abcdefghijklmnopqrstuvwxyz0123456789`-=[]\\;\',./ \n\t')
        + ['enter', 'tab', 'shift', 'ctrl', 'f5', 'backspace']
    )}

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


@pytest.fixture(autouse=True)
def no_typing_pause(monkeypatch):
    monkeypatch.setattr(host_input.time, 'sleep', lambda s: None)


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

