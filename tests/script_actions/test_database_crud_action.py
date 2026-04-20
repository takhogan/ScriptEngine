import pytest


def test_database_crud_action_unknown_provider_raises(system_executor, base_context, run_queue):
    executor, _, _ = system_executor
    action = {
        "actionName": "databaseCRUD",
        "actionData": {"targetSystem": "none", "databaseType": "unsupported"},
    }
    with pytest.raises(Exception, match="DB provider unimplemented"):
        executor.handle_action(action, {}, base_context, run_queue)
