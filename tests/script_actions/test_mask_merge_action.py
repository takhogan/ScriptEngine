import pytest


def test_mask_merge_action_not_implemented_asserts(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {"actionName": "maskMergeAction", "actionData": {"targetSystem": "none"}}
    with pytest.raises(AssertionError):
        executor.handle_action(action, {}, base_context, run_queue)
