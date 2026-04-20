from ScriptEngine.common.enums import ScriptExecutionState


def test_context_switch_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "contextSwitchAction",
        "actionData": {
            "targetSystem": "none",
            "state": {"a": 1},
            "context": {"b": 2, "script_counter": 99, "script_timer": 42},
            "update_dict": {"state": {"x": 3}, "context": {"y": 4}},
        },
    }
    _, status, state, context, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["x"] == 3
    assert context["y"] == 4
