from ScriptEngine.common.enums import ScriptExecutionState


def test_variable_assignment_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "variableAssignment",
        "actionData": {
            "targetSystem": "none",
            "outputVarName": "x",
            "setIfNull": False,
            "inputExpression": "2 + 2",
            "inputParser": "eval",
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["x"] == 4
