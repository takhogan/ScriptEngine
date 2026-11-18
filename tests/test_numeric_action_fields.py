"""Fields the action schema types as string|number (postActionDelay,
counterThreshold, the random-variable bounds, scrollDistance, ...).

The editor writes them as strings ("1"), but a script written through the
API may hold the number itself (1). A keyboardAction with
"postActionDelay": 1 used to end its run in ERROR after the action had
succeeded: TypeError: object of type 'int' has no len(), raised in
script_executor.execute_action."""
import datetime
import glob
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from ScriptEngine.common.script_engine_utils import expression_text, eval_number, state_eval
from ScriptEngine.helpers import random_variable_helper as rv_mod
from ScriptEngine.helpers.random_variable_helper import RandomVariableHelper


def test_expression_text_turns_numbers_into_their_text():
    assert expression_text(1) == '1'
    assert expression_text(0) == '0'
    assert expression_text(1.5) == '1.5'
    assert expression_text(' x + 1 ') == 'x + 1'
    assert expression_text('') == ''
    assert expression_text(None) == ''
    assert expression_text(None, default='0') == '0'


def test_eval_number_takes_a_number_or_an_expression():
    assert eval_number(2, {}) == 2.0
    assert eval_number(0.25, {}) == 0.25
    assert eval_number('2', {}) == 2.0
    assert eval_number('x * 2', {'x': 3}) == 6.0
    assert eval_number('', {}) is None
    assert eval_number(None, {}, default=0) == 0


def test_state_eval_returns_a_number_as_is():
    assert state_eval(5, {}, {}) == 5
    assert state_eval(0.5, {}, {}) == 0.5
    assert state_eval('5', {}, {}) == 5


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(rv_mod.time, 'sleep', lambda seconds: calls.append(seconds))
    return calls


@pytest.mark.parametrize('delay, slept', [
    (1, [1.0]),
    ('1', [1.0]),
    (1.5, [1.5]),
    ('wait + 1', [3.0]),
    (0, []),
    ('0', []),
])
def test_post_action_delay_accepts_numbers_and_expressions(sleeps, delay, slept):
    RandomVariableHelper.parse_post_action_delay(delay, {'wait': 2})
    assert sleeps == slept


@pytest.mark.parametrize('low, high', [(2, 3), ('2', '3'), (2.0, '3.0')])
def test_uniform_random_variable_accepts_numbers_and_strings(low, high):
    data = {'distributionType': 'uniform', 'uniformDistMin': low, 'uniformDistMax': high}
    for value in RandomVariableHelper.get_rv_val(data, repeats=20):
        assert 2.0 <= value <= 3.0


@pytest.mark.parametrize('mean, stddev, low, high', [(5, 1, 4, 6), ('5', '1', '4', '6')])
def test_normal_random_variable_accepts_numbers_and_strings(mean, stddev, low, high):
    data = {
        'distributionType': 'normal',
        'normalDistMean': mean, 'normalDistStdDev': stddev,
        'normalDistMin': low, 'normalDistMax': high,
    }
    value = RandomVariableHelper.get_rv_val(data)[0]
    assert 4.0 <= value <= 6.0


# A whole run, the way the failing one went: a child script whose actions
# carry postActionDelay as a number, called from a scriptReference whose own
# postActionDelay is a number too.

SCRIPT_NAME = 'NumericPostActionDelay'

WRAPPER = '''
import ScriptEngine.clients.screenplan_api as api

def fake_init(self):
    self.server_token = 'fake'

def fake_send_request(self, request, *args, **kwargs):
    raise AssertionError('this run sends no request: ' + request.path)

api.ScreenPlanAPI.__init__ = fake_init
api.ScreenPlanAPI.send_request = fake_send_request

from ScriptEngine.script_manager import main
if __name__ == '__main__':
    main()
'''


