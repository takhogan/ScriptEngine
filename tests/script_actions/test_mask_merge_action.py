import numpy as np
import pytest

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.types import ScreenPlanImage


def _make_match(point, size, original_shape=(200, 300, 3), score=0.9):
    h, w = size
    mask = np.full((h, w), 255, dtype=np.uint8)
    matched_area = np.full((h, w, 3), 255, dtype=np.uint8)
    oh, ow = original_shape[0], original_shape[1]
    original_image = np.full(original_shape, 50, dtype=np.uint8)
    return ScreenPlanImage(
        input_type='shape',
        point=(float(point[0]), float(point[1])),
        output_mask=mask,
        matched_area=matched_area,
        height=h,
        width=w,
        original_image=original_image,
        original_height=oh,
        original_width=ow,
        score=score,
        n_matches=1,
        detect_object_result=True,
    )


def _base_action(**overrides):
    action_data = {
        "leftInputExpression": "left",
        "rightInputExpression": "right",
        "joinLeftAt": "center",
        "joinRightAt": "center",
        "includeLeftMatch": False,
        "includeRightMatch": False,
        "joinTogetherAs": "rectangle",
        "outputVarName": "merged",
        "targetSystem": "none",
    }
    action_data.update(overrides)
    return {"actionName": "matchMergeAction", "actionData": action_data}


def test_match_merge_rectangle_between_centers(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    state = {
        "left": _make_match((10, 10), (20, 20)),    # center (20, 20)
        "right": _make_match((100, 60), (40, 40)),  # center (120, 80)
    }
    action = _base_action(joinTogetherAs="rectangle")

    _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)

    assert status == ScriptExecutionState.SUCCESS
    merged = state["merged"]
    assert isinstance(merged, ScreenPlanImage)
    # Rectangle spans the two centers (20,20)->(120,80).
    assert merged.point == (20.0, 20.0)
    assert merged.width == 100
    assert merged.height == 60
    assert merged.output_mask.max() == 255


def test_match_merge_includes_matches_in_bbox(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    state = {
        "left": _make_match((10, 10), (20, 20)),
        "right": _make_match((100, 60), (40, 40)),
    }
    action = _base_action(includeLeftMatch=True, includeRightMatch=True)

    _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)

    assert status == ScriptExecutionState.SUCCESS
    merged = state["merged"]
    # Union of both full boxes: (10,10) -> (140,100).
    assert merged.point == (10.0, 10.0)
    assert merged.width == 130
    assert merged.height == 90


def test_match_merge_segment(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    state = {
        "left": _make_match((10, 10), (40, 40)),
        "right": _make_match((100, 10), (40, 40)),
    }
    action = _base_action(joinTogetherAs="segment", joinLeftAt="right", joinRightAt="left")

    _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)

    assert status == ScriptExecutionState.SUCCESS
    merged = state["merged"]
    assert isinstance(merged, ScreenPlanImage)
    assert merged.output_mask.max() == 255


def test_match_merge_invalid_input_raises(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    state = {"left": {"not": "a match"}, "right": _make_match((0, 0), (10, 10))}
    action = _base_action()
    with pytest.raises(ValueError):
        executor.handle_action(action, state, base_context, run_queue)
