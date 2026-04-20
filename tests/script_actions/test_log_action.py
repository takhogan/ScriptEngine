import numpy as np

from ScriptEngine.common.enums import ScriptExecutionState


def test_log_action(device_executor, base_context, run_queue):
    executor, dc, _, _ = device_executor
    dc.actions["screenshot"] = lambda: np.random.randint(0, 255, (30, 40, 3), dtype=np.uint8)
    action = {
        "actionName": "logAction",
        "actionData": {"targetSystem": "desktop", "logType": "logImage"},
    }
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
