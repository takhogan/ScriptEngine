import numpy as np

from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod


def test_detect_object_action_lazy_and_eager(device_executor, base_context, run_queue, monkeypatch):
    executor, dc, _, _ = device_executor
    action = {"actionName": "detectObject", "actionData": {"targetSystem": "desktop"}}
    monkeypatch.setattr(
        sae_mod.DetectObjectHelper,
        "get_detect_area",
        lambda *_: {
            "screencap_im_bgr": np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8),
            "original_image": None,
            "original_height": 20,
            "original_width": 30,
            "fixed_scale": False,
        },
    )
    monkeypatch.setattr(sae_mod.DetectObjectHelper, "handle_detect_object", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        sae_mod.DetectObjectHelper,
        "handle_detect_action_result",
        lambda *_: (action, ScriptExecutionState.SUCCESS, {}, base_context, run_queue),
    )
    dc.actions["screenshot"] = lambda: np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)

    fn, args = executor.execute_action(action, {}, base_context, run_queue, lazy_eval=True)
    assert callable(fn)
    assert args[0]["actionName"] == "detectObject"

    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue, lazy_eval=False)
    assert status == ScriptExecutionState.SUCCESS
