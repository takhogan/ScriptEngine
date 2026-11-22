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

def test_a_bare_file_value_is_a_still_image_for_every_slot():
    assert parse_device_bindings('file:/tmp/a.png') == ({}, 'file:/tmp/a.png')
    assert parse_device_bindings(['phone0=avd:Pixel_7', 'file:/tmp/a.png']) == (
        {'phone0': 'avd:Pixel_7'}, 'file:/tmp/a.png')
    for nothing in (None, '', 'null', [], ['', 'null'], 'phone0=', 'phone0=null'):
        assert parse_device_bindings(nothing) == ({}, None)


def test_a_bare_sim_value_is_a_simulated_device_for_every_slot():
    value = 'sim:/packs/examplegame?seed=3&start=HOST/run-a'
    assert parse_device_bindings(value) == ({}, value)
    assert parse_device_bindings(['', value]) == ({}, value)
    assert parse_device_bindings('sim:ExampleGame/examplegame') == ({}, 'sim:ExampleGame/examplegame')
    assert ds.default_slot_for_device_id(value) == ds.ALL_SLOTS


def test_a_sim_is_never_bound_to_one_slot_nor_beside_another_device():
    with pytest.raises(DeviceBindingError, match=r'^--device phone0=sim:/p: a simulated device stands in for every slot: '
                                                 r'pass it alone, as --device sim:/p$'):
        parse_device_bindings('phone0=sim:/p')
    with pytest.raises(DeviceBindingError, match=r'pass it alone, without desktop0=host, phone0=avd:A$'):
        parse_device_bindings(['sim:/p', 'phone0=avd:A', 'desktop0=host'])
    with pytest.raises(DeviceBindingError, match=r'given twice \(sim:/p and file:/tmp/a.png\)'):
        parse_device_bindings(['sim:/p', 'file:/tmp/a.png'])
    with pytest.raises(DeviceBindingError, match="'phone' is not a slot"):
        parse_device_bindings('phone=sim:/p')


@pytest.mark.parametrize('value, slot', [
    ('avd:Pixel_7', 'phone0'),
    ('bluestacks:Pie64', 'phone0'),
    ('adb:10.0.0.5:5555', 'phone0'),
    ('ios:00008110-ABC', 'phone0'),
    ('pikvm:office-pc', 'desktop0'),
    ('host', 'desktop0'),
    ('MININT-X<>bluestacks:Rvc64', 'device0'),
    ('something', 'device0'),
])
def test_any_other_bare_value_is_an_error_naming_its_slot(value, slot):
    with pytest.raises(DeviceBindingError) as raised:
        parse_device_bindings(value)
    assert str(raised.value) == '--device {0}: name its slot, as --device {1}={0}'.format(value, slot)
    # The same in a list beside slot entries, and in a comma-separated list.
    with pytest.raises(DeviceBindingError, match='name its slot'):
        parse_device_bindings(['desktop0=host', value])
    if slot != 'phone0':
        with pytest.raises(DeviceBindingError, match='name its slot'):
            parse_device_bindings(value + ',phone0=avd:Pixel_7')


def test_the_error_message_matches_the_spec_example():
    with pytest.raises(DeviceBindingError, match=r'^--device avd:Pixel_7: name its slot, as --device phone0=avd:Pixel_7$'):
        parse_device_bindings('avd:Pixel_7')


def test_a_misspelt_slot_is_named_as_not_a_slot():
    with pytest.raises(DeviceBindingError, match="'phone' is not a slot"):
        parse_device_bindings('phone=avd:Pixel_7')
    with pytest.raises(DeviceBindingError, match="'Phone0' is not a slot"):
        parse_device_bindings('Phone0=avd:Pixel_7')


def test_slot_entries_comma_and_repeated_forms():
    want = {'phone0': 'avd:Pixel_7', 'desktop0': 'pikvm:office-pc'}
    assert parse_device_bindings('phone0=avd:Pixel_7,desktop0=pikvm:office-pc')[0] == want
    assert parse_device_bindings(['phone0=avd:Pixel_7', 'desktop0=pikvm:office-pc'])[0] == want
    # Split at the first '=' only; a comma not followed by `<slot>=` stays in the value.
    assert parse_device_bindings('phone1=adb:10.0.0.5:5555,x=y')[0] == {'phone1': 'adb:10.0.0.5:5555,x=y'}
    assert parse_device_bindings('phone0=file:/tmp/a=b.png')[0] == {'phone0': 'file:/tmp/a=b.png'}
    assert parse_device_bindings(['desktop0=host', 'phone0=avd:Pixel_7'])[0] == {'desktop0': 'host', 'phone0': 'avd:Pixel_7'}
    assert parse_device_bindings(' device0 = MININT-X<>bluestacks:Rvc64 ')[0] == {'device0': 'MININT-X<>bluestacks:Rvc64'}


def test_binding_errors():
    with pytest.raises(DeviceBindingError, match='bound twice'):
        parse_device_bindings(['phone0=avd:A', 'phone0=avd:B'])
    with pytest.raises(DeviceBindingError, match='given twice'):
        parse_device_bindings(['file:/tmp/a.png', 'file:/tmp/b.png'])
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
    # How to bind it, for an MCP caller as well as the command line.
    assert 'devices: {"tablet1": "<device id>"} in an MCP run_script or test_actions call' in errors[0]
    assert '--device tablet1=<device> on the command line' in errors[0]
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


# ---------------------------------------------------------------------------
# slots as read-only state variables: phone0["type"] == "ios"

