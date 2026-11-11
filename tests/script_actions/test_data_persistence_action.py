import os
import sqlite3

import pytest

from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.common.constants.script_engine_constants as constants_mod


@pytest.fixture
def data_root(monkeypatch, tmp_path):
    root = tmp_path / "data-root"
    root.mkdir()
    monkeypatch.setattr(constants_mod, "DATA_ROOT", str(root))
    return root


def _action(file_action_type, file_type, file_path, input_expression="''", output_var_name="out", action_name="dataPersistenceAction"):
    return {
        "actionName": action_name,
        "actionData": {
            "targetSystem": "none",
            "fileActionType": file_action_type,
            "fileType": file_type,
            "filePath": file_path,
            "inputExpression": input_expression,
            "outputVarName": output_var_name,
        },
    }


def _context(base_context, script_name="Scores", workspace="Default"):
    return {**base_context, "script_name": script_name, "workspace": workspace}


def test_read_text_absolute_path(system_executor, base_context, run_queue, tmp_path):
    executor, _, _ = system_executor
    f = tmp_path / "in.txt"
    f.write_text("abc")
    _, status, state, _, _, _ = executor.handle_action(
        _action("r", "text", repr(str(f))), {}, base_context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"] == "abc"


def test_legacy_file_io_action_name_still_runs(system_executor, base_context, run_queue, tmp_path):
    executor, _, _ = system_executor
    f = tmp_path / "in.txt"
    f.write_text("abc")
    _, status, state, _, _, _ = executor.handle_action(
        _action("r", "text", repr(str(f)), action_name="fileIOAction"), {}, base_context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"] == "abc"


def test_relative_write_goes_to_script_assets(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context, script_name="Child", workspace="Workspace1")
    _, status, state, _, _, _ = executor.handle_action(
        _action("w", "json", "'exports/today.json'", input_expression="{'a': 1}"), {}, context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    written = data_root / "scriptAssets" / "Workspace1" / "Child" / "exports" / "today.json"
    assert written.read_text() == '{"a": 1}'

    _, status, state, _, _, _ = executor.handle_action(
        _action("r", "json", "'exports/today.json'"), {}, context, run_queue
    )
    assert state["out"] == {"a": 1}


def test_relative_path_without_context_uses_props_script_name(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    executor.props["script_name"] = "TopScript"
    executor.handle_action(_action("w", "text", "'note.txt'", input_expression="'hi'"), {}, base_context, run_queue)
    assert (data_root / "scriptAssets" / "Default" / "TopScript" / "note.txt").read_text() == "hi"


def test_sqlite_object_write_creates_table_then_query_read(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {"score": 42}
    _, status, state, _, _, _ = executor.handle_action(
        _action("w", "sqlite", "'scores.db'",
                input_expression="{'table': 'scores', 'values': [{'name': 'a', 'score': score}, {'name': 'b', 'score': 7, 'meta': {'x': 1}}]}"),
        state, context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"]["rowcount"] == 2
    assert os.path.exists(data_root / "scriptAssets" / "Default" / "Scores" / "scores.db")

    # Plain SQL that is not a Python expression is used as written.
    _, status, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'scores.db'", input_expression="SELECT name, score, meta FROM scores ORDER BY name"),
        state, context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"] == [
        {"name": "a", "score": 42, "meta": None},
        {"name": "b", "score": 7, "meta": '{"x": 1}'},
    ]


def test_sqlite_query_writes_and_parameterized_read(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(
        _action("w", "sqlite", "'kv.db'",
                input_expression="'CREATE TABLE kv (k TEXT PRIMARY KEY, v INTEGER); INSERT INTO kv VALUES (\"a\", 1);'"),
        state, context, run_queue
    )
    _, _, state, _, _, _ = executor.handle_action(
        _action("w", "sqlite", "'kv.db'",
                input_expression="{'query': 'INSERT INTO kv VALUES (?, ?)', 'params': [['b', 2], ['c', 3]]}"),
        state, context, run_queue
    )
    assert state["out"]["rowcount"] == 2
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'kv.db'",
                input_expression="{'query': 'SELECT v FROM kv WHERE k = :k', 'params': {'k': 'c'}}"),
        state, context, run_queue
    )
    assert state["out"] == [{"v": 3}]


def test_sqlite_object_write_adds_missing_column(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "sqlite", "'t.db'", input_expression="{'table': 't', 'values': {'a': 1}}"), state, context, run_queue)
    executor.handle_action(_action("w", "sqlite", "'t.db'", input_expression="{'table': 't', 'values': {'a': 2, 'b': 'x'}}"), state, context, run_queue)
    rows = sqlite3.connect(data_root / "scriptAssets" / "Default" / "Scores" / "t.db").execute("SELECT a, b FROM t ORDER BY a").fetchall()
    assert rows == [(1, None), (2, "x")]


def test_sqlite_read_of_missing_database_does_not_create_it(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    with pytest.raises(FileNotFoundError):
        executor.handle_action(_action("r", "sqlite", "'missing.db'", input_expression="'SELECT 1'"), {}, _context(base_context), run_queue)
    assert not os.path.exists(data_root / "scriptAssets" / "Default" / "Scores" / "missing.db")


def test_sqlite_rejects_unknown_object(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    with pytest.raises(ValueError):
        executor.handle_action(_action("w", "sqlite", "'t.db'", input_expression="{'rows': []}"), {}, _context(base_context), run_queue)
