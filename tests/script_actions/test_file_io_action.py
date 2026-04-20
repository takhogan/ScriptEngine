from ScriptEngine.common.enums import ScriptExecutionState


def test_file_io_action_read_text(system_executor, base_context, run_queue, tmp_path):
    executor, _, _ = system_executor
    f = tmp_path / "in.txt"
    f.write_text("abc")
    action = {
        "actionName": "fileIOAction",
        "actionData": {
            "targetSystem": "none",
            "fileActionType": "r",
            "fileType": "text",
            "filePath": repr(str(f)),
            "inputExpression": "''",
            "outputVarName": "out",
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"] == "abc"
