from ScriptEngine.common.enums import ScriptExecutionState


def test_conditional_statement_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "conditionalStatement",
        "actionData": {"condition": "1 == 1", "targetSystem": "none"},
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
