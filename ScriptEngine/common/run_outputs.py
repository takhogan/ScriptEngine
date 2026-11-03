"""outputs.json: a script's outputs in a form a program can read.

outputs.txt, beside it, is for people: `<type> name: str(value)` per line. The
controller reads outputs.json instead for an agent tool call's result
(agent-toolkits plan §7, item 2):

    {"version": 1, "outputs": {"<name>": {"type": "json", "value": <value>}
                                        | {"type": "repr", "value": "<repr(value)>"}}}

A value is "json" when json.dumps takes it as it is (no default= hook, and no
NaN or infinity, which JSON has no spelling for), else its repr. A SecureSecret
is never serialized as its value: json.dumps refuses it, so it, and any list or
dict holding one, ends up as a repr, which SecureSecret redacts.
"""
import json
import os

OUTPUTS_JSON_FILENAME = 'outputs.json'
OUTPUTS_JSON_VERSION = 1


def describe_output(value):
    """One output's entry in outputs.json."""
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {'type': 'repr', 'value': repr(value)}
    return {'type': 'json', 'value': value}


def outputs_document(outputs):
    """outputs.json's content for a {name: value} dict."""
    return {
        'version': OUTPUTS_JSON_VERSION,
        'outputs': {name: describe_output(value) for name, value in outputs.items()},
    }


def write_outputs_json(path, outputs):
    """Writes outputs.json at path, whole or not at all: it goes to a temporary
    file first and is renamed into place, so a reader never sees half of it."""
    document = outputs_document(outputs)
    temporary_path = path + '.tmp'
    with open(temporary_path, 'w', encoding='utf-8') as outputs_file:
        json.dump(document, outputs_file)
    os.replace(temporary_path, path)
    return document


def outputs_json_path_beside(outputs_txt_path):
    return os.path.join(os.path.dirname(outputs_txt_path), OUTPUTS_JSON_FILENAME)


def script_output_names(script_object):
    """The names in a script's outputs.json definition ([name, expression,
    isDefault] rows), in order."""
    return [row[0].strip() for row in (script_object.get('outputs') or [])]


def outputs_from_state(names, state):
    """The values state holds for names, leaving out the names it has none for."""
    return {name: state[name] for name in names if name in state}
