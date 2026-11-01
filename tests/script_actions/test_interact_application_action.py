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


def test_interact_application_records_the_application(device_executor, base_context, run_queue):
    executor, dc, _, logger = device_executor
    dc.actions["stop_application"] = lambda app: None
    action = {
        "actionName": "interactApplicationAction",
        "actionData": {"targetSystem": "adb", "actionType": "stop", "applicationName": " com.example.app "},
    }
    executor.execute_action(action, {}, base_context, run_queue)
    result = logger.action_log.result
    assert result["application_action"] == "stop"
    assert result["application"] == "com.example.app"
    assert result["payload"] is None
    assert result["succeeded"] is True
    assert result["input_at"].endswith("Z")
