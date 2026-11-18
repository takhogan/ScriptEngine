from ScriptEngine.common.enums import ScriptExecutionState


def _action(action_type, **data):
    return {
        "actionName": "interactDeviceAction",
        "actionData": {"targetSystem": "phone0", "actionType": action_type, **data},
    }


def test_start_application(device_executor, base_context, run_queue):
    executor, dc, _, _ = device_executor
    calls = []
    dc.actions["start_application"] = lambda app, args: calls.append((app, args))
    action = _action("startApplication", targetSystem="desktop", applicationName="app.name", actionPayload="--demo 1")
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert calls == [("app.name", ["--demo", "1"])]


def test_stop_application_records_the_application(device_executor, base_context, run_queue):
    executor, dc, _, logger = device_executor
    dc.actions["stop_application"] = lambda app: None
    executor.execute_action(_action("stopApplication", applicationName=" com.example.app "), {}, base_context, run_queue)
    result = logger.action_log.result
    assert result["application_action"] == "stopApplication"
    assert result["application"] == "com.example.app"
    assert result["payload"] is None
    assert result["succeeded"] is True
    assert result["input_at"].endswith("Z")


def test_start_and_stop_device_ignore_the_application(device_executor, base_context, run_queue):
    executor, dc, _, logger = device_executor
    calls = []
    dc.actions["start_device"] = lambda: calls.append("start")
    dc.actions["stop_device"] = lambda: calls.append("stop")
    for action_type in ("startDevice", "stopDevice"):
        action = _action(action_type, applicationName="com.example.app", actionPayload="x")
        _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
        assert status == ScriptExecutionState.SUCCESS
        result = logger.action_log.result
        assert result["application_action"] == action_type
        assert result["application"] is None
        assert result["payload"] is None
        assert result["succeeded"] is True
    assert calls == ["start", "stop"]


def test_a_device_that_cannot_start_itself_fails_the_action(device_executor, base_context, run_queue):
    executor, dc, _, logger = device_executor

    def not_implemented():
        raise NotImplementedError("start_device not implemented for DesktopDeviceManager")

    dc.actions["start_device"] = not_implemented
    _, status, _, _, _, _ = executor.execute_action(_action("startDevice", targetSystem="host"), {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE
    assert logger.action_log.result["succeeded"] is False


def test_the_v23_name_and_action_types_still_run(device_executor, base_context, run_queue):
    executor, dc, _, logger = device_executor
    calls = []
    dc.actions["start_application"] = lambda app, args: calls.append(("start", app, args))
    dc.actions["stop_application"] = lambda app: calls.append(("stop", app))
    for action_type in ("start", "stop"):
        action = {
            "actionName": "interactApplicationAction",
            "actionData": {"targetSystem": "adb", "actionType": action_type, "applicationName": "com.example.app"},
        }
        _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
        assert status == ScriptExecutionState.SUCCESS
    assert logger.action_log.result["application_action"] == "stopApplication"
    assert calls == [("start", "com.example.app", None), ("stop", "com.example.app")]
