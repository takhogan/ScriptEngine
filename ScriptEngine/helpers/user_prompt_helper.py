import datetime
import time

from dateutil import tz

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.script_engine_utils import state_eval, is_script_cancelled
script_logger = ScriptLogger()

DEFAULT_TIMEOUT_SECONDS = 600
# Each poll asks the controller to hold the request this long for an answer.
# Between polls the helper checks for a cancelled run and the deadlines, so
# this bounds how late it notices either.
POLL_WAIT_MS = 5000
# A poll the controller did not answer (it is restarting, say) is retried
# after this long.
POLL_RETRY_SECONDS = 2

# How a default value answers a Yes/No or OK/Cancel prompt.
AFFIRMATIVE_DEFAULTS = {'yes', 'y', 'ok', 'true', '1'}
NEGATIVE_DEFAULTS = {'no', 'n', 'cancel', 'false', '0'}


class UserPromptHelper:
    """Runs a userPromptAction: hands the question to the controller, which
    shows it to the user (promptMethod 'web': a popup on screenplan.io), and
    waits for the answer.

    The controller keeps the prompt (POST /api/user-prompts) and answers each
    poll (GET /api/user-prompts/{id}) when the prompt is answered, or after
    POLL_WAIT_MS with it still pending. Polls double as the engine's
    heartbeat: the controller drops a prompt nobody has polled for a while,
    so a run that was killed does not leave a popup behind.

    Returns (status, state). Yes/OK and a submitted text are SUCCESS; No,
    Cancel, no answer by the timeout (with no default value) and a cancelled
    run are FAILURE.
    """

    def __init__(self, api_client=None, clock=time.monotonic, sleep=time.sleep):
        self.api_client = api_client if api_client is not None else ScreenPlanAPI()
        self.clock = clock
        self.sleep = sleep

    def handle_action(self, action, state, script_name):
        action_data = action['actionData']
        prompt_method = action_data.get('promptMethod') or 'web'
        prompt_type = action_data.get('promptType') or 'text'
        output_var_name = (action_data.get('outputVarName') or '').strip()
        default_value = action_data.get('defaultValue') or ''
        message = action_data.get('promptMessage') or ''
        details_expression = (action_data.get('inputExpression') or '').strip()
        details = str(state_eval(details_expression, {}, state)) if details_expression else ''
        timeout_seconds = self._timeout_seconds(action_data, state)
        script_context = state.get('SCRIPT_CONTEXT', {})
        script_id = script_context.get('script_id')
        run_timeout = script_context.get('timeout')

        log_lines = [
            'prompt method: {}'.format(prompt_method),
            'prompt type: {}'.format(prompt_type),
            'message: {}'.format(message),
        ]
        if details:
            log_lines.append('details: {}'.format(details))
        log_lines.append('timeout: {}s'.format(timeout_seconds))

        if prompt_method != 'web':
            return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines,
                                'unknown prompt method {}'.format(prompt_method))

        prompt_payload = {
            'promptMethod': prompt_method,
            'promptType': prompt_type,
            'message': message,
            'details': details,
            'defaultValue': default_value,
            'timeoutSeconds': timeout_seconds,
            'scriptName': script_name,
            'baseScriptName': script_context.get('base_script_name'),
            'scriptId': script_id,
            'actionGroup': action.get('actionGroup'),
        }
        prompt = self._create_prompt(prompt_payload)
        if prompt is None:
            return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines,
                                'the controller did not take the prompt')
        script_logger.log('user prompt {} waiting for an answer: {}'.format(prompt['id'], message))

        deadline = self.clock() + timeout_seconds
        while True:
            if script_id is not None and is_script_cancelled(script_id):
                self._cancel_prompt(prompt['id'])
                return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines,
                                    'run cancelled before an answer')
            if run_timeout is not None and datetime.datetime.now().astimezone(tz=tz.tzutc()) > run_timeout:
                self._cancel_prompt(prompt['id'])
                return self._answer_with_default(state, output_var_name, prompt_type, default_value, log_lines,
                                                 'no answer before the run timed out')
            remaining = deadline - self.clock()
            if remaining <= 0:
                self._cancel_prompt(prompt['id'])
                return self._answer_with_default(state, output_var_name, prompt_type, default_value, log_lines,
                                                 'no answer in {}s'.format(timeout_seconds))

            wait_ms = int(min(POLL_WAIT_MS, remaining * 1000))
            response = self.api_client.send_request(ScreenPlanAPIRequest(
                request_id=None,
                method='GET',
                request_type='json',
                path='user-prompts/{}?waitMs={}'.format(prompt['id'], wait_ms),
                payload={}
            ))
            if response is None:
                self.sleep(POLL_RETRY_SECONDS)
                continue
            polled = response.get('prompt')
            if polled is None:
                # The controller restarted and lost it: ask again, keeping
                # this action's deadline.
                prompt_payload['timeoutSeconds'] = max(1, int(deadline - self.clock()))
                recreated = self._create_prompt(prompt_payload)
                if recreated is None:
                    self.sleep(POLL_RETRY_SECONDS)
                else:
                    prompt = recreated
                continue

            prompt_status = polled.get('status')
            if prompt_status == 'answered':
                answer = polled.get('response') or {}
                return self._answer(state, output_var_name, prompt_type, answer, log_lines)
            if prompt_status == 'expired':
                return self._answer_with_default(state, output_var_name, prompt_type, default_value, log_lines,
                                                 'no answer in {}s'.format(timeout_seconds))
            if prompt_status == 'cancelled':
                return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines,
                                    'prompt cancelled by the controller')

    def _timeout_seconds(self, action_data, state):
        timeout_expression = str(action_data.get('timeoutSeconds') or '').strip()
        if not timeout_expression:
            return DEFAULT_TIMEOUT_SECONDS
        return max(1, int(float(state_eval(timeout_expression, {}, state))))

    def _create_prompt(self, payload):
        response = self.api_client.send_request(ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='json',
            path='user-prompts',
            payload=payload
        ))
        if response is None:
            return None
        return response.get('prompt')

    def _cancel_prompt(self, prompt_id):
        self.api_client.send_request(ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='json',
            path='user-prompts/{}/cancel'.format(prompt_id),
            payload={}
        ))

    def _answer(self, state, output_var_name, prompt_type, answer, log_lines):
        accepted = bool(answer.get('accepted'))
        answered_at = answer.get('answeredAt') or ''
        if prompt_type == 'text':
            value = answer.get('value') if accepted else None
            if value is not None:
                value = str(value)
            outcome = 'answered {!r}'.format(value) if accepted else 'cancelled by the user'
        else:
            value = accepted
            outcome = 'answered {}'.format(_choice_label(prompt_type, accepted))
        if answered_at:
            log_lines = log_lines + ['answered at: ' + answered_at]
        status = ScriptExecutionState.SUCCESS if accepted else ScriptExecutionState.FAILURE
        return self._finish(state, output_var_name, value, status, log_lines, outcome)

    def _answer_with_default(self, state, output_var_name, prompt_type, default_value, log_lines, reason):
        if default_value == '':
            return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines, reason)
        if prompt_type == 'text':
            return self._finish(state, output_var_name, default_value, ScriptExecutionState.SUCCESS, log_lines,
                                '{}, used the default {!r}'.format(reason, default_value))
        normalized = default_value.strip().lower()
        if normalized in AFFIRMATIVE_DEFAULTS or normalized in NEGATIVE_DEFAULTS:
            accepted = normalized in AFFIRMATIVE_DEFAULTS
            status = ScriptExecutionState.SUCCESS if accepted else ScriptExecutionState.FAILURE
            return self._finish(state, output_var_name, accepted, status, log_lines,
                                '{}, used the default {}'.format(reason, _choice_label(prompt_type, accepted)))
        return self._finish(state, output_var_name, None, ScriptExecutionState.FAILURE, log_lines,
                            '{}; the default {!r} is not a {} answer'.format(reason, default_value, prompt_type))

    def _finish(self, state, output_var_name, value, status, log_lines, outcome):
        if output_var_name:
            state[output_var_name] = value
        script_logger.log('user prompt: ' + outcome)
        script_logger.get_action_log().add_post_file(
            'text',
            'user-prompt.txt',
            '\n'.join(log_lines + ['outcome: ' + outcome])
        )
        summary = outcome if len(outcome) <= 60 else outcome[:57] + '...'
        script_logger.get_action_log().set_summary(summary)
        return status, state


def _choice_label(prompt_type, accepted):
    if prompt_type == 'okcancel':
        return 'OK' if accepted else 'Cancel'
    return 'Yes' if accepted else 'No'
