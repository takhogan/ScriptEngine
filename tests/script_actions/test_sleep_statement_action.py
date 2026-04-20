from ScriptEngine.common.enums import ScriptExecutionState


def test_sleep_statement_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "sleepStatement",
        "actionData": {"targetSystem": "none", "inputExpression": "0"},
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
