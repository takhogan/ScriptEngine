"""Action result files: what one action did, as fields.

Every action writes `{counter}-{actionName}-{actionGroup}-result.json` next to
its action-log.json, at info and debug level. The action log has the same
shape for every action; this file holds what is specific to each one: a
detect's matches and scores, where a click landed, a colour comparison's
score, what OCR read. It is listed among the action log's supporting files,
so the studio and the MCP find it like any other file of the action.

The type definition is ScriptActionResult in screenplan-contracts
(packages/screenplan-contracts/schemas/script-action-result.schema.json).
Change a field there and here together.

    {
      "format": "screenplan.action-result", "version": 1,
      "action": "detectObject", "action_group": 1, "script_counter": 2,
      "fields": { "detect_type": "floatingObject", "matches": [...], ... }
    }

Fields arrive from several places while an action runs (the detection, the
thread that draws its log images, the executor), and a parallel detect runs
in a worker process with its own copy of the action log. So the file is the
record, not any one copy in memory: each update reads it, merges the new
fields in (nested objects merge, everything else is replaced) and writes it
back, on the action log's single writer thread.
"""
import json
import math
import os

import numpy as np

RESULT_FORMAT = 'screenplan.action-result'
RESULT_VERSION = 1
RESULT_FILE_SUFFIX = 'result.json'


def jsonable(value):
    """`value` with numpy types, tuples and non-finite floats made JSON-safe."""
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


def point(xy):
    return None if xy is None else {'x': jsonable(xy[0]), 'y': jsonable(xy[1])}


def size(width, height):
    return {'width': jsonable(width), 'height': jsonable(height)}


def box(x, y, width, height):
    return {'x': jsonable(x), 'y': jsonable(y), 'width': jsonable(width), 'height': jsonable(height)}


def merge(base, update):
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def envelope(action_name, action_group, script_counter):
    return {
        'format': RESULT_FORMAT,
        'version': RESULT_VERSION,
        'action': action_name,
        'action_group': action_group,
        'script_counter': script_counter,
        'fields': {},
    }


def write_result(path, initial, fields):
    """Merge `fields` into the result file at `path`, creating it from `initial`."""
    document = None
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as result_file:
                document = json.load(result_file)
        except (OSError, ValueError):
            document = None
    if document is None:
        document = initial
    merge(document.setdefault('fields', {}), fields)
    temp_path = path + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as result_file:
        json.dump(document, result_file, indent=2)
    os.replace(temp_path, path)
