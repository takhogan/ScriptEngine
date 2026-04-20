from ScriptEngine.common.enums import ScriptExecutionState


def test_user_secret_management_action_server_absent(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {"actionName": "userSecretManagementAction", "actionData": {"targetSystem": "none"}}
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE
