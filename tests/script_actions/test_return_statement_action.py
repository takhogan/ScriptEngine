from ScriptEngine.common.enums import ScriptExecutionState


def test_return_statement_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "returnStatement",
        "actionData": {
            "targetSystem": "none",
            "returnStatementType": "exitScript",
            "returnStatus": "success",
        },
    }
    _, status, _, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.FINISHED
