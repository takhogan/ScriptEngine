from ScriptEngine.common.enums import ScriptExecutionState


def test_interact_application_action(device_executor, base_context, run_queue):
    executor, dc, _, _ = device_executor
    calls = []
    dc.actions["start_application"] = lambda app, args: calls.append((app, args))
    action = {
        "actionName": "interactApplicationAction",
        "actionData": {
            "targetSystem": "desktop",
            "actionType": "start",
            "applicationName": "app.name",
            "actionPayload": "--demo 1",
        },
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert calls == [("app.name", ["--demo", "1"])]
