from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.system_script_action_executor as ssae_mod


def test_random_variable_action(system_executor, base_context, run_queue, monkeypatch):
    executor, _, _ = system_executor
    monkeypatch.setattr(ssae_mod.RandomVariableHelper, "get_rv_val", lambda *_: [7])
    action = {
        "actionName": "randomVariable",
        "actionData": {"targetSystem": "none", "outputVarName": "rv"},
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["rv"] == 7
