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


# --- SQLite round trips: read rows, insert them back, read again ---------------------------

def _db_rows(path, query):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(query).fetchall()
    finally:
        connection.close()


def test_sqlite_round_trip_read_rows_insert_into_copy_table(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "sqlite", "'r.db'", input_expression=(
        "{'table': 'src', 'values': ["
        "{'name': 'a', 'score': 1, 'ratio': 0.5, 'blob': b'\\x00\\x01', 'note': None},"
        "{'name': 'b', 'score': 2, 'ratio': 1.25, 'blob': b'\\xff', 'note': 'x'}]}"
    )), state, context, run_queue)

    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'r.db'", input_expression="SELECT * FROM src ORDER BY name", output_var_name="rows"),
        state, context, run_queue
    )
    original = state["rows"]
    assert original == [
        {"name": "a", "score": 1, "ratio": 0.5, "blob": b"\x00\x01", "note": None},
        {"name": "b", "score": 2, "ratio": 1.25, "blob": b"\xff", "note": "x"},
    ]

    # The rows a read answers go straight back into an object write.
    _, status, state, _, _, _ = executor.handle_action(
        _action("w", "sqlite", "'r.db'", input_expression="{'table': 'dst', 'values': rows}"),
        state, context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"]["rowcount"] == 2
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'r.db'", input_expression="SELECT * FROM dst ORDER BY name"),
        state, context, run_queue
    )
    assert state["out"] == original
    db = data_root / "scriptAssets" / "Default" / "Scores" / "r.db"
    assert _db_rows(db, "SELECT typeof(score), typeof(ratio), typeof(blob) FROM dst ORDER BY name") == [
        ("integer", "real", "blob"), ("integer", "real", "blob")
    ]


def test_sqlite_round_trip_read_modify_write_back_into_same_table(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "sqlite", "'c.db'",
        input_expression="'CREATE TABLE counter (k TEXT PRIMARY KEY, n INTEGER); INSERT INTO counter VALUES (\"runs\", 1);'"),
        state, context, run_queue)
    for _ in range(3):
        _, _, state, _, _, _ = executor.handle_action(
            _action("r", "sqlite", "'c.db'", input_expression="SELECT n FROM counter WHERE k = 'runs'", output_var_name="rows"),
            state, context, run_queue
        )
        executor.handle_action(_action("w", "sqlite", "'c.db'",
            input_expression="{'query': 'UPDATE counter SET n = ? WHERE k = ?', 'params': [rows[0]['n'] + 1, 'runs']}"),
            state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'c.db'", input_expression="SELECT * FROM counter"), state, context, run_queue
    )
    assert state["out"] == [{"k": "runs", "n": 4}]


def test_sqlite_json_values_come_back_as_text(system_executor, base_context, run_queue, data_root):
    # Dicts and lists are stored as JSON text, and a read answers that text, not the object.
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "sqlite", "'j.db'",
        input_expression="{'table': 't', 'values': {'meta': {'x': [1, 2]}, 'tags': ['a', 'b']}}"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'j.db'", input_expression="SELECT meta, tags FROM t"), state, context, run_queue
    )
    assert state["out"] == [{"meta": '{"x": [1, 2]}', "tags": '["a", "b"]'}]
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'j.db'", input_expression="SELECT json_extract(meta, '$.x[1]') AS x FROM t"), state, context, run_queue
    )
    assert state["out"] == [{"x": 2}]


# --- SQLite: invalid input ------------------------------------------------------------------

