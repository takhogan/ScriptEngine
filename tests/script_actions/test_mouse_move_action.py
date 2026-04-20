from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod


def test_mouse_move_drag(device_executor, base_context, run_queue, monkeypatch):
    executor, dc, _, logger = device_executor
    dc.actions["click_and_drag"] = lambda *args, **kwargs: ([0, 1], [0, 1])
    monkeypatch.setattr(
        sae_mod.ClickActionHelper,
        "get_point_choice",
        lambda *args, **kwargs: ((5, 6), (5, 6), [(5, 6)], [(5, 6)]),
    )
    action = {
        "actionName": "mouseMoveAction",
        "actionData": {
            "targetSystem": "desktop",
            "sourceDetectTypeData": {"inputExpression": ""},
            "sourcePointList": [],
            "targetDetectTypeData": {"inputExpression": ""},
            "targetPointList": [],
            "dragMouse": True,
            "releaseMouseOnCompletion": True,
        },
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert logger.action_log.summary == "moved mouse from (5, 6) to (5, 6)"
