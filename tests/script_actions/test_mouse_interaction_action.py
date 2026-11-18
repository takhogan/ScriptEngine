import pytest

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


def test_mouse_interaction_scrolls_a_string_distance_as_a_number(device_executor, base_context, run_queue, monkeypatch):
    # scrollDistance is string|number in the action schema; the device's
    # scroll takes a whole number of wheel notches either way.
    executor, dc, _, _ = device_executor
    scrolled = []
    dc.actions["scroll"] = lambda x, y, distance: scrolled.append(distance)
    monkeypatch.setattr(
        sae_mod.ClickActionHelper,
        "get_point_choice",
        lambda *args, **kwargs: ((10, 11), (10, 11), [(10, 11)], [(10, 11)]),
    )
    for distance in ("-3", -3, "notches * 2"):
        action = {
            "actionName": "mouseInteractionAction",
            "actionData": {
                "targetSystem": "desktop",
                "sourceDetectTypeData": {"inputExpression": ""},
                "sourcePointList": [],
                "mouseActionType": "scroll",
                "scrollDistance": distance,
                "clickCount": 1,
                "betweenClickDelay": False,
                "randomVariableTypeData": {},
                "mouseButton": "left",
            },
        }
        executor.execute_action(action, {"notches": 2}, base_context, run_queue)
    assert scrolled == [-3, -3, 4]


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


def test_a_click_macos_denies_input_to_ends_the_run_with_the_reason(device_executor, base_context, run_queue, monkeypatch):
    """The desktop driver raises HostInputDeniedError (helpers/host_input.py):
    the action says why and the error ends the run, instead of a SUCCESS for a
    click macOS dropped."""
    from ScriptEngine.helpers.host_input import HostInputDeniedError

    executor, dc, _, logger = device_executor

    def denied(*args):
        raise HostInputDeniedError()
    dc.actions["click"] = denied
    monkeypatch.setattr(
        sae_mod.ClickActionHelper,
        "get_point_choice",
        lambda *args, **kwargs: ((10, 11), (10, 11), [(10, 11)], [(10, 11)]),
    )
    action = {
        "actionName": "mouseInteractionAction",
        "actionGroup": 3,
        "actionData": {
            "targetSystem": "python",
            "sourceDetectTypeData": {"inputExpression": ""},
            "sourcePointList": [],
            "mouseActionType": "click",
            "clickCount": 1,
            "betweenClickDelay": False,
            "randomVariableTypeData": {},
            "mouseButton": "left",
        },
    }
    with pytest.raises(HostInputDeniedError, match='macOS denied Accessibility'):
        executor.execute_action(action, {}, base_context, run_queue)
    assert logger.action_log.summary.startswith('input refused: macOS denied Accessibility')
    assert logger.action_log.status == 'ERROR'
