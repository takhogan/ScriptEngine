import datetime

import pytest
from dateutil import tz

from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.helpers.user_prompt_helper as user_prompt_helper_mod
from ScriptEngine.helpers.user_prompt_helper import UserPromptHelper
from tests.script_actions.conftest import FakeLogger


class FakeControllerAPI:
    """Answers the helper's requests from a script of poll results.

    `polls` is consumed one per GET: a dict is the prompt's state as the
    controller reports it, None is a request that failed, and 'lost' is the
    controller not knowing the id (it restarted)."""

    def __init__(self, polls, create_result='ok'):
        self.polls = list(polls)
        self.create_result = create_result
        self.requests = []
        self.created = 0

    def send_request(self, request, retry=True):
        self.requests.append(request)
        if request.method == 'POST' and request.path == 'user-prompts':
            if self.create_result is None:
                return None
            self.created += 1
            return {'prompt': {'id': 'p{}'.format(self.created), 'status': 'pending'}}
        if request.method == 'POST' and request.path.endswith('/cancel'):
            return {'prompt': {'status': 'cancelled'}}
        poll = self.polls.pop(0) if self.polls else {'status': 'pending'}
        if poll is None:
            return None
        if poll == 'lost':
            return {'prompt': None}
        return {'prompt': poll}

    def paths(self, method):
        return [r.path for r in self.requests if r.method == method]


class FakeClock:
    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


@pytest.fixture
def logger(monkeypatch):
    logger = FakeLogger()
    monkeypatch.setattr(user_prompt_helper_mod, 'script_logger', logger)
    monkeypatch.setattr(user_prompt_helper_mod, 'is_script_cancelled', lambda script_id: False)
    return logger


def make_action(**action_data):
    data = {
        'targetSystem': 'none',
        'promptMethod': 'web',
        'promptMessage': "'Enter the code'",
        'promptType': 'text',
        'defaultValue': '',
        'timeoutSeconds': '600',
        'outputVarName': 'userResponse',
    }
    data.update(action_data)
    return {'actionName': 'userPromptAction', 'actionGroup': 7, 'actionData': data}


def make_state():
    return {'SCRIPT_CONTEXT': {
        'script_id': 'script-1',
        'base_script_name': 'BaseScript',
        'timeout': datetime.datetime.now().astimezone(tz=tz.tzutc()) + datetime.timedelta(hours=1),
    }}


def run(api, action, state=None, clock=None):
    helper = UserPromptHelper(api_client=api, clock=clock or FakeClock(0.01), sleep=lambda seconds: None)
    return helper.handle_action(action, state if state is not None else make_state(), 'ChildScript')


