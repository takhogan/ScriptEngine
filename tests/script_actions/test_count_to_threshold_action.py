from ScriptEngine.common.enums import ScriptExecutionState


def test_count_to_threshold_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "countToThresholdAction",
        "actionData": {
            "targetSystem": "none",
            "counterVarName": "c",
            "counterThreshold": "2",
            "incrementBy": "1",
            "thresholdType": "counter",
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status in (ScriptExecutionState.FAILURE, ScriptExecutionState.SUCCESS)
    assert "c" in state
