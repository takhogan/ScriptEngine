"""keyboardAction's result fields (UI_MAPPER.md §8, E2): keys, masked for secrets."""
import pytest

import ScriptEngine.helpers.device_action_interpreter as dai_mod
from ScriptEngine.common.logging.action_result import merge
from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter
from ScriptEngine.helpers.user_secrets_helper import SecureSecret


class ActionLog:
    def __init__(self):
        self.result = {}
        self.post = ''

    def update_result(self, fields):
        merge(self.result, fields)

    def add_post_file(self, file_type, path, contents, *args, **kwargs):
        self.post += contents

    def append_post_file(self, file_type, path, contents, *args, **kwargs):
        self.post += contents

    def set_summary(self, summary):
        self.summary = summary


class Logger:
    def __init__(self):
        self.action_log = ActionLog()

    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return self.action_log


class Controller:
    def __init__(self):
        self.sent = []

    def get_device_attribute(self, target, attr, device_params=None):
        # A plain device: not in dummy mode, and nothing a PiKVM has
        # (prepare_typed_keys, hid_state).
        if attr == 'dummy_mode':
            return False
        raise AttributeError(attr)

    def get_device_action(self, target, action_name, device_params=None):
        return lambda key: self.sent.append((action_name, key))


@pytest.fixture
def logger(monkeypatch):
    fake = Logger()
    monkeypatch.setattr(dai_mod, 'script_logger', fake)
    return fake


def keyboard(action_type, expression):
    return {'actionName': 'keyboardAction',
            'actionData': {'targetSystem': 'adb', 'keyboardActionType': action_type, 'keyboardExpression': expression}}


def test_plain_keys_are_recorded(logger):
    controller = Controller()
    DeviceActionInterpreter.parse_keyboard_action(controller, keyboard('keyPress', 'ab{enter}'), {}, {})
    result = logger.action_log.result
    assert result['keyboard_action'] == 'keyPress'
    assert result['keys'] == ['a', 'b', 'enter']
    assert result['masked'] is False
    assert result['input_at'].endswith('Z')
    assert [key for _, key in controller.sent] == ['a', 'b', 'enter']


def test_a_hotkey_is_recorded_as_its_chord(logger):
    DeviceActionInterpreter.parse_keyboard_action(Controller(), keyboard('hotkey', '{ctrl},{c}'), {}, {})
    assert logger.action_log.result['keys'] == ['ctrl', 'c']


def test_a_secret_masks_the_keys_and_their_count(logger):
    controller = Controller()
    state = {'password': SecureSecret('hunter2'), 'name': 'bob'}
    DeviceActionInterpreter.parse_keyboard_action(controller, keyboard('keyPress', '{password}{name}'), state, {})
    result = logger.action_log.result
    assert result['keys'] is None and result['masked'] is True
    # A variable after the secret does not unmask what the secret typed.
    assert 'hunter2' not in logger.action_log.post and 'h ' not in logger.action_log.post
    assert ''.join(key for _, key in controller.sent) == 'hunter2bob'


def test_dummy_mode_succeeds_and_sends_nothing(logger):
    class Dummy(Controller):
        def get_device_attribute(self, target, attr, device_params=None):
            return attr == 'dummy_mode'
    controller = Dummy()
    status, _, _ = DeviceActionInterpreter.parse_keyboard_action(controller, keyboard('keyPress', 'hi'), {}, {})
    assert status.name == 'SUCCESS'
    assert controller.sent == [] and logger.action_log.result['input_at'] is None
