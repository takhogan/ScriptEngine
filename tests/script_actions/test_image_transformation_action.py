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


# A single white pixel dilated by a k x k kernel n times grows into a square
# of side (k - 1) * n + 1, so the white area shows which kernel and how many
# iterations the action used.
def _dilate(executor, base_context, run_queue, **fields):
    image = np.zeros((21, 21, 3), dtype=np.uint8)
    image[10, 10] = 255
    state = {"img": {"matched_area": image}}
    action = {
        "actionName": "imageTransformationAction",
        "actionData": {
            "targetSystem": "none",
            "inputExpression": "img",
            "transformationType": "dilate",
            "outputVarName": "out",
            **fields,
        },
    }
    _, status, state, _, _, _ = executor.handle_action(action, state, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    return int(np.count_nonzero(state["out"]["matched_area"][:, :, 0]))


def test_dilate_uses_its_own_kernel_and_iterations(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    # dilate 3x3 twice -> 5x5; the erode values (kernel 1) would leave 1 pixel
    white = _dilate(executor, base_context, run_queue,
                    erodeKernelSize=1, erodeIterations=1,
                    dilateKernelSize=3, dilateIterations=2)
    assert white == 5 * 5


def test_dilate_accepts_numbers_and_strings(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    for kernel, iterations in ((3, 1), ("3", "1"), (3, "1"), ("3", 1)):
        white = _dilate(executor, base_context, run_queue,
                        erodeKernelSize=1, erodeIterations=1,
                        dilateKernelSize=kernel, dilateIterations=iterations)
        assert white == 3 * 3, (kernel, iterations)


def test_dilate_falls_back_to_erode_values_when_unset(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    # erode 3x3 three times -> 7x7, what dilate did before it read its own fields
    for unset in ({}, {"dilateKernelSize": None, "dilateIterations": None},
                  {"dilateKernelSize": "", "dilateIterations": "  "},
                  {"dilateKernelSize": "None", "dilateIterations": "null"}):
        white = _dilate(executor, base_context, run_queue,
                        erodeKernelSize="3", erodeIterations=3, **unset)
        assert white == 7 * 7, unset


def test_dilate_falls_back_per_field(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    # dilate kernel 5 set, iterations unset -> erode's 2 iterations: 9x9
    white = _dilate(executor, base_context, run_queue,
                    erodeKernelSize=3, erodeIterations=2,
                    dilateKernelSize=5, dilateIterations="")
    assert white == 9 * 9
