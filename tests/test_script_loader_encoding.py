import builtins
import json

import pytest

import ScriptEngine.script_loader as script_loader_mod

# What a script saved by the editor or write_script can hold: a conditional's
# text icon (⬋ ? ⬊), the icon glyphs write_script left before it saved their
# codes (🔐 is f0 9f 94 90, ⌨️ ends ef b8 8f: 0x90 and 0x8f have no character
# in cp1252), and whatever a user typed into a field.
TYPED = '日本語 ﬁ 🔐'


def windows_default_open(file, mode='r', *args, **kwargs):
    # On Windows, open() without an encoding uses the ANSI code page.
    if 'b' not in mode and kwargs.get('encoding') is None:
        kwargs['encoding'] = 'cp1252'
    return builtins.open(file, mode, *args, **kwargs)


def write_script(folder, *, bom=False):
    folder.mkdir()
    action_rows = [{
        'rowID': 0,
        'actionRowIndex': 0,
        'actions': [
            {
                'actionName': 'conditionalStatement', 'actionGroup': 0, 'childGroups': [], 'parentGroups': [],
                'actionIcon': {'iconType': 'textIcon', 'iconText': '\n  ⬋ ? ⬊\n  \ncount > 2'},
                'actionData': {'condition': 'count > 2'},
            },
            {
                'actionName': 'keyboardAction', 'actionGroup': 1, 'childGroups': [], 'parentGroups': [],
                'actionIcon': {'iconType': 'symbolIcon', 'iconSymbol': '\n    ⌨️\n  '},
                'actionData': {'keyboardExpression': TYPED},
            },
        ],
    }]
    files = {
        'actionRows.json': action_rows,
        'props.json': {'deploymentToLibrary': 'false', 'description': TYPED},
        'inputs.json': [['name', repr(TYPED), True]],
        'outputs.json': [],
    }
    for name, value in files.items():
        text = json.dumps(value, ensure_ascii=False)
        (folder / name).write_bytes(('\ufeff' if bom else '').encode('utf-8') + text.encode('utf-8'))


class FakeLogger:
    def log(self, *args, **kwargs):
        return None


@pytest.fixture
def cp1252_host(monkeypatch, tmp_path):
    monkeypatch.setattr(script_loader_mod, 'script_logger', FakeLogger())
    monkeypatch.setattr(script_loader_mod, 'open', windows_default_open, raising=False)
    monkeypatch.setattr(script_loader_mod, '_resolve_library_script_path', lambda name, *_: str(tmp_path / name))
    return tmp_path


def test_a_script_with_non_ascii_text_loads_on_a_cp1252_host(cp1252_host):
    write_script(cp1252_host / 'Typed')

    script = script_loader_mod.parse_script('Typed')

    actions = script['actionRows'][0]['actions']
    assert actions[0]['actionIcon']['iconText'].strip().startswith('⬋ ? ⬊')
    assert actions[1]['actionData']['keyboardExpression'] == TYPED
    assert actions[1]['actionIcon']['iconSymbol'].strip() == '⌨️'
    assert script['props']['description'] == TYPED
    assert script['inputs'] == [['name', repr(TYPED), True]]


def test_a_script_file_saved_with_a_bom_loads(cp1252_host):
    write_script(cp1252_host / 'Notepad', bom=True)

    script = script_loader_mod.parse_script('Notepad')

    assert script['actionRows'][0]['actions'][1]['actionData']['keyboardExpression'] == TYPED


def test_a_text_asset_is_read_as_utf8(cp1252_host):
    (cp1252_host / 'run.sh').write_bytes('echo "日本語 🔐"\n'.encode('utf-8'))

    assert script_loader_mod._read_asset_payload('run.sh', 'shellScript', str(cp1252_host), None, None) == 'echo "日本語 🔐"\n'


def test_a_file_that_is_not_utf8_names_itself(cp1252_host):
    write_script(cp1252_host / 'Edited')
    # Saved again in cp1252 by a text editor: 'é' is the single byte 0xe9.
    (cp1252_host / 'Edited' / 'props.json').write_bytes('{"deploymentToLibrary": "false", "description": "café"}'.encode('cp1252'))

    with pytest.raises(ValueError, match=r"Edited/props\.json is not UTF-8 text: byte 0xe9 at offset 52"):
        script_loader_mod.parse_script('Edited')
