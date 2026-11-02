"""--inputs-file: an agent tool call's inputs as literal values, assigned without
eval, so typed text never becomes Python source (agent-toolkits plan §7,
item 4). test_agent_tool_run.py runs them through script_manager end to end."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ScriptEngine.script_executor as script_executor_mod
from ScriptEngine.script_executor import ScriptExecutor
from ScriptEngine.script_manager import InputsFileError, load_inputs_file, merge_literal_inputs, parse_constants

VALUES = {
    'windows_path': 'C:\\Users\\x\\a:b.txt',
    'crlf_text': 'line one\r\nline two\r\n\r\nend',
    'large': 'x' * 100 * 1024,
    'looks_like_python': "__import__('os').system('x')",
    'number': 3,
    'nothing': None,
    'nested': {'a': [1, 'b']},
}


def write(tmp_path, content, encoding='utf-8'):
    path = tmp_path / 'inputs.json'
    path.write_bytes(content.encode(encoding) if isinstance(content, str) else content)
    return str(path)


def test_values_load_as_they_are(tmp_path):
    assert load_inputs_file(write(tmp_path, json.dumps(VALUES))) == VALUES


def test_a_byte_order_mark_is_not_text(tmp_path):
    assert load_inputs_file(write(tmp_path, '\ufeff{"a": "é"}')) == {'a': 'é'}


@pytest.mark.parametrize('content, message', [
    ('["a", "b"]', 'must hold a JSON object'),
    ('"text"', 'must hold a JSON object'),
    ('{"a": ', 'cannot read it as UTF-8 JSON'),
    (b'\xff\xfe{}', 'cannot read it as UTF-8 JSON'),
])
def test_a_file_that_is_not_a_json_object_is_refused(tmp_path, content, message):
    with pytest.raises(InputsFileError, match=message):
        load_inputs_file(write(tmp_path, content))


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(InputsFileError, match='cannot read it'):
        load_inputs_file(str(tmp_path / 'absent.json'))


def test_the_file_wins_over_constants():
    constants, _ = parse_constants(["text:'from constants'", 'other:1'])
    rows = merge_literal_inputs(constants, {'text': 'from the file'})
    assert rows == [['text', '', True], ['other', '1', False]]


def test_no_file_leaves_constants_as_they_are():
    constants, _ = parse_constants(['other:1'])
    assert merge_literal_inputs(constants, None) == constants


class FakeActionLog:
    def set_pre_file(self, *args, **kwargs):
        return None


class FakeLogger:
    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return FakeActionLog()


def test_parse_inputs_takes_the_values_without_eval(monkeypatch, tmp_path):
    """The top-level executor's input rows and input state, as load_and_run builds them."""
    monkeypatch.setattr(script_executor_mod, 'script_logger', FakeLogger())
    calls = []
    real_state_eval = script_executor_mod.state_eval
    monkeypatch.setattr(script_executor_mod, 'state_eval',
                        lambda expression, *args, **kwargs: calls.append(expression) or real_state_eval(expression, *args, **kwargs))
    top = ScriptExecutor.__new__(ScriptExecutor)
    top.props = {'script_name': 'Top'}
    top.log_folder = str(tmp_path) + '/'
    top.state = {}
    constants, _ = parse_constants(["looks_like_python:'from constants'", 'other:1 + 1'])
    top.inputs = merge_literal_inputs(constants, VALUES)

    top.parse_inputs(dict(VALUES))

    for name, value in VALUES.items():
        assert top.state[name] == value
    assert top.state['other'] == 2
    # Only the --constants expression was evaluated, and the null value's
    # stand-in 'None'; no file value was.
    assert calls == ['None', '1 + 1']
    inputs_txt = (tmp_path / 'inputs.txt').read_text(encoding='utf-8')
    assert "<class 'str'> looks_like_python: __import__('os').system('x')" in inputs_txt
