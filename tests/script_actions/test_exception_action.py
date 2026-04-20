from ScriptEngine.common.enums import ScriptExecutionState


def test_exception_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "exceptionAction",
        "actionData": {
            "targetSystem": "none",
            "exceptionMessage": "boom",
            "takeScreenshot": False,
            "exitProgram": False,
        },
        "actionGroup": "g1",
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.FINISHED_FAILURE
