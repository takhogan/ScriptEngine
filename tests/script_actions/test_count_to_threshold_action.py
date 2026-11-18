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


def test_count_to_threshold_takes_numeric_fields(system_executor, base_context, run_queue):
    # string|number in the action schema: a script written through the API
    # may hold the numbers themselves.
    executor, _, _ = system_executor
    action = {
        "actionName": "countToThresholdAction",
        "actionData": {
            "targetSystem": "none",
            "counterVarName": "c",
            "counterThreshold": 2,
            "incrementBy": 1,
            "initialValue": 0,
            "thresholdType": "counter",
        },
    }
    state = {}
    statuses = []
    for _ in range(3):
        _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)
        statuses.append(status)
    assert statuses == [ScriptExecutionState.FAILURE, ScriptExecutionState.FAILURE, ScriptExecutionState.SUCCESS]
    assert state["c"] == 2


def test_count_to_threshold_timer_takes_numeric_seconds(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "countToThresholdAction",
        "actionData": {
            "targetSystem": "none",
            "counterVarName": "t",
            "counterThreshold": 0,
            "incrementBy": 1,
            "thresholdType": "timer",
            "counterThresholdSeconds": 0,
        },
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
