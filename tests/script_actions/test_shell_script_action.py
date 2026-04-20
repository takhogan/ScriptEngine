from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.helpers.shell_script_helper import ShellScriptHelper


def test_shell_script_action(system_executor, empty_state, base_context, run_queue, monkeypatch):
    executor, _, _ = system_executor
    monkeypatch.setattr(
        ShellScriptHelper,
        "run_shell_script",
        staticmethod(lambda action, state: {"done": True}),
    )
    action = {"actionName": "shellScript", "actionData": {"targetSystem": "none"}}
    _, status, state, _, _, _ = executor.handle_action(action, empty_state, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["done"] is True
