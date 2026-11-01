"""keyboardAction's log: each key sent, with when, masked exactly where it came
from a secret, and a PiKVM's report of its keyboard before and after."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers import device_action_interpreter as dai_mod
from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter
from ScriptEngine.helpers.user_secrets_helper import SecureSecret
from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager


class FakeActionLog:
    def __init__(self):
        self.files = {}
        self.summary = None
        self.result = {}

    def update_result(self, fields):
        self.result.update(fields)

    def add_post_file(self, file_type, name, text):
        self.files[name] = text

    def append_post_file(self, file_type, name, text):
        self.files[name] = self.files.get(name, '') + text

    def set_summary(self, summary):
        self.summary = summary


class FakeDevice:
    def __init__(self, hid=None, hid_error=None):
        self.sent = []
        self.dummy_mode = False
        self._hid = hid
        self._hid_error = hid_error

    def key_press(self, key):
        self.sent.append(('press', key))

    def key_down(self, key):
        self.sent.append(('down', key))

    def hotkey(self, keys):
        self.sent.append(('hotkey', tuple(keys)))

    def hid_state(self):
        if self._hid_error:
            raise Exception(self._hid_error)
        return self._hid


class FakeController:
    def __init__(self, device, has_hid=True):
        self.device = device
        self.has_hid = has_hid

    def get_device_attribute(self, target, name, params=None):
        if name == 'hid_state' and not self.has_hid:
            raise AttributeError(name)
        return getattr(self.device, name)

    def get_device_action(self, target, name, params=None):
        return getattr(self.device, name)


@pytest.fixture
def action_log(monkeypatch):
    log = FakeActionLog()
    monkeypatch.setattr(dai_mod.script_logger, 'get_action_log', lambda: log)
    dai_mod.script_logger.set_log_file_path(os.devnull)
    dai_mod.script_logger.set_log_to_stdout(False)
    return log


def keyboard(action_type, expression):
    return {'actionData': {'keyboardActionType': action_type, 'keyboardExpression': expression, 'targetSystem': 'kvm'}}


def test_each_key_is_logged_with_when_it_was_sent_and_a_secret_masked_key_by_key(action_log):
    state = {'pin': SecureSecret('4711'), 'name': 'ann'}
    device = FakeDevice(hid={'online': True, 'keyboard_online': True, 'leds': {'num': True, 'caps': False}})
    DeviceActionInterpreter.parse_keyboard_action(FakeController(device), keyboard('keyPress', '{pin}{name}{enter}'), state, {})
    assert device.sent == [('press', c) for c in '4711ann'] + [('press', 'enter')]
    log = action_log.files['keyboardAction-log.txt']
    # A non-secret variable after a secret one used to unmask the secret in the log.
    assert '4711' not in log and '4711' not in action_log.summary
    assert action_log.summary == 'Typed Characters: * * * * a n n enter'
    # The result fields mask every key, and their count, once any came from a secret.
    assert action_log.result['keys'] is None and action_log.result['masked'] is True
    lines = [line for line in log.splitlines() if line.startswith('  +')]
    assert len(lines) == 8
    assert lines[0].split()[1:3] == ['press', '*']
    assert lines[-1].split()[1:3] == ['press', 'enter']
    times = [float(line.split()[0][1:-1]) for line in lines]
    assert times == sorted(times)
    assert 'Keyboard as the device reported it before: keyboard online; LEDs caps off, num on' in log
    assert 'Keyboard as the device reported it after: keyboard online' in log


def test_an_offline_keyboard_is_called_out(action_log):
    device = FakeDevice(hid={'online': True, 'keyboard_online': False, 'leds': {}})
    DeviceActionInterpreter.parse_keyboard_action(FakeController(device), keyboard('keyDown', 'a'), {}, {})
    assert 'keyboard OFFLINE (the target has no USB keyboard from it: keys go nowhere)' in action_log.files['keyboardAction-log.txt']


def test_a_device_without_a_keyboard_report_or_one_that_fails_still_types(action_log):
    device = FakeDevice()
    DeviceActionInterpreter.parse_keyboard_action(FakeController(device, has_hid=False), keyboard('hotkey', '{ctrl},{alt},{delete}'), {}, {})
    assert device.sent == [('hotkey', ('ctrl', 'alt', 'delete'))]
    log = action_log.files['keyboardAction-log.txt']
    assert 'hotkey ctrl+alt+delete' in log
    assert 'as the device reported it' not in log

    failing = FakeDevice(hid_error='connection refused')
    DeviceActionInterpreter.parse_keyboard_action(FakeController(failing), keyboard('keyPress', 'x'), {}, {})
    assert failing.sent == [('press', 'x')]
    assert 'could not be read (connection refused)' in action_log.files['keyboardAction-log.txt']


def test_process_expression_flags_each_key():
    keys, flags = DeviceActionInterpreter.process_expression('a{pin}{tab}{num}', {'pin': SecureSecret('xy'), 'num': 7})
    assert keys == ['a', 'x', 'y', 'tab', '7']
    assert flags == [False, True, True, False, False]


def test_pikvm_reports_kvmds_keyboard_state():
    class FakeKvm:
        def get_endpoint_state(self, path):
            assert path == '/api/hid'
            return {'online': True, 'busy': False, 'keyboard': {'online': False, 'leds': {'caps': False, 'scroll': False, 'num': True}}}

    manager = PiKVMDeviceManager.__new__(PiKVMDeviceManager)
    manager.instance = FakeKvm()
    manager.dummy_mode = False
    assert manager.hid_state() == {'online': True, 'keyboard_online': False, 'leds': {'caps': False, 'scroll': False, 'num': True}}
    manager.dummy_mode = True
    assert manager.hid_state() is None
