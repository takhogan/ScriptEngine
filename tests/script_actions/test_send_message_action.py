from ScriptEngine.common.enums import ScriptExecutionState


def test_send_message_action_when_server_absent(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "sendMessageAction",
        "actionData": {
            "targetSystem": "none",
            "inputExpression": "'hello'",
            "subject": "'subj'",
            "messagingChannelName": "alerts",
        },
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE
