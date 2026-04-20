from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod


def test_keyboard_action(device_executor, base_context, run_queue, monkeypatch):
    executor, _, _, _ = device_executor
    monkeypatch.setattr(
        sae_mod.DeviceActionInterpreter,
        "parse_keyboard_action",
        lambda *_: (ScriptExecutionState.SUCCESS, {"x": 1}, {"y": 2}),
    )
    action = {"actionName": "keyboardAction", "actionData": {"targetSystem": "desktop"}}
    _, status, state, context, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["x"] == 1
    assert context["y"] == 2
