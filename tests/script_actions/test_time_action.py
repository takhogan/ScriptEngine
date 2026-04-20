import datetime

from ScriptEngine.common.enums import ScriptExecutionState


def test_time_action(device_executor, base_context, run_queue):
    executor, _, _, _ = device_executor
    action = {
        "actionName": "timeAction",
        "actionData": {"targetSystem": "desktop", "timezone": "local", "outputVarName": "t"},
    }
    _, status, state, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert isinstance(state["t"], datetime.datetime)
