from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod


def test_color_compare_action(device_executor, base_context, run_queue, monkeypatch):
    executor, _, _, _ = device_executor
    monkeypatch.setattr(
        sae_mod.DetectObjectHelper,
        "get_detect_area",
        lambda *_: {
            "screencap_im_bgr": "cached",
            "original_image": None,
            "original_height": 20,
            "original_width": 30,
            "fixed_scale": False,
        },
    )
    monkeypatch.setattr(sae_mod.ColorCompareHelper, "handle_color_compare", lambda *_: 0.9)
    action = {
        "actionName": "colorCompareAction",
        "actionData": {"targetSystem": "desktop", "threshold": "0.1"},
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
