from ScriptEngine.common.enums import ScriptExecutionState


def test_for_loop_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "forLoopAction",
        "actionData": {
            "targetSystem": "none",
            "inVariables": "vals",
            "forVariables": "item",
        },
        "childGroups": [],
    }
    _, status, state, _, run_queue, _ = executor.handle_action(action, {"vals": [1, 2]}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["item"] == 1
    assert len(run_queue) == 1
