"""dataPersistenceAction: where its files live, and its SQLite reads and writes.

A relative filePath resolves under the script's assets folder,
`scriptAssets/{workspace}/{scriptName}/` in the controller's data root, so a
script finds the files it wrote on any later run, whatever folder the engine
was started from. The folder belongs to the script that holds the action, not
the script that called it: a subscript reads and writes the same files
whichever script runs it.

SQLite: inputExpression evaluates to
  - a SQL string: the query to run (reads and writes);
  - {"query": str, "params": list | dict}: a parameterized query, and for a
    write, params given as a list of rows (lists or dicts) runs once per row;
  - {"table": str, "values": dict | list[dict]} (writes only): inserts the rows,
    creating the table from their keys if it is missing and adding any column
    it lacks. Dict and list values are stored as JSON text.
A read answers its rows as a list of dicts; a write answers
{"rowcount": int, "lastrowid": int | None}.
"""
import json
import os
import sqlite3
from pathlib import Path

from ScriptEngine.common.constants.script_engine_constants import data_path

WRITE_ACTION_TYPES = ('w', 'wb', 'a')
SCRIPT_ASSETS_FOLDER_NAME = 'scriptAssets'


def script_assets_dir(workspace, script_name):
    """scriptAssets/{workspace}/{scriptName}/ in the data root (not created here)."""
    return os.path.abspath(data_path(SCRIPT_ASSETS_FOLDER_NAME, workspace or 'Default', script_name))


def resolve_data_path(file_path, workspace, script_name, for_write):
    """An absolute path is used as given. A relative one resolves under the
    script's assets folder, which is created here; for a write, so is the
    file's own parent folder below it (`exports/today.json`)."""
    file_path = os.path.expanduser(str(file_path))
    if os.path.isabs(file_path):
        return file_path
    assets_dir = script_assets_dir(workspace, script_name)
    os.makedirs(assets_dir, exist_ok=True)
    resolved = os.path.normpath(os.path.join(assets_dir, file_path))
    if for_write:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
    return resolved


def _quote_identifier(name):
    if not isinstance(name, str) or len(name) == 0:
        raise ValueError('sqlite: a table or column name must be a non-empty string, got {!r}'.format(name))
    return '"' + name.replace('"', '""') + '"'


def _column_type(value):
    if isinstance(value, bool) or isinstance(value, int):
        return 'INTEGER'
    if isinstance(value, float):
        return 'REAL'
    if isinstance(value, (bytes, bytearray, memoryview)):
        return 'BLOB'
    return 'TEXT'


def _to_sqlite_value(value):
    if value is None or isinstance(value, (str, int, float, bytes, bytearray, memoryview)):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    # numpy scalars and the like
    if hasattr(value, 'item'):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def _query_and_params(query_value):
    if isinstance(query_value, str):
        return query_value, None
    if isinstance(query_value, dict) and 'query' in query_value:
        query = query_value['query']
        if not isinstance(query, str):
            raise ValueError('sqlite: "query" must be a string, got {}'.format(type(query).__name__))
        return query, query_value.get('params')
    raise ValueError(
        'sqlite: inputExpression must evaluate to a SQL string or {"query": ..., "params": ...}'
        ' (writes also take {"table": ..., "values": ...}), got ' + type(query_value).__name__
    )


def _is_many(params):
    return isinstance(params, (list, tuple)) and len(params) > 0 and \
        all(isinstance(row, (list, tuple, dict)) for row in params)


def sqlite_read(db_path, query_value):
    """Runs a query against an existing database and answers its rows as dicts."""
    if not os.path.exists(db_path):
        raise FileNotFoundError('sqlite: no database at ' + db_path)
    query, params = _query_and_params(query_value)
    # Read-only, so a read never creates or changes the file.
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(query, params) if params is not None else connection.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def _insert_rows(connection, table, values):
    rows = [values] if isinstance(values, dict) else values
    if not isinstance(rows, (list, tuple)) or not all(isinstance(row, dict) for row in rows):
        raise ValueError('sqlite: "values" must be a dict or a list of dicts')
    if len(rows) == 0:
        return {'rowcount': 0, 'lastrowid': None}
    columns = []
    column_types = {}
    for row in rows:
        for key, value in row.items():
            if key not in column_types:
                columns.append(key)
                column_types[key] = _column_type(value) if value is not None else None
            elif column_types[key] is None and value is not None:
                column_types[key] = _column_type(value)

    quoted_table = _quote_identifier(table)
    column_defs = ', '.join(
        _quote_identifier(column) + ' ' + (column_types[column] or 'TEXT') for column in columns
    )
    connection.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(quoted_table, column_defs))
    existing = {row[1] for row in connection.execute('PRAGMA table_info({})'.format(quoted_table))}
    for column in columns:
        if column not in existing:
            connection.execute('ALTER TABLE {} ADD COLUMN {} {}'.format(
                quoted_table, _quote_identifier(column), column_types[column] or 'TEXT'
            ))

    rowcount = 0
    lastrowid = None
    for row in rows:
        row_columns = list(row)
        cursor = connection.execute(
            'INSERT INTO {} ({}) VALUES ({})'.format(
                quoted_table,
                ', '.join(_quote_identifier(column) for column in row_columns),
                ', '.join('?' for _ in row_columns)
            ),
            [_to_sqlite_value(row[column]) for column in row_columns]
        )
        rowcount += cursor.rowcount
        lastrowid = cursor.lastrowid
    return {'rowcount': rowcount, 'lastrowid': lastrowid}


def sqlite_write(db_path, write_value):
    """Runs a write (a query, a parameterized query or rows to insert) in one
    transaction, creating the database file if it is missing."""
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            if isinstance(write_value, dict) and 'table' in write_value:
                if 'values' not in write_value:
                    raise ValueError('sqlite: {"table": ...} needs "values", a dict or a list of dicts')
                return _insert_rows(connection, write_value['table'], write_value['values'])
            query, params = _query_and_params(write_value)
            if params is None:
                try:
                    cursor = connection.execute(query)
                except (sqlite3.ProgrammingError, sqlite3.Warning) as error:
                    # More than one statement: run them as a script.
                    if 'one statement' not in str(error):
                        raise
                    connection.executescript(query)
                    return {'rowcount': connection.total_changes, 'lastrowid': None}
            elif _is_many(params):
                cursor = connection.executemany(query, params)
            else:
                cursor = connection.execute(query, params)
            return {'rowcount': cursor.rowcount, 'lastrowid': cursor.lastrowid}
    finally:
        connection.close()


def eval_sqlite_input(input_expression, evaluate):
    """inputExpression is a Python expression like the action's other inputs,
    so a query is usually a string literal or an f-string. Plain SQL that is
    not a valid expression (SELECT * FROM scores) is used as written."""
    try:
        return evaluate(input_expression)
    except SyntaxError:
        return input_expression
