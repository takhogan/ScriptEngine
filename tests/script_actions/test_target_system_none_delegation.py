from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod
import ScriptEngine.system_script_action_executor as ssae_mod


def test_target_system_none_delegation(device_executor, base_context, run_queue, monkeypatch):
    executor, _, _, _ = device_executor
    monkeypatch.setattr(
        ssae_mod.SystemScriptActionExecutor,
        "handle_action",
        lambda self, action, state, context, queue: (
            action,
            ScriptExecutionState.SUCCESS,
            state,
            context,
            queue,
            [],
        ),
    )
    action = {"actionName": "shellScript", "actionData": {"targetSystem": "none", "shellScript": "echo hi"}}
    _, status, _, _, _, _ = executor.execute_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
