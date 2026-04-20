import datetime

from ScriptEngine.common.enums import ScriptExecutionState


def test_system_time_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "timeAction",
        "actionData": {"targetSystem": "none", "timezone": "utc", "outputVarName": "t"},
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert isinstance(state["t"], datetime.datetime)
