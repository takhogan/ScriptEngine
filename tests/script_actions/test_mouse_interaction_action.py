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


def test_mouse_interaction_double_click_without_delay(device_executor, base_context, run_queue, monkeypatch):
    executor, dc, _, _ = device_executor
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
            "clickCount": 2,
            "betweenClickDelay": False,
            "randomVariableTypeData": {},
            "mouseButton": "left",
        },
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert calls == [(10, 11, "left"), (10, 11, "left")]


def test_mouse_interaction_records_when_it_clicked_and_how_far_it_scrolled(device_executor, base_context, run_queue, monkeypatch):
    executor, dc, _, logger = device_executor
    dc.actions["scroll"] = lambda x, y, distance: None
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
            "mouseActionType": "scroll",
            "scrollDistance": -3,
            "clickCount": 1,
            "betweenClickDelay": False,
            "randomVariableTypeData": {},
            "mouseButton": "left",
        },
    }
    executor.execute_action(action, {}, base_context, run_queue)
    assert logger.action_log.result["scroll_distance"] == -3
    assert logger.action_log.result["input_at"].endswith("Z")


def test_a_mouse_up_without_a_mouse_down_sends_nothing(device_executor, base_context, run_queue, monkeypatch):
    executor, _, _, logger = device_executor
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
            "mouseActionType": "mouseUp",
            "clickCount": 1,
            "betweenClickDelay": False,
            "randomVariableTypeData": {},
            "mouseButton": "left",
        },
    }
    executor.execute_action(action, {}, base_context, run_queue)
    assert logger.action_log.result["input_at"] is None
