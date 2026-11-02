"""outputs.json beside outputs.txt: each output's value when JSON takes it,
else its repr, and never a secret's value (agent-toolkits plan §7, item 2)."""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ScriptEngine.script_executor as script_executor_mod
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.run_outputs import describe_output, outputs_document, write_outputs_json
from ScriptEngine.helpers.user_secrets_helper import SecureSecret
from ScriptEngine.script_executor import ScriptExecutor

REDACTED = '***** REDACTED SECRET *****'


class Unserializable:
    def __repr__(self):
        return '<Unserializable>'


def test_a_bool_a_string_and_a_list_are_json():
    assert describe_output(True) == {'type': 'json', 'value': True}
    assert describe_output('C:\\a:b\r\n') == {'type': 'json', 'value': 'C:\\a:b\r\n'}
    assert describe_output([1, 'two', None, {'k': 2.5}]) == {'type': 'json', 'value': [1, 'two', None, {'k': 2.5}]}


def test_an_object_that_does_not_serialize_is_its_repr():
    assert describe_output(Unserializable()) == {'type': 'repr', 'value': '<Unserializable>'}
    assert describe_output({(1, 2): 'tuple key'}) == {'type': 'repr', 'value': "{(1, 2): 'tuple key'}"}


def test_nan_is_a_repr_since_json_has_no_spelling_for_it():
    assert describe_output(math.nan) == {'type': 'repr', 'value': 'nan'}


def test_a_secret_is_never_its_value():
    assert describe_output(SecureSecret('hunter2')) == {'type': 'repr', 'value': REDACTED}
    in_list = describe_output(['user', SecureSecret('hunter2')])
    in_dict = describe_output({'password': SecureSecret('hunter2')})
    assert in_list == {'type': 'repr', 'value': "['user', " + REDACTED + "]"}
    assert in_dict == {'type': 'repr', 'value': "{'password': " + REDACTED + "}"}
    assert 'hunter2' not in json.dumps(outputs_document({'a': in_list, 'b': in_dict}))


def test_write_outputs_json(tmp_path):
    path = str(tmp_path / 'outputs.json')
    write_outputs_json(path, {'ok': True, 'thing': Unserializable()})
    assert json.loads(Path(path).read_text()) == {
        'version': 1,
        'outputs': {'ok': {'type': 'json', 'value': True}, 'thing': {'type': 'repr', 'value': '<Unserializable>'}},
    }
    assert os.listdir(tmp_path) == ['outputs.json']


class FakeActionLog:
    def set_post_file(self, *args, **kwargs):
        return None


class FakeLogger:
    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return FakeActionLog()


def child_script(monkeypatch, outputs, state):
    monkeypatch.setattr(script_executor_mod, 'script_logger', FakeLogger())
    child = ScriptExecutor.__new__(ScriptExecutor)
    child.props = {'script_name': 'Child'}
    child.outputs = outputs
    child.state = state
    child.status = ScriptExecutionState.FINISHED
    return child


def test_parse_outputs_writes_outputs_json_beside_outputs_txt(monkeypatch, tmp_path):
    child = child_script(monkeypatch, [
        ['flag', '', True],
        ['text', '', True],
        ['items', '[1, 2]', False],
        ['thing', '', True],
        ['password', '', True],
    ], {'flag': False, 'text': 'line\r\n', 'thing': Unserializable(), 'password': SecureSecret('hunter2')})
    parent_state = {}

    child.parse_outputs(parent_state, str(tmp_path) + '/outputs.txt')

    assert parent_state['items'] == [1, 2]
    document = json.loads((tmp_path / 'outputs.json').read_text())
    assert document == {'version': 1, 'outputs': {
        'flag': {'type': 'json', 'value': False},
        'text': {'type': 'json', 'value': 'line\r\n'},
        'items': {'type': 'json', 'value': [1, 2]},
        'thing': {'type': 'repr', 'value': '<Unserializable>'},
        'password': {'type': 'repr', 'value': REDACTED},
    }}
    assert 'hunter2' not in (tmp_path / 'outputs.json').read_text()
    assert (tmp_path / 'outputs.txt').exists()
