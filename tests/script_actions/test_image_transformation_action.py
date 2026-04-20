import numpy as np

from ScriptEngine.common.enums import ScriptExecutionState


def test_image_transformation_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    image = np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)
    state = {"img": {"matched_area": image}}
    action = {
        "actionName": "imageTransformationAction",
        "actionData": {
            "targetSystem": "none",
            "inputExpression": "img",
            "transformationType": "resize",
            "resizeScaleFactor": "1",
            "outputVarName": "img2",
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert "img2" in state
