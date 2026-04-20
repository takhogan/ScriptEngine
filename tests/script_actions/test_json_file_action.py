from ScriptEngine.common.enums import ScriptExecutionState


def test_json_file_action_read(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "jsonFileAction",
        "actionData": {
            "targetSystem": "none",
            "mode": "read",
            "fileName": "missing.json",
            "varName": "j",
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["j"] == {}
