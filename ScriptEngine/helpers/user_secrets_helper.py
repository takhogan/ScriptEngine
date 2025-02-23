from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.script_engine_utils import state_eval
script_logger = ScriptLogger()

class SecureSecret:
    def __init__(self, value):
        self._value = value
    
    def __str__(self):
        return "***** REDACTED SECRET *****"
    
    def __repr__(self):
        return "***** REDACTED SECRET *****"
    
    def get_value(self):
        return self._value

class UserSecretsHelper:
    def __init__(self):
        self.api = ScreenPlanAPI()

    def handle_action(self, action, state):
        if action["actionData"]["userSecretActionType"] == "getSecret":
            request = ScreenPlanAPIRequest(
                request_id=None,
                method='GET',
                request_type='getUserSecret',
                path=f'script-studio/getUserSecret/{action["actionData"]["secretName"]}',
                payload={}
            )
            
            api_client = ScreenPlanAPI()
            success = api_client.send_request(request)
            
            if success:
                state[action["actionData"]["outputVarName"]] = SecureSecret(request.response.get('secret'))
                script_logger.get_action_log().add_post_file(
                    'text',
                    'getUserSecret-log.txt',
                    f'Successfully retrieved secret {action["actionData"]["secretName"]}'
                )
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.get_action_log().add_post_file(
                    'text', 
                    'getUserSecret-error.txt',
                    f'Failed to retrieve secret {action["actionData"]["secretName"]}'
                )
                status = ScriptExecutionState.FAILURE

        elif action["actionData"]["userSecretActionType"] == "updateSecret":
            request = ScreenPlanAPIRequest(
                request_id=None,
                method='POST',
                request_type='updateUserSecret',
                path='script-studio/updateUserSecret',
                payload={
                    'secretName': action["actionData"]["secretName"],
                    'secretValue': state_eval(action["actionData"]["inputExpression"], {}, state).get_value() if isinstance(state_eval(action["actionData"]["inputExpression"], {}, state), SecureSecret) else state_eval(action["actionData"]["inputExpression"], {}, state)
                }
            )
            
            api_client = ScreenPlanAPI()
            success = api_client.send_request(request)
            
            if success:
                script_logger.get_action_log().add_post_file(
                    'text',
                    'updateUserSecret-log.txt', 
                    f'Successfully updated secret {action["actionData"]["secretName"]}'
                )
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.get_action_log().add_post_file(
                    'text',
                    'updateUserSecret-error.txt',
                    f'Failed to update secret {action["actionData"]["secretName"]}'
                )
                status = ScriptExecutionState.FAILURE
        return state, status