@pytest.mark.parametrize("input_expression", [
    "{'table': 't'}",                                  # no values
    "{'table': 't', 'values': 5}",                     # values not a dict or list
    "{'table': 't', 'values': [{'a': 1}, 'b']}",       # a row that is not a dict
    "{'table': 't', 'values': [[1, 2]]}",              # rows as lists
    "{'table': '', 'values': {'a': 1}}",               # empty table name
    "{'table': 3, 'values': {'a': 1}}",                # table name not a string
    "{'table': 't', 'values': {3: 'x'}}",              # column name not a string
    "{'query': 42}",                                   # query not a string
    "42",                                              # neither SQL nor an object
    "['SELECT 1']",
])
def test_sqlite_write_rejects_invalid_objects(system_executor, base_context, run_queue, data_root, input_expression):
    executor, _, _ = system_executor
    with pytest.raises(ValueError):
        executor.handle_action(_action("w", "sqlite", "'bad.db'", input_expression=input_expression), {}, _context(base_context), run_queue)
    db = data_root / "scriptAssets" / "Default" / "Scores" / "bad.db"
    if db.exists():
        assert _db_rows(db, "SELECT name FROM sqlite_master") == []


@pytest.mark.parametrize("input_expression", ["{'table': 't', 'values': {'a': 1}}", "{'query': 42}", "42"])
def test_sqlite_read_rejects_invalid_objects(system_executor, base_context, run_queue, data_root, input_expression):
    executor, _, _ = system_executor
    context = _context(base_context)
    executor.handle_action(_action("w", "sqlite", "'ok.db'", input_expression="'CREATE TABLE t (a INTEGER)'"), {}, context, run_queue)
    with pytest.raises(ValueError):
        executor.handle_action(_action("r", "sqlite", "'ok.db'", input_expression=input_expression), {}, context, run_queue)


