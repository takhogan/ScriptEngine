"""A keyboard action on a PiKVM types its text exactly or not at all (agent-toolkits
plan §7, item 5). pikvm_lib sent a character it has no key for as Key{char},
which the PiKVM ignores, and a CRLF as two Enters, so a VDI_WriteFile could
write a file that differs from its input without a word. The engine checks
the text itself, so this holds on a host still running an older pikvm_lib."""
import os
import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.helpers import device_action_interpreter as dai_mod
from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter
from ScriptEngine.helpers.typeable_text import TYPEABLE_CHARACTERS, UntypeableTextError, prepare_typed_keys
from ScriptEngine.helpers.user_secrets_helper import SecureSecret
from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager

from test_keyboard_key_log import FakeActionLog, FakeController, keyboard


class FakeKvm(PiKVMDeviceManager):
    """A PiKVM manager down to what a keyboard action calls, recording each key."""

    def __init__(self):
        self.sent = []
        self.dummy_mode = False

    def key_press(self, key):
        self.sent.append(('press', key))

    def key_down(self, key):
        self.sent.append(('down', key))

    def hid_state(self):
        return None


@pytest.fixture
def action_log(monkeypatch):
    log = FakeActionLog()
    monkeypatch.setattr(dai_mod.script_logger, 'get_action_log', lambda: log)
    dai_mod.script_logger.set_log_file_path(os.devnull)
    dai_mod.script_logger.set_log_to_stdout(False)
    return log


def test_the_typeable_characters_are_printable_ascii_tab_and_line_breaks():
    assert TYPEABLE_CHARACTERS == frozenset(string.printable) - {'\x0b', '\x0c'}


def test_the_set_is_pikvm_libs_when_it_has_one():
    keymaps = pytest.importorskip('pikvm_lib.keymaps')
    if not hasattr(keymaps, 'TYPEABLE_CHARACTERS'):
        pytest.skip('this pikvm_lib predates its own text check')
    assert TYPEABLE_CHARACTERS == keymaps.TYPEABLE_CHARACTERS


def test_line_breaks_are_one_enter_each():
    keys, flags = prepare_typed_keys(list('a\r\nb\rc\nd'), [False] * 8)
    assert keys == ['a', '\n', 'b', '\n', 'c', '\n', 'd']
    assert flags == [False] * 7


def test_named_keys_pass():
    keys, _ = prepare_typed_keys(['enter', 'a', 'f5'], [False] * 3)
    assert keys == ['enter', 'a', 'f5']


def test_untypeable_text_names_the_character_and_its_position():
    with pytest.raises(UntypeableTextError) as raised:
        prepare_typed_keys(list('café'), [False] * 4)
    assert "'é' (U+00E9) at position 3" in str(raised.value)


def test_a_secrets_character_is_not_named():
    with pytest.raises(UntypeableTextError) as raised:
        prepare_typed_keys(list('pässword'), [True] * 8)
    assert 'ä' not in str(raised.value)
    assert 'a character of a secret at position 1' in str(raised.value)


def test_a_crlf_from_a_variable_is_typed_as_one_enter(action_log):
    device = FakeKvm()
    status, _, _ = DeviceActionInterpreter.parse_keyboard_action(
        FakeController(device), keyboard('keyPress', '{text}'), {'text': 'C:\\a:b\r\nx\ty'}, {})
    assert status == ScriptExecutionState.SUCCESS
    assert device.sent == [('press', c) for c in 'C:\\a:b\nx\ty']


def test_untypeable_text_fails_the_action_and_types_nothing(action_log):
    device = FakeKvm()
    status, _, _ = DeviceActionInterpreter.parse_keyboard_action(
        FakeController(device), keyboard('keyPress', 'ok {text}'), {'text': 'naïve'}, {})
    assert status == ScriptExecutionState.FAILURE
    assert device.sent == []
    assert "Refused: cannot type 'ï' (U+00EF) at position 5" in action_log.files['keyboardAction-log.txt']
    assert action_log.summary.startswith('refused: ')


def test_a_secret_with_an_untypeable_character_is_refused_without_showing_it(action_log):
    device = FakeKvm()
    status, _, _ = DeviceActionInterpreter.parse_keyboard_action(
        FakeController(device), keyboard('keyPress', '{pin}'), {'pin': SecureSecret('12€4')}, {})
    assert status == ScriptExecutionState.FAILURE
    assert device.sent == []
    assert '€' not in action_log.files['keyboardAction-log.txt']
    assert '12' not in action_log.summary


def test_a_device_without_the_check_types_as_before(action_log):
    from test_keyboard_key_log import FakeDevice
    device = FakeDevice()
    status, _, _ = DeviceActionInterpreter.parse_keyboard_action(
        FakeController(device), keyboard('keyPress', '{text}'), {'text': 'é\r\n'}, {})
    assert status == ScriptExecutionState.SUCCESS
    assert device.sent == [('press', 'é'), ('press', '\r'), ('press', '\n')]