def test_slot_info_is_read_only_and_survives_copies():
    import copy
    import pickle
    info = ds.slot_info('phone0', 'phone0', 'ios:00008110-ABC')
    assert info['type'] == 'ios' and info['driver'] == 'ios' and info['bound'] is True
    for write in (lambda: info.__setitem__('type', 'android'), lambda: info.update(type='x'),
                  lambda: info.pop('type'), lambda: info.clear(), lambda: info.__delitem__('type')):
        with pytest.raises(TypeError, match='phone0 is read-only'):
            write()
    assert copy.deepcopy(info) is info
    restored = pickle.loads(pickle.dumps(info))
    assert isinstance(restored, ds.SlotInfo) and restored == info
    assert json.loads(json.dumps({'phone0': info}))['phone0']['type'] == 'ios'


@pytest.mark.parametrize('device_id, label, driver', [
    ('avd:Pixel_7', 'android', 'adb'),
    ('bluestacks:Pie64', 'android', 'adb'),
    ('ios:00008110-ABC', 'ios', 'ios'),
    ('pikvm:office-pc', 'kvm', 'kvm'),
    ('file:/tmp/a.png', 'file', 'file'),
    (None, None, None),
])
def test_slot_info_types(device_id, label, driver):
    info = ds.slot_info('phone1', 'phone1', device_id)
    assert (info['type'], info['driver'], info['bound']) == (label, driver, device_id is not None)


def test_the_host_reports_its_operating_system():
    assert ds.slot_info('desktop0', 'desktop0', 'host', platform='win32')['type'] == 'windows'
    assert ds.slot_info('desktop0', 'desktop0', 'host', platform='darwin')['type'] == 'macos'
    assert ds.slot_info('desktop0', 'desktop0', 'host', platform='linux')['type'] == 'linux'


def test_slot_infos_cover_defaults_script_slots_and_bindings(controller):
    from ScriptEngine.common.script_engine_utils import state_eval
    c = controller({'phone0': 'ios:00008110-ABC', 'tablet2': 'avd:Pixel_7'})
    rows = [{'actions': [act('detectObject', 1, targetSystem='phone3')]}]
    infos = c.slot_infos({'devices': [{'slot': 'desktop1'}]}, rows)
    assert list(infos) == ['device0', 'desktop0', 'desktop1', 'phone0', 'phone3', 'tablet0', 'tablet2']
    assert infos['desktop0']['deviceId'] == 'host' and infos['desktop0']['bound'] is True
    assert infos['phone3']['bound'] is False and infos['phone3']['type'] is None
    assert infos['tablet2']['type'] == 'android'
    assert state_eval('phone0["type"] == "ios"', {}, dict(infos)) is True
    assert state_eval('phone3["type"] == "ios"', {}, dict(infos)) is False


def test_slot_infos_follow_the_device_map(controller):
    c = controller({'phone1': 'ios:00008110-ABC'})
    c.push_slot_map({'phone0': 'phone1'})
    info = c.slot_infos({}, [])['phone0']
    assert (info['slot'], info['runSlot'], info['type']) == ('phone0', 'phone1', 'ios')
    c.pop_slot_map()
    assert c.slot_infos({}, [])['phone0']['bound'] is False


def make_executor(device_controller, actions=(), props=None, state=None):
    from types import SimpleNamespace
    from ScriptEngine.script_executor import ScriptExecutor
    script_obj = {'props': dict(props or {}, script_name='Cross_Platform'), 'actionRows': [{'actions': list(actions)}],
                  'inputs': [], 'outputs': []}
    return ScriptExecutor(script_obj, {}, None, 'Cross_Platform', 'now', 'id', device_controller,
                          SimpleNamespace(get_script_version=lambda name: None), None, None, None,
                          state=state, create_log_folders=False)


def test_a_conditional_statement_branches_on_the_bound_phone(controller, monkeypatch):
    from ScriptEngine.common.enums import ScriptExecutionState
    from ScriptEngine.system_script_action_executor import SystemScriptActionExecutor
    import ScriptEngine.system_script_action_executor as ssae
    from types import SimpleNamespace
    log = SimpleNamespace(set_summary=lambda *a: None, add_post_file=lambda *a, **k: None)
    monkeypatch.setattr(ssae, 'script_logger', SimpleNamespace(log=lambda *a, **k: None, get_action_log=lambda: log,
                                                               get_log_path_prefix=lambda: '/tmp/'))
    system = SystemScriptActionExecutor(base_script_name='s', props={'dir_path': '/tmp'}, io_executor=None,
                                        screen_plan_server_attached=False)

    def condition(state, text):
        action = {'actionName': 'conditionalStatement', 'actionGroup': 1, 'actionData': {'condition': text}}
        return system.handle_action(action, state, {"script_counter": 1}, [])[1]

    ios_run = make_executor(controller({'phone0': 'ios:00008110-ABC'}))
    android_run = make_executor(controller({'phone0': 'avd:Pixel_7'}))
    assert condition(ios_run.state, 'phone0["type"] == "ios"') == ScriptExecutionState.SUCCESS
    assert condition(android_run.state, 'phone0["type"] == "ios"') == ScriptExecutionState.FAILURE
    assert condition(android_run.state, 'phone0["type"] == "android" and desktop0["bound"]') == ScriptExecutionState.SUCCESS


def test_a_script_variable_of_the_same_name_wins_and_children_see_their_mapped_slot(controller):
    c = controller({'phone1': 'ios:00008110-ABC'})
    run = make_executor(c, state={'tablet0': 'mine'})
    assert run.state['tablet0'] == 'mine' and run.state['phone1']['type'] == 'ios'
    child = make_executor(c)
    assert child.state['phone0']['bound'] is False
    c.push_slot_map({'phone0': 'phone1'})
    child.set_device_state()
    assert child.state['phone0']['type'] == 'ios' and child.state['phone0']['runSlot'] == 'phone1'
