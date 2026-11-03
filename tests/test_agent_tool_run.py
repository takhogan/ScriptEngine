"""A run the way the controller starts one for an agent tool call (agent-toolkits
plan §7, §12): script_manager with --inputs-file and --approved-secrets, a
data root of its own, and ScreenPlanAPI replaced so nothing reaches the
network or reads a controller's token. Checks what the controller reads back:
the exit code, stderr, {runFolder}/outputs.json, needs_approval.json and the
root action log's status."""
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
SCRIPT_NAME = 'AgentToolTest'
SECRET_VALUE = 'hunter2-do-not-leak'

# Started in place of script_manager: replaces ScreenPlanAPI, records each
# request it is sent to FAKE_API_RECORD, then runs script_manager.main().
WRAPPER = '''
import json, os, sys
import ScriptEngine.clients.screenplan_api as api

def fake_init(self):
    self.server_token = 'fake'

def fake_send_request(self, request, *args, **kwargs):
    with open(os.environ['FAKE_API_RECORD'], 'a') as record:
        record.write(json.dumps({'path': request.path}) + '\\n')
    return {'secret': os.environ['FAKE_SECRET_VALUE']}

api.ScreenPlanAPI.__init__ = fake_init
api.ScreenPlanAPI.send_request = fake_send_request

from ScriptEngine.script_manager import main
if __name__ == '__main__':
    main()
'''


def action(group, name, action_data, children=()):
    return {
        'actionName': name,
        'actionGroup': group,
        'actionLabel': None,
        'rowIndex': 0,
        'actionIndex': group - 1,
        'childGroups': [
            {'srcGroup': group, 'destGroup': child, 'destRowIndex': 0, 'destActionIndex': child - 1, 'type': 'firstMatch'}
            for child in children
        ],
        'actionData': dict(action_data, targetSystem='none', postActionDelay=''),
    }


def assignment(group, var_name, expression, children=()):
    return action(group, 'variableAssignment', {
        'outputVarName': var_name, 'inputExpression': expression, 'inputParser': 'eval', 'setIfNull': False,
    }, children)


def write_script(data_root):
    folder = data_root / 'scripts' / 'scriptLibrary' / 'Default' / SCRIPT_NAME
    folder.mkdir(parents=True)
    actions = [
        assignment(1, 'echoed', 'text', children=[2]),
        action(2, 'userSecretManagementAction', {
            'userSecretActionType': 'getSecret', 'secretName': 'vdi_password', 'outputVarName': 'password',
        }, children=[3]),
        assignment(3, 'after_secret', '"read"'),
    ]
    props = {
        'targetSystem': 'none', 'width': None, 'height': None, 'scriptMode': 'train', 'deploymentToLibrary': True,
        'scriptReference': {
            'actionName': 'scriptReference', 'actionGroup': 0, 'childGroups': [], 'parentGroups': [],
            'actionData': {
                'targetSystem': 'none', 'scriptName': SCRIPT_NAME, 'scriptAttributes': [],
                'branchingBehavior': 'firstMatch', 'actionOrder': 'sequential', 'scriptMaxActionAttempts': '50',
                'onOutOfActionAttempts': 'returnFailure', 'runMode': 'run', 'libraryScript': True,
                'postActionDelay': '0',
            },
        },
    }
    inputs = [['text', '"default text"', True]]
    outputs = [
        ['echoed', '', True],
        ['password', '', True],
        ['after_secret', '', True],
        ['ok', 'True', False],
        ['items', '[1, "two", None]', False],
    ]
    (folder / 'actionRows.json').write_text(json.dumps([{'actions': actions}]))
    (folder / 'props.json').write_text(json.dumps(props))
    (folder / 'inputs.json').write_text(json.dumps(inputs))
    (folder / 'outputs.json').write_text(json.dumps(outputs))


class Run:
    def __init__(self, completed, data_root, api_record):
        self.returncode = completed.returncode
        self.stderr = completed.stderr
        self.stdout = completed.stdout
        folders = glob.glob(str(data_root / 'logs' / ('00000-' + SCRIPT_NAME + '-*')))
        assert len(folders) == 1, (folders, completed.stdout[-3000:], completed.stderr[-3000:])
        self.folder = Path(folders[0])
        self.requests = [json.loads(line) for line in api_record.read_text().splitlines()] if api_record.exists() else []

    def json(self, relative):
        return json.loads((self.folder / relative).read_text(encoding='utf-8'))

    def root_status(self):
        return self.json('00001-scriptReference-0-action-log.json')['status']

    def node_status(self, name):
        paths = glob.glob(str(self.folder / '**' / ('*-' + name + '-action-log.json')), recursive=True)
        assert len(paths) == 1, paths
        return json.loads(Path(paths[0]).read_text())['status']

    def outputs(self):
        document = self.json('outputs.json')
        assert document['version'] == 1
        return document['outputs']


