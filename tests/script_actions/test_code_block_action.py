from ScriptEngine.common.enums import ScriptExecutionState


def test_code_block_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "codeBlock",
        "actionData": {"targetSystem": "none", "codeBlock": "result = 123"},
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["result"] == 123
