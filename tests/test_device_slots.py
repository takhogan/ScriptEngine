"""Device slots (interface version 23, workspace docs/specs/device-slots.md).

The --device binding list, the load-time v22 mapping (checked against
@screenplan/script-vcs's migrateV22ToV23 on the real library when a dump is
given), the run-start check across scriptReferences, and slot resolution in
DeviceController: managers cached per device, deviceMap, the errors that
name a slot.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ScriptEngine.common import device_slots as ds
from ScriptEngine.common.device_slots import (
    DeviceBindingError, map_v22_script, parse_device_bindings, static_required_slots,
)


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('device-slots-logs') / 'test.txt'))
    return logger


def act(name, group, **data):
    return {'actionName': name, 'actionGroup': group, 'actionData': data}


def script(actions, props=None):
    return {'actionRows': [{'actions': actions}], 'props': props or {}}


# ---------------------------------------------------------------------------
# --device

def test_bare_values_bind_their_types_default_slot():
    assert parse_device_bindings('avd:Pixel_7') == ({'phone0': 'avd:Pixel_7'}, None)
    assert parse_device_bindings('bluestacks:Pie64') == ({'phone0': 'bluestacks:Pie64'}, None)
    assert parse_device_bindings('ios:00008110-ABC') == ({'phone0': 'ios:00008110-ABC'}, None)
    assert parse_device_bindings('pikvm:office-pc') == ({'desktop0': 'pikvm:office-pc'}, None)
    assert parse_device_bindings('host') == ({'desktop0': 'host'}, None)
    assert parse_device_bindings('file:/tmp/a.png') == ({}, 'file:/tmp/a.png')
    assert parse_device_bindings('something') == ({'device0': 'something'}, None)
    for nothing in (None, '', 'null', [], ['', 'null']):
        assert parse_device_bindings(nothing) == ({}, None)


def test_slot_entries_comma_and_repeated_forms():
    want = {'phone0': 'avd:Pixel_7', 'desktop0': 'pikvm:office-pc'}
    assert parse_device_bindings('phone0=avd:Pixel_7,desktop0=pikvm:office-pc')[0] == want
    assert parse_device_bindings(['phone0=avd:Pixel_7', 'desktop0=pikvm:office-pc'])[0] == want
    # Split at the first '=' only; a comma not followed by `<slot>=` stays in the value.
    assert parse_device_bindings('phone1=adb:10.0.0.5:5555,x=y')[0] == {'phone1': 'adb:10.0.0.5:5555,x=y'}
    assert parse_device_bindings('phone0=file:/tmp/a=b.png')[0] == {'phone0': 'file:/tmp/a=b.png'}
    assert parse_device_bindings(['desktop0=host', 'avd:Pixel_7'])[0] == {'desktop0': 'host', 'phone0': 'avd:Pixel_7'}


def test_binding_errors():
    with pytest.raises(DeviceBindingError, match='bound twice'):
        parse_device_bindings(['phone0=avd:A', 'avd:B'])
    with pytest.raises(DeviceBindingError, match="'host' cannot be bound"):
        parse_device_bindings('host=avd:A')
    with pytest.raises(DeviceBindingError, match="'none' cannot be bound"):
        parse_device_bindings('none=avd:A')


# ---------------------------------------------------------------------------
# the load-time v22 mapping

def test_map_v22_follows_the_table_and_lists_the_slots():
    s = script([act('detectObject', 1, targetSystem='adb'), act('detectObject', 2, targetSystem='python'),
                act('codeBlock', 3, targetSystem='none'), act('detectObject', 4, targetSystem='ios')],
               {'targetSystem': 'python'})
    assert map_v22_script(s['actionRows'], s['props'], 22)
    assert [a['actionData']['targetSystem'] for a in s['actionRows'][0]['actions']] == ['phone0', 'desktop0', 'none', 'phone0']
    assert s['props']['devices'] == [{'slot': 'desktop0'}, {'slot': 'phone0'}]
    assert s['props']['targetSystem'] == 'desktop0'
    assert not map_v22_script(s['actionRows'], s['props'], None), 'idempotent'


def test_map_v22_host_rule_and_v23_untouched():
    s = script([act('detectObject', 1, targetSystem='python'), act('detectObject', 2, targetSystem='kvm')])
    map_v22_script(s['actionRows'], s['props'], 22)
    assert [a['actionData']['targetSystem'] for a in s['actionRows'][0]['actions']] == ['host', 'desktop0']
    assert s['props']['devices'] == [{'slot': 'desktop0'}]
    v23 = script([act('detectObject', 1, targetSystem='python')])
    assert not map_v22_script(v23['actionRows'], v23['props'], 23)
    assert v23['actionRows'][0]['actions'][0]['actionData']['targetSystem'] == 'python'


def test_loader_maps_a_v22_folder(tmp_path):
    from ScriptEngine.script_loader import parse_script_file
    folder = tmp_path / 'Old_Script'
    folder.mkdir()
    rows = [{'actions': [dict(act('sleepStatement', 0, targetSystem='adb', inputExpression='1'), childGroups=[])]}]
    for name, value in (('actionRows.json', rows), ('props.json', {'targetSystem': 'none'}),
                        ('inputs.json', []), ('outputs.json', [])):
        (folder / name).write_text(json.dumps(value), encoding='utf-8')
    (folder / 'interfaceVersion.txt').write_text('22', encoding='utf-8')
    obj = parse_script_file('Old_Script', *(open(folder / n, 'rb') for n in ('actionRows.json', 'props.json', 'inputs.json', 'outputs.json')), str(folder))
    assert obj['actionRows'][0]['actions'][0]['actionData']['targetSystem'] == 'phone0'
    assert obj['props']['devices'] == [{'slot': 'phone0'}]


SLOTS_DUMP = os.environ.get('SCREENPLAN_SLOTS_DUMP')
LIBRARY = os.environ.get('SCREENPLAN_SLOTS_LIBRARY', os.path.expanduser(
    '~/Library/Application Support/ScriptEngineController/scripts/scriptLibrary'))


@pytest.mark.skipif(not SLOTS_DUMP, reason='set SCREENPLAN_SLOTS_DUMP to the dump written by script-vcs corpus.test.mjs (SCRIPT_VCS_SLOTS_DUMP)')
def test_load_time_mapping_matches_the_typescript_migration_on_the_library():
    with open(SLOTS_DUMP, 'r', encoding='utf-8') as f:
        dump = json.load(f)
    checked = 0
    for label, want in dump.items():
        ws, name = label.split('/', 1)
        folder = os.path.join(LIBRARY, ws, name)
        with open(os.path.join(folder, 'actionRows.json'), 'r', encoding='utf-8') as f:
            rows = json.load(f)
        with open(os.path.join(folder, 'props.json'), 'r', encoding='utf-8') as f:
            props = json.load(f)
        with open(os.path.join(folder, 'interfaceVersion.txt'), 'r', encoding='utf-8') as f:
            version = int(f.read().strip())
        map_v22_script(rows, props, version)
        targets = [(a.get('actionData') or {}).get('targetSystem') for r in rows for a in r.get('actions', [])]
        assert targets == want['targets'], label
        assert props.get('devices') == want['devices'], label
        assert props.get('targetSystem') == want['propsTargetSystem'], label
        checked += 1
    assert checked == len(dump) > 0


# ---------------------------------------------------------------------------
# the run-start check

def test_static_required_slots_follow_device_maps_into_children():
    login = script([act('detectObject', 1, targetSystem='device0'), act('detectObject', 2, targetSystem='phone1')],
                   {'devices': [{'slot': 'device0'}, {'slot': 'phone1', 'description': 'second phone'}]})
    top = script([
        act('detectObject', 1, targetSystem='desktop0'),
        act('scriptReference', 2, targetSystem='none', scriptName='Login', deviceMap={'device0': 'tablet0'}),
        act('scriptReference', 3, targetSystem='none', scriptName='{computed}'),
        act('scriptReference', 4, targetSystem='none', scriptName='Missing'),
    ], {'devices': [{'slot': 'desktop0'}, {'slot': 'tablet0', 'description': 'the tablet'}]})
    required, adb = static_required_slots(top, lambda name: login if name == 'Login' else None)
    assert required == {'phone1': ['second phone'], 'tablet0': ['the tablet']}
    assert adb == set()
    # Mapping a child's required slot onto the parent's device0 makes it the host's when unbound.
    top2 = script([act('scriptReference', 1, targetSystem='none', scriptName='Login', deviceMap={'phone1': 'device0'})])
    assert static_required_slots(top2, lambda name: login)[0] == {}


def test_static_required_slots_need_a_childs_default_mapped_slots():
    # A parent whose own props list nothing yet (an older save) still needs the child's phone0 at run start.
    child = script([act('detectObject', 1, targetSystem='desktop0'), act('detectObject', 2, targetSystem='phone0')],
                   {'devices': [{'slot': 'desktop0'}, {'slot': 'phone0', 'description': 'the phone'}]})
    top = script([act('scriptReference', 1, targetSystem='none', scriptName='Test_Slots_A')])
    assert static_required_slots(top, lambda name: child)[0] == {'phone0': ['the phone']}
    mapped = script([act('scriptReference', 1, targetSystem='none', scriptName='Test_Slots_A', deviceMap={'phone0': 'phone1'})])
    assert static_required_slots(mapped, lambda name: child)[0] == {'phone1': ['the phone']}


# ---------------------------------------------------------------------------
# DeviceController

class FakeManager:
    def __init__(self, kind, params=None, input_source=None):
        self.kind, self.params, self.input_source = kind, params, input_source
        self.width = self.height = 10

    def screenshot(self):
        return self.kind

    def ensure_device_initialized(self):
        pass


@pytest.fixture
def controller(monkeypatch):
    import ScriptEngine.device_controller as dc
    from ScriptEngine.managers import desktop_device_manager, adb_device_manager
    monkeypatch.setattr(desktop_device_manager, 'DesktopDeviceManager', lambda props, src: FakeManager('desktop', None, src))
    monkeypatch.setattr(adb_device_manager, 'ADBDeviceManager',
                        lambda props, params, src, **kw: FakeManager('adb:' + params.get('deviceId', 'file'), params, src))
    config = {'avd:Pixel_7': {'deviceId': 'avd:Pixel_7', 'type': 'avd'},
              'bluestacks:Pie64': {'deviceId': 'bluestacks:Pie64', 'type': 'bluestacks'}}
    monkeypatch.setattr(dc.DeviceController, 'get_device_params', staticmethod(lambda key: config.get(key)))

    def make(bindings, all_slots_value=None):
        return dc.DeviceController({'dir_path': '.', 'width': None, 'height': None}, {}, None, None,
                                   bindings=bindings, all_slots_value=all_slots_value)
    return make


def test_unbound_device0_and_desktop0_and_host_share_the_host(controller):
    c = controller({})
    assert c.initialize_device('device0') is c.initialize_device('desktop0') is c.initialize_device('host') is c.initialize_device('')
    assert c.device_key('device0') == c.device_key('host') == 'host'
    assert c.describe_target('desktop0') == ('desktop0', 'host')


def test_bound_slots_get_their_own_managers(controller):
    c = controller({'phone0': 'avd:Pixel_7', 'phone1': 'bluestacks:Pie64', 'desktop0': 'host'})
    p0, p1 = c.initialize_device('phone0'), c.initialize_device('phone1')
    assert p0 is not p1 and p0.kind == 'adb:avd:Pixel_7' and p1.kind == 'adb:bluestacks:Pie64'
    assert c.get_device_action('phone1', 'screenshot')() == 'adb:bluestacks:Pie64'
    assert c.initialize_device('desktop0') is c.initialize_device('host')
    # A v22 'adb' (system scripts) is the device bound to phone0.
    assert c.initialize_device('adb') is p0
    assert c.describe_target('phone1') == ('phone1', 'bluestacks:Pie64')


def test_unbound_and_missing_slots_name_the_slot(controller):
    c = controller({'phone0': 'avd:Gone'})
    with pytest.raises(Exception, match='needs slot phone1, and the run bound nothing to it: add phone1=<device>'):
        c.initialize_device('phone1')
    with pytest.raises(Exception, match='slot phone0 is bound to avd:Gone, which .* no longer holds'):
        c.initialize_device('phone0')
    assert c.describe_target('phone1') == ('phone1', None)


def test_device_map_maps_a_childs_slots(controller):
    c = controller({'tablet0': 'avd:Pixel_7'})
    c.push_slot_map({'device0': 'tablet0'})
    assert c.initialize_device('device0').kind == 'adb:avd:Pixel_7'
    assert c.initialize_device('desktop0').kind == 'desktop', 'unmapped slots keep their name'
    c.push_slot_map({'phone0': 'device0'})
    assert c.run_slot('phone0') == 'tablet0', 'maps compose through nested calls'
    assert c.run_slot('host') == 'host'
    c.pop_slot_map()
    c.pop_slot_map()
    assert c.run_slot('device0') == 'device0'


def test_check_child_slots_after_mapping(controller):
    c = controller({'tablet0': 'avd:Pixel_7'})
    child = script([act('detectObject', 1, targetSystem='phone1')], {'devices': [{'slot': 'phone1', 'description': 'd'}]})
    c.push_slot_map({'phone1': 'tablet0'})
    c.check_child_slots(child, 'Child')
    c.pop_slot_map()
    with pytest.raises(Exception, match='script Child needs device slots the run bound nothing to: phone1: d'):
        c.check_child_slots(child, 'Child')


def test_check_bindings_lists_missing_slots_and_warns_on_kinds(controller):
    c = controller({'phone0': 'avd:Pixel_7', 'desktop0': 'avd:Pixel_7'})
    errors, warnings = c.check_bindings({'phone0': [], 'tablet1': ['the tablet'], 'phone2': []}, {'phone0'})
    assert len(errors) == 1 and 'phone2' in errors[0] and 'tablet1: the tablet' in errors[0]
    assert warnings == ['DEVICE CONTROLLER: slot desktop0 is a desktop slot, bound to avd:Pixel_7 (a adb device); running it anyway']
    errors, _ = controller({'phone0': 'pikvm:x'}).check_bindings({}, {'phone0'})
    assert 'not an adb device' in errors[0]


def test_a_bare_file_binds_every_slot(controller, tmp_path):
    import cv2
    import numpy as np
    png = tmp_path / 'still.png'
    cv2.imwrite(str(png), np.zeros((4, 6, 3), dtype=np.uint8))
    c = controller({}, all_slots_value='file:' + str(png))
    assert c.initialize_device('phone3').input_source['width'] == 6
    assert c.check_bindings({'phone3': []})[0] == []


# ---------------------------------------------------------------------------
# the log video: one per device, labelled with the slot

def test_log_video_splits_by_device_and_labels_the_slot():
    from ScriptEngine.script_log_preview_generator import ScriptLogPreviewGenerator as G
    frame = lambda slot, device: {'script_name': 'S', 'action_name': 'a', 'post_file': 'p', 'device_slot': slot, 'device_id': device}
    one = [frame('phone0', 'avd:A'), frame('phone0', 'avd:A')]
    assert G.split_by_device(one, '/r/script-log-preview.mp4') == [('/r/script-log-preview.mp4', one)]
    mixed = [frame('phone0', 'avd:A'), frame('desktop0', 'host'), frame('phone0', 'avd:A'), frame('tablet0', 'avd:B')]
    out = G.split_by_device(mixed, '/r/script-log-preview.mp4')
    assert [path for path, _ in out] == ['/r/script-log-preview.mp4', '/r/script-log-preview-desktop0.mp4', '/r/script-log-preview-tablet0.mp4']
    assert [len(frames) for _, frames in out] == [2, 1, 1]
    assert G.frame_title(frame('phone0', 'avd:A')) == 'S [phone0]'
    assert G.frame_title({'script_name': 'S'}) == 'S'