def assignment(group, var_name, expression, post_action_delay, children=()):
    return {
        'actionName': 'variableAssignment',
        'actionGroup': group,
        'actionLabel': None,
        'rowIndex': 0,
        'actionIndex': group - 1,
        'childGroups': [
            {'srcGroup': group, 'destGroup': child, 'destRowIndex': 0, 'destActionIndex': child - 1, 'type': 'firstMatch'}
            for child in children
        ],
        'actionData': {
            'targetSystem': 'none', 'outputVarName': var_name, 'inputExpression': expression,
            'inputParser': 'eval', 'setIfNull': False, 'postActionDelay': post_action_delay,
        },
    }


def write_script(data_root):
    folder = data_root / 'scripts' / 'scriptLibrary' / 'Default' / SCRIPT_NAME
    folder.mkdir(parents=True)
    actions = [
        assignment(1, 'first', '1', 0, children=[2]),
        assignment(2, 'second', 'first + 1', 0.1),
    ]
    props = {
        'targetSystem': 'none', 'width': None, 'height': None, 'scriptMode': 'train', 'deploymentToLibrary': True,
        'scriptReference': {
            'actionName': 'scriptReference', 'actionGroup': 0, 'childGroups': [], 'parentGroups': [],
            'actionData': {
                'targetSystem': 'none', 'scriptName': SCRIPT_NAME, 'scriptAttributes': [],
                'branchingBehavior': 'firstMatch', 'actionOrder': 'sequential', 'scriptMaxActionAttempts': 50,
                'onOutOfActionAttempts': 'returnFailure', 'runMode': 'run', 'libraryScript': True,
                'postActionDelay': 0,
            },
        },
    }
    (folder / 'actionRows.json').write_text(json.dumps([{'actions': actions}]))
    (folder / 'props.json').write_text(json.dumps(props))
    (folder / 'inputs.json').write_text(json.dumps([]))
    (folder / 'outputs.json').write_text(json.dumps([['second', '', True]]))


def test_a_run_with_numeric_post_action_delays_succeeds(tmp_path):
    data_root = tmp_path / 'data'
    write_script(data_root)
    (data_root / 'tmp').mkdir()
    script_id = str(uuid.uuid4())
    start_time = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    (data_root / 'tmp' / 'running_scripts.json').write_text(json.dumps([{
        'script_id': script_id, 'start_time_str': start_time, 'script_name': SCRIPT_NAME, 'parallel': False,
    }]))
    wrapper = tmp_path / 'run_engine.py'
    wrapper.write_text(WRAPPER)
    env = dict(
        os.environ,
        PYTHONPATH=str(ENGINE_ROOT),
        PYTHONUTF8='1',
        SCREENPLAN_AUTH_HASH_PATH=str(tmp_path / 'no_auth_hash.json'),
        SCREENPLAN_SERVER_CONFIG_PATH=str(tmp_path / 'no_server_config.json'),
        PIKVM_LIB_LOG_FILE=os.devnull,
    )
    env.pop('SCREENPLAN_DATA_ROOT', None)
    completed = subprocess.run(
        [
            sys.executable, str(wrapper),
            '--data-root', str(data_root),
            '--script-name', SCRIPT_NAME,
            '--start-time', start_time,
            '--script-id', script_id,
            '--log-level', 'info',
            '--screen-plan-server-attached',
        ],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, encoding='utf-8', timeout=180,
    )
    folders = glob.glob(str(data_root / 'logs' / ('00000-' + SCRIPT_NAME + '-*')))
    assert len(folders) == 1, (folders, completed.stdout[-3000:], completed.stderr[-3000:])
    folder = Path(folders[0])
    stdout = (folder / 'global-stdout.txt').read_text(encoding='utf-8') if (folder / 'global-stdout.txt').exists() else ''

    assert 'TypeError' not in stdout, stdout[-3000:]
    assert completed.returncode == 0, completed.stderr[-3000:]
    root_log = json.loads((folder / '00001-scriptReference-0-action-log.json').read_text(encoding='utf-8'))
    assert root_log['status'] == 'SUCCESS', stdout[-3000:]
    assert json.loads((folder / 'outputs.json').read_text(encoding='utf-8'))['outputs']['second']['value'] == 2
