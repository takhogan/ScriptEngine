"""The run-time secret gate (agent-toolkits plan §7 item 3, §9): with
--approved-secrets, a getSecret for a secret not on the list sends nothing and
stops the run for approval; without the flag, every secret is read as before.
test_agent_tool_run.py runs it through script_manager end to end."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ScriptEngine.helpers.user_secrets_helper as helper_mod
import ScriptEngine.script_executor as script_executor_mod
from ScriptEngine.common import secret_gate
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.secret_gate import SecretApprovalRequired
from ScriptEngine.helpers.user_secrets_helper import SecureSecret, UserSecretsHelper
from ScriptEngine.script_executor import ScriptExecutor


class FakeAPI:
    def __init__(self):
        self.requests = []

    def send_request(self, request):
        self.requests.append(request.path)
        return {'secret': 'hunter2'}


class FakeActionLog:
    def __init__(self):
        self.statuses = []
        self.summary = None
        self.files = {}

    def set_status(self, status):
        self.statuses.append(status)

    def set_summary(self, summary):
        self.summary = summary

    def add_post_file(self, file_type, name, text):
        self.files[name] = text


class FakeLogger:
    def __init__(self):
        self.action_log = FakeActionLog()

    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return self.action_log


@pytest.fixture
def helper(monkeypatch):
    logger = FakeLogger()
    monkeypatch.setattr(helper_mod, 'script_logger', logger)
    monkeypatch.setattr(helper_mod, 'ScreenPlanAPI', FakeAPI)
    secrets_helper = UserSecretsHelper()
    secrets_helper.logger = logger
    yield secrets_helper
    secret_gate.configure(None)


def get_secret(name='vdi_password'):
    return {
        'actionName': 'userSecretManagementAction',
        'actionGroup': 7,
        'actionData': {'userSecretActionType': 'getSecret', 'secretName': name, 'outputVarName': 'password',
                       'targetSystem': 'none'},
    }


def test_without_the_flag_every_secret_is_read(helper):
    secret_gate.configure(None)
    status, state = helper.handle_action(get_secret(), {})
    assert status == ScriptExecutionState.SUCCESS
    assert isinstance(state['password'], SecureSecret) and state['password'].get_value() == 'hunter2'
    assert helper.api_client.requests == ['getUserSecret/vdi_password']


def test_an_approved_secret_is_read(helper):
    secret_gate.configure(['other', 'vdi_password'])
    status, state = helper.handle_action(get_secret(), {})
    assert status == ScriptExecutionState.SUCCESS
    assert state['password'].get_value() == 'hunter2'
    assert helper.api_client.requests == ['getUserSecret/vdi_password']


@pytest.mark.parametrize('approved', [[], ['other']])
def test_an_unapproved_secret_sends_nothing_and_stops_for_approval(helper, approved):
    secret_gate.configure(approved)
    state = {}
    with pytest.raises(SecretApprovalRequired) as raised:
        helper.handle_action(get_secret(), state)
    assert helper.api_client.requests == []
    assert state == {}
    assert raised.value.secret == 'vdi_password'
    assert raised.value.action == 'userSecretManagementAction-7'
    assert helper.logger.action_log.statuses == ['NEEDS_APPROVAL']
    assert helper.logger.action_log.summary == 'needs approval: secret vdi_password'


def test_updating_a_secret_is_not_gated(helper):
    secret_gate.configure([])
    action = get_secret()
    action['actionData'].update(userSecretActionType='updateSecret', inputExpression='"new"')
    status, _ = helper.handle_action(action, {})
    assert status == ScriptExecutionState.SUCCESS
    assert helper.api_client.requests == ['updateUserSecret']


def test_the_executor_running_the_action_names_its_script(monkeypatch):
    class Raising:
        def execute_action(self, *args, **kwargs):
            raise SecretApprovalRequired('vdi_password', 'userSecretManagementAction-7')

    monkeypatch.setattr(script_executor_mod, 'script_logger', FakeLogger())
    executor = ScriptExecutor.__new__(ScriptExecutor)
    executor.props = {'script_name': 'VDI_SignIn'}
    executor.script_action_executor = Raising()
    executor.state, executor.context, executor.run_queue = {}, {}, []
    with pytest.raises(SecretApprovalRequired) as raised:
        executor.handle_action({'actionName': 'userSecretManagementAction', 'actionData': {'targetSystem': 'none'}})
    assert raised.value.to_dict() == {
        'status': 'NEEDS_APPROVAL',
        'secret': 'vdi_password',
        'script': 'VDI_SignIn',
        'action': 'userSecretManagementAction-7',
    }


def test_needs_approval_is_a_run_status():
    assert ScriptExecutionState.NEEDS_APPROVAL.name == secret_gate.NEEDS_APPROVAL == 'NEEDS_APPROVAL'
