from ScriptEngine.common.enums import ScriptExecutionState


def test_code_block_action(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "codeBlock",
        "actionData": {"targetSystem": "none", "codeBlock": "result = 123"},
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["result"] == 123


def test_code_block_action_async(system_executor, base_context, run_queue):
    executor, io, _ = system_executor
    action = {
        "actionName": "codeBlock",
        "actionData": {"targetSystem": "none", "codeBlock": "result = 123", "async": True},
    }
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    # Async code blocks are dispatched to the IO thread pool; execution does not
    # block, so the body has not run yet and the result is absent.
    assert status == ScriptExecutionState.SUCCESS
    assert "result" not in state
    assert len(io.calls) == 1
    # Running the submitted task executes the body and mutates the shared state.
    submitted_fn, _ = io.calls[0]
    submitted_fn()
    assert state["result"] == 123