def test_sqlite_bad_sql_raises_and_a_read_cannot_write(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    executor.handle_action(_action("w", "sqlite", "'s.db'", input_expression="'CREATE TABLE t (a INTEGER)'"), {}, context, run_queue)
    with pytest.raises(sqlite3.OperationalError):
        executor.handle_action(_action("w", "sqlite", "'s.db'", input_expression="SELEKT nonsense"), {}, context, run_queue)
    with pytest.raises(sqlite3.OperationalError):
        executor.handle_action(_action("r", "sqlite", "'s.db'", input_expression="SELECT b FROM t"), {}, context, run_queue)
    # The database is opened read-only for a read.
    with pytest.raises(sqlite3.OperationalError):
        executor.handle_action(_action("r", "sqlite", "'s.db'", input_expression="INSERT INTO t VALUES (1)"), {}, context, run_queue)
    assert _db_rows(data_root / "scriptAssets" / "Default" / "Scores" / "s.db", "SELECT * FROM t") == []


def test_sqlite_failed_write_rolls_back_every_row(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    db = data_root / "scriptAssets" / "Default" / "Scores" / "u.db"
    executor.handle_action(_action("w", "sqlite", "'u.db'", input_expression="'CREATE TABLE u (k TEXT PRIMARY KEY)'"), {}, context, run_queue)
    with pytest.raises(sqlite3.IntegrityError):
        executor.handle_action(_action("w", "sqlite", "'u.db'",
            input_expression="{'query': 'INSERT INTO u VALUES (?)', 'params': [['a'], ['b'], ['a']]}"), {}, context, run_queue)
    assert _db_rows(db, "SELECT * FROM u") == []
    with pytest.raises(sqlite3.IntegrityError):
        executor.handle_action(_action("w", "sqlite", "'u.db'",
            input_expression="{'table': 'u', 'values': [{'k': 'x'}, {'k': 'x'}]}"), {}, context, run_queue)
    assert _db_rows(db, "SELECT * FROM u") == []


def test_sqlite_odd_names_and_values_are_stored_safely(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "sqlite", "'o.db'", input_expression=(
        "{'table': 'my \"table\"; DROP TABLE x', 'values': {'col \"q\"': \"it's\", 'when': {1, 2} and None, 'obj': object.__name__}}"
    )), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(
        _action("r", "sqlite", "'o.db'", input_expression="'SELECT * FROM \"my \"\"table\"\"; DROP TABLE x\"'"), state, context, run_queue
    )
    assert state["out"] == [{'col "q"': "it's", "when": None, "obj": "object"}]


# --- text, json and image files -------------------------------------------------------------

def test_text_write_append_read_round_trip(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("w", "text", "'log.txt'", input_expression="'line 1\\n'"), state, context, run_queue)
    executor.handle_action(_action("a", "text", "'log.txt'", input_expression="'line 2 é\\n'"), state, context, run_queue)
    _, status, state, _, _, _ = executor.handle_action(_action("r", "text", "'log.txt'"), state, context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert state["out"] == "line 1\nline 2 é\n"
    # A second write replaces the file.
    executor.handle_action(_action("w", "text", "'log.txt'", input_expression="'fresh'"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(_action("r", "text", "'log.txt'"), state, context, run_queue)
    assert state["out"] == "fresh"


def test_text_binary_write_and_read(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {}
    executor.handle_action(_action("wb", "text", "'raw.bin'", input_expression="b'\\x00\\xffab'"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(_action("rb", "text", "'raw.bin'"), state, context, run_queue)
    assert state["out"] == b"\x00\xffab"


def test_json_round_trip_nested_values(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    state = {"value": {"name": "a", "n": 3, "ratio": 0.5, "ok": True, "none": None, "items": [1, {"x": "é"}]}}
    executor.handle_action(_action("w", "json", "'v.json'", input_expression="value"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(_action("r", "json", "'v.json'", output_var_name="back"), state, context, run_queue)
    assert state["back"] == state["value"]
    # A list at the top level works too.
    executor.handle_action(_action("w", "json", "'l.json'", input_expression="[1, 'two', None]"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(_action("r", "json", "'l.json'"), state, context, run_queue)
    assert state["out"] == [1, "two", None]


def test_json_write_of_unserializable_value_raises(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    with pytest.raises(TypeError):
        executor.handle_action(_action("w", "json", "'bad.json'", input_expression="{'s': {1, 2}}"), {}, _context(base_context), run_queue)


def test_json_read_of_malformed_file_raises(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    context = _context(base_context)
    executor.handle_action(_action("w", "text", "'broken.json'", input_expression="'{\"a\": '"), {}, context, run_queue)
    with pytest.raises(ValueError):
        executor.handle_action(_action("r", "json", "'broken.json'"), {}, context, run_queue)


def test_image_write_read_round_trip(system_executor, base_context, run_queue, data_root):
    import numpy as np
    from ScriptEngine.common.types import ScreenPlanImage
    executor, _, _ = system_executor
    context = _context(base_context)
    pixels = np.zeros((6, 9, 3), dtype=np.uint8)
    pixels[1:4, 2:7] = (10, 200, 30)
    state = {"img": {"matched_area": pixels}}
    _, status, state, _, _, _ = executor.handle_action(
        _action("w", "image", "'shots/a.png'", input_expression="img"), state, context, run_queue
    )
    assert status == ScriptExecutionState.SUCCESS
    assert (data_root / "scriptAssets" / "Default" / "Scores" / "shots" / "a.png").exists()

    _, _, state, _, _, _ = executor.handle_action(_action("r", "image", "'shots/a.png'", output_var_name="back"), state, context, run_queue)
    back = state["back"]
    assert isinstance(back, ScreenPlanImage)
    assert (back.height, back.width) == (6, 9)
    assert np.array_equal(back.matched_area, pixels)

    # The image a read answers can be written again (as a detect's output would be).
    executor.handle_action(_action("w", "image", "'shots/b.png'", input_expression="back"), state, context, run_queue)
    _, _, state, _, _, _ = executor.handle_action(_action("r", "image", "'shots/b.png'", output_var_name="again"), state, context, run_queue)
    assert np.array_equal(state["again"].matched_area, pixels)


def test_image_read_of_missing_file_raises(system_executor, base_context, run_queue, data_root):
    executor, _, _ = system_executor
    with pytest.raises(Exception):
        executor.handle_action(_action("r", "image", "'nope.png'"), {}, _context(base_context), run_queue)