@pytest.fixture
def run_engine(tmp_path):
    def run(*args, inputs=None):
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
        api_record = tmp_path / 'api_requests.jsonl'
        command = [
            sys.executable, str(wrapper),
            '--data-root', str(data_root),
            '--script-name', SCRIPT_NAME,
            '--start-time', start_time,
            '--script-id', script_id,
            '--log-level', 'info',
            '--screen-plan-server-attached',
        ]
        if inputs is not None:
            inputs_path = tmp_path / 'inputs.json'
            inputs_path.write_text(inputs, encoding='utf-8') if isinstance(inputs, str) else \
                inputs_path.write_text(json.dumps(inputs), encoding='utf-8')
            command += ['--inputs-file', str(inputs_path)]
        command += list(args)
        env = dict(
            os.environ,
            PYTHONPATH=str(ENGINE_ROOT),
            PYTHONUTF8='1',
            FAKE_API_RECORD=str(api_record),
            FAKE_SECRET_VALUE=SECRET_VALUE,
            # Nothing here may find a real controller's token or port.
            SCREENPLAN_AUTH_HASH_PATH=str(tmp_path / 'no_auth_hash.json'),
            SCREENPLAN_SERVER_CONFIG_PATH=str(tmp_path / 'no_server_config.json'),
            PIKVM_LIB_LOG_FILE=os.devnull,
        )
        env.pop('SCREENPLAN_DATA_ROOT', None)
        completed = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True, text=True,
                                   encoding='utf-8', timeout=180)
        return Run(completed, data_root, api_record)
    return run


def test_unapproved_secret_stops_the_run_for_approval_and_reads_nothing(run_engine):
    run = run_engine('--approved-secrets', inputs={'text': 'hi'})

    assert run.returncode == 3, run.stdout[-3000:]
    assert run.stderr == ''
    assert run.requests == []
    assert not (run.folder / 'errors.txt').exists()
    assert run.json('needs_approval.json') == {
        'status': 'NEEDS_APPROVAL',
        'secret': 'vdi_password',
        'script': SCRIPT_NAME,
        'action': 'userSecretManagementAction-2',
    }
    assert run.root_status() == 'NEEDS_APPROVAL'
    assert run.node_status('userSecretManagementAction-2') == 'NEEDS_APPROVAL'
    # The child never returned its outputs, so the top level holds only what
    # it had: none of the script's output names.
    assert run.outputs() == {}


def test_an_approved_secret_is_read(run_engine):
    run = run_engine('--approved-secrets', 'other', 'vdi_password', inputs={'text': 'hi'})

    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stderr == ''
    assert run.requests == [{'path': 'getUserSecret/vdi_password'}]
    assert not (run.folder / 'needs_approval.json').exists()
    assert run.root_status() == 'SUCCESS'
    outputs = run.outputs()
    assert outputs['echoed'] == {'type': 'json', 'value': 'hi'}
    assert outputs['after_secret'] == {'type': 'json', 'value': 'read'}
    assert outputs['ok'] == {'type': 'json', 'value': True}
    assert outputs['items'] == {'type': 'json', 'value': [1, 'two', None]}
    # The secret is an output here, and still never written as its value.
    assert outputs['password'] == {'type': 'repr', 'value': '***** REDACTED SECRET *****'}
    for path in run.folder.rglob('outputs.json'):
        assert SECRET_VALUE not in path.read_text()


def test_without_the_flag_there_is_no_gate(run_engine):
    run = run_engine(inputs={'text': 'hi'})

    assert run.returncode == 0, run.stderr[-3000:]
    assert run.requests == [{'path': 'getUserSecret/vdi_password'}]
    assert run.root_status() == 'SUCCESS'
    assert run.outputs()['after_secret'] == {'type': 'json', 'value': 'read'}


def test_the_child_script_writes_outputs_json_beside_outputs_txt(run_engine):
    run = run_engine()

    child_outputs = glob.glob(str(run.folder / '*' / 'outputs.txt'))
    assert len(child_outputs) == 1
    document = json.loads((Path(child_outputs[0]).parent / 'outputs.json').read_text())
    assert document['outputs']['echoed'] == {'type': 'json', 'value': 'default text'}
    assert document['outputs']['password']['type'] == 'repr'


@pytest.mark.parametrize('value', [
    'C:\\Users\\x\\a:b.txt',
    'line one\r\nline two\r\n\r\nlast line',
    'x' * 100 * 1024,
    "__import__('os').system('x')",
])
def test_inputs_file_values_arrive_as_they_are(run_engine, value):
    run = run_engine('--approved-secrets', 'vdi_password', inputs={'text': value})

    assert run.returncode == 0, run.stderr[-3000:]
    assert run.outputs()['echoed'] == {'type': 'json', 'value': value}


def test_inputs_file_wins_over_constants(run_engine):
    run = run_engine('--approved-secrets', 'vdi_password', '--constants', "text:'from constants'",
                     inputs={'text': 'from the file'})

    assert run.returncode == 0, run.stderr[-3000:]
    assert run.outputs()['echoed'] == {'type': 'json', 'value': 'from the file'}


def test_inputs_file_that_is_not_an_object_fails_at_start(run_engine):
    run = run_engine(inputs='["text", "hi"]')

    assert run.returncode == 1
    assert 'must hold a JSON object' in run.stderr
    assert run.requests == []
    assert not (run.folder / '00001-scriptReference-0-action-log.json').exists()
    assert run.outputs() == {}