def test_user_prompt_action_server_absent(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = make_action()
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE


def test_text_answer_is_stored(logger):
    api = FakeControllerAPI([
        {'status': 'pending'},
        {'status': 'answered', 'response': {'accepted': True, 'value': '123456', 'answeredAt': '2026-10-31T12:00:01.000Z'}},
    ])
    state = make_state()
    state['total'] = 42
    status, state = run(api, make_action(promptMessage="f'Is {total} right?'"), state)
    assert status == ScriptExecutionState.SUCCESS
    assert state['userResponse'] == '123456'
    created = api.requests[0].payload
    assert created['message'] == 'Is 42 right?'
    assert 'details' not in created
    assert created['promptMethod'] == 'web'
    assert created['scriptId'] == 'script-1'
    assert created['scriptName'] == 'ChildScript'
    assert created['baseScriptName'] == 'BaseScript'
    assert created['actionGroup'] == 7
    assert created['timeoutSeconds'] == 600
    assert all(path.startswith('user-prompts/p1?waitMs=') for path in api.paths('GET'))
    assert logger.action_log.summary == "answered '123456'"


def test_text_cancel_fails_with_none(logger):
    api = FakeControllerAPI([{'status': 'answered', 'response': {'accepted': False, 'value': None}}])
    status, state = run(api, make_action())
    assert status == ScriptExecutionState.FAILURE
    assert state['userResponse'] is None


@pytest.mark.parametrize('prompt_type,accepted,expected_status', [
    ('yesno', True, ScriptExecutionState.SUCCESS),
    ('yesno', False, ScriptExecutionState.FAILURE),
    ('okcancel', True, ScriptExecutionState.SUCCESS),
    ('okcancel', False, ScriptExecutionState.FAILURE),
])
def test_choice_answers_are_booleans(logger, prompt_type, accepted, expected_status):
    api = FakeControllerAPI([{'status': 'answered', 'response': {'accepted': accepted}}])
    status, state = run(api, make_action(promptType=prompt_type))
    assert status == expected_status
    assert state['userResponse'] is accepted


def test_timeout_uses_the_default_value(logger):
    api = FakeControllerAPI([])
    status, state = run(api, make_action(defaultValue='fallback', timeoutSeconds='5'), clock=FakeClock(2))
    assert status == ScriptExecutionState.SUCCESS
    assert state['userResponse'] == 'fallback'
    assert api.paths('POST')[-1] == 'user-prompts/p1/cancel'


def test_timeout_default_answers_a_choice(logger):
    api = FakeControllerAPI([])
    status, state = run(api, make_action(promptType='yesno', defaultValue='No', timeoutSeconds='5'), clock=FakeClock(2))
    assert status == ScriptExecutionState.FAILURE
    assert state['userResponse'] is False


def test_timeout_without_default_fails(logger):
    api = FakeControllerAPI([])
    status, state = run(api, make_action(timeoutSeconds='2 * 2'), clock=FakeClock(2))
    assert status == ScriptExecutionState.FAILURE
    assert state['userResponse'] is None
    assert api.requests[0].payload['timeoutSeconds'] == 4


def test_controller_expiry_uses_the_default_value(logger):
    api = FakeControllerAPI([{'status': 'expired'}])
    status, state = run(api, make_action(defaultValue='fallback'))
    assert status == ScriptExecutionState.SUCCESS
    assert state['userResponse'] == 'fallback'


def test_cancelled_run_cancels_the_prompt(logger, monkeypatch):
    monkeypatch.setattr(user_prompt_helper_mod, 'is_script_cancelled', lambda script_id: script_id == 'script-1')
    api = FakeControllerAPI([])
    status, state = run(api, make_action(defaultValue='fallback'))
    assert status == ScriptExecutionState.FAILURE
    assert state['userResponse'] is None
    assert api.paths('POST') == ['user-prompts', 'user-prompts/p1/cancel']


def test_run_timeout_ends_the_wait(logger):
    api = FakeControllerAPI([])
    state = make_state()
    state['SCRIPT_CONTEXT']['timeout'] = datetime.datetime.now().astimezone(tz=tz.tzutc()) - datetime.timedelta(seconds=1)
    status, state = run(api, make_action(), state)
    assert status == ScriptExecutionState.FAILURE
    assert api.paths('GET') == []


def test_a_lost_prompt_is_asked_again_and_failed_polls_retry(logger):
    api = FakeControllerAPI([
        None,
        'lost',
        {'status': 'answered', 'response': {'accepted': True, 'value': 'again'}},
    ])
    status, state = run(api, make_action())
    assert status == ScriptExecutionState.SUCCESS
    assert state['userResponse'] == 'again'
    assert api.created == 2
    assert api.paths('GET')[-1].startswith('user-prompts/p2?')


def test_controller_refusing_the_prompt_fails(logger):
    api = FakeControllerAPI([], create_result=None)
    status, state = run(api, make_action())
    assert status == ScriptExecutionState.FAILURE
    assert api.paths('GET') == []


def test_an_empty_message_is_sent_empty(logger):
    api = FakeControllerAPI([{'status': 'answered', 'response': {'accepted': True, 'value': 'x'}}])
    run(api, make_action(promptMessage=''))
    assert api.requests[0].payload['message'] == ''


def test_unknown_prompt_method_fails(logger):
    api = FakeControllerAPI([])
    status, _ = run(api, make_action(promptMethod='carrier-pigeon'))
    assert status == ScriptExecutionState.FAILURE
    assert api.requests == []
