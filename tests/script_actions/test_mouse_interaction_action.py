from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod


def test_mouse_interaction_click(device_executor, base_context, run_queue, monkeypatch):
    executor, dc, _, logger = device_executor
    calls = []
    dc.actions["click"] = lambda x, y, btn: calls.append((x, y, btn))
    monkeypatch.setattr(
        sae_mod.ClickActionHelper,
        "get_point_choice",
        lambda *args, **kwargs: ((10, 11), (10, 11), [(10, 11)], [(10, 11)]),
    )
    action = {
        "actionName": "mouseInteractionAction",
        "actionData": {
            "targetSystem": "desktop",
            "sourceDetectTypeData": {"inputExpression": ""},
            "sourcePointList": [],
            "mouseActionType": "click",
            "clickCount": 1,
            "betweenClickDelay": False,
            "randomVariableTypeData": {},
            "mouseButton": "left",
        },
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert calls == [(10, 11, "left")]
    assert logger.action_log.summary == "performed click at location (10, 11)"
