"""The simulated device (managers/simulated_device_manager.py) on a made-up
sim pack, and the run clock it makes virtual (common/sim_clock.py).

The pack has two recorded runs of a script 'Loader': a home screen, a key
press, a click on an icon, a loading screen and the city view. Frames are
flat colours, so a screenshot says which frame the device is showing."""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.common import sim_clock
from ScriptEngine.device_controller import DeviceController
from ScriptEngine.managers.simulated_device_manager import SimulatedDeviceError, SimulatedDeviceManager

W, H = 40, 60
COLOURS = {'home0': 10, 'home1': 40, 'load0': 80, 'load1': 90, 'city0': 160, 'home2': 50, 'load2': 85, 'city2': 170}


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('sim-logs') / 'test.txt'))
    return logger


@pytest.fixture(autouse=True)
def wall_clock_again():
    sim_clock.reset()
    yield
    sim_clock.reset()


def click(t, x, y, script='Loader', group=2, state='home'):
    return {'t': t, 'kind': 'click', 'x': x, 'y': y, 'box': {'x': x - 5, 'y': y - 5, 'width': 10, 'height': 10},
            'to': None, 'keys': None, 'script': script, 'group': group, 'state': state}


@pytest.fixture
def pack(tmp_path):
    frames = tmp_path / 'frames'
    frames.mkdir()
    for name, v in COLOURS.items():
        cv2.imwrite(str(frames / (name + '.png')), np.full((H, W, 3), v, np.uint8))
    runs = [
        {'id': 'HOST/run-a', 'root': 'Loader', 'host': 'HOST', 'return_code': 0,
         'frames': [[0.0, 'home0', 'home'], [3.0, 'home1', 'home'], [6.0, 'load0', 'load'],
                    [26.0, 'load1', 'load'], [30.0, 'city0', 'city']],
         'inputs': [{'t': 1.0, 'kind': 'key', 'x': None, 'y': None, 'box': None, 'to': None, 'keys': None,
                     'script': 'Loader', 'group': 13, 'state': 'home'},
                    click(4.0, 20, 30), click(31.0, 5, 5, script='City', group=1, state='city')]},
        {'id': 'HOST/run-b', 'root': 'Loader', 'host': 'HOST', 'return_code': 0,
         'frames': [[0.0, 'home2', 'home'], [2.0, 'load2', 'load'], [12.0, 'city2', 'city']],
         'inputs': [click(1.0, 21, 31)]},
    ]
    doc = {'format': 'screenplan-ui-sim-pack', 'version': 0, 'width': W, 'height': H, 'screenshot_s': 0.5,
           'frames_dir': 'frames', 'runs': runs}
    (tmp_path / 'sim-pack.json').write_text(json.dumps(doc))
    return tmp_path


def sim(pack, **params):
    return SimulatedDeviceManager({}, dict({'path': str(pack), 'script': 'Loader', 'start': 'HOST/run-a',
                                            'log_folder': str(pack)}, **params))


def shown(d):
    v = int(d.screenshot()[0, 0, 0])
    return next(k for k, c in COLOURS.items() if c == v)


def test_the_clock_is_the_wall_clock_until_a_sim_makes_it_virtual():
    started = time.time()
    sim_clock.sleep(0.05)
    assert time.time() - started >= 0.05
    sim_clock.make_virtual()
    before, wall = sim_clock.time(), time.time()
    sim_clock.sleep(600)
    assert sim_clock.time() - before >= 600
    assert time.time() - wall < 1


def test_plays_the_recorded_run_and_waits_at_its_next_input(pack):
    d = sim(pack)
    assert sim_clock.is_virtual()
    assert shown(d) == 'home0'
    sim_clock.sleep(10)
    # the run pressed a key at 1 s; what came after depended on it
    assert shown(d) == 'home0'


def test_an_input_the_run_made_continues_it(pack):
    d = sim(pack)
    d.key_press('home')
    sim_clock.sleep(2.5)                  # past the middle of 1 s .. 3 s
    assert shown(d) == 'home1'
    d.click(19, 29)                       # inside the box of the click at 4 s
    sim_clock.sleep(3)
    assert shown(d) == 'load0'
    sim_clock.sleep(30)
    assert shown(d) == 'city0'
    log = [json.loads(l) for l in open(pack / 'sim-log.jsonl')]
    assert [e.get('how') for e in log if e['event'] == 'input'] == ['continued', 'continued']


def test_a_click_nowhere_recorded_does_nothing_by_default_and_fails_on_request(pack):
    d = sim(pack)
    d.key_press('home')
    sim_clock.sleep(2.5)
    d.click(1, 1)
    assert d.counts['low evidence'] == 1
    assert shown(d) == 'home1'
    f = sim(pack, policy='fail')
    f.key_press('home')
    sim_clock.sleep(2.5)
    with pytest.raises(SimulatedDeviceError):
        f.click(1, 1)


def test_a_click_made_only_in_another_run_switches_to_it(pack):
    # run-b clicked the icon at 1 s on its home screen, with no key press first
    d = sim(pack, start='HOST/run-b')
    d.click(20, 30)
    sim_clock.sleep(1.5)
    assert shown(d) == 'load2'
    d2 = sim(pack, seed=0)
    d2.key_press('home')
    sim_clock.sleep(2.5)
    d2.click(21, 31)                      # in both boxes: the run's own click wins
    assert d2.counts['continued'] == 2


def test_held_on_a_screen_goes_on_as_a_visit_that_lasted_as_long(pack):
    # run-b's loading lasted 2 s .. 12 s with no input; run-a's 6 s .. 30 s
    # ended with a click. Held on run-b's last frame (the city) the device has
    # nowhere to go; held on loading it goes on as a long enough visit.
    d = sim(pack, start='HOST/run-b', hold_s=1)
    d.click(20, 30)
    sim_clock.sleep(1.5)
    assert shown(d) == 'load2'
    sim_clock.sleep(20)
    assert shown(d) == 'city2'            # run-b went on by itself


def sim_controller(pack):
    """A run's controller for --device sim:{pack}: script_manager's params, as a bare value for every slot."""
    from ScriptEngine.script_manager import sim_device_params
    value = 'sim:{}?start=HOST/run-a'.format(pack)
    params = sim_device_params(value, 'Loader', str(pack))
    return DeviceController({}, params, None, None, bindings={}, all_slots_value=value)


def test_the_controller_routes_every_slot_and_device_type_to_one_sim(pack):
    c = sim_controller(pack)
    sim = c.initialize_device('phone0')
    assert isinstance(sim, SimulatedDeviceManager)
    # Every slot, bound or not, the host, a deviceMap'd child slot and the v22 types: the one sim.
    for target in ('', 'device0', 'desktop0', 'phone3', 'tablet1', 'host', 'adb', 'python', 'kvm'):
        assert c.initialize_device(target) is sim, target
    c.push_slot_map({'phone0': 'phone2'})
    assert c.initialize_device('phone0') is sim
    c.pop_slot_map()
    assert c.get_device_attribute('phone0', 'width') == W
    assert c.device_key('phone0') == c.device_key('host') == 'sim'
    assert c.describe_target('phone0') == ('phone0', 'sim:' + str(pack))
    # No slot is left unbound: the run-start and child checks pass.
    assert c.check_bindings({'phone3': [], 'desktop1': ['the office PC']}) == ([], [])
    c.check_child_slots({'props': {'devices': [{'slot': 'phone1'}]}, 'actionRows': []}, 'Child')
    assert c.device_id_to_device_type('sim:ExampleGame/examplegame') == 'sim'


def test_sim_device_params_from_a_pack_folder_or_a_configured_sim(pack, monkeypatch):
    import ScriptEngine.script_manager as sm
    monkeypatch.setattr(sm, '_devices_config', lambda: {})
    params = sm.sim_device_params('sim:{}?seed=3&start=HOST/run-a'.format(pack), 'Loader', '/runs/1')
    assert params == {'seed': '3', 'start': 'HOST/run-a', 'deviceId': 'sim:' + str(pack), 'path': str(pack),
                      'script-engine-device-type': 'sim', 'script': 'Loader', 'log_folder': '/runs/1'}
    entry = {'type': 'sim', 'path': str(pack), 'seed': '5', 'script': 'Other'}
    monkeypatch.setattr(sm, '_devices_config', lambda: {'sim:ExampleGame/examplegame': entry})
    params = sm.sim_device_params('sim:ExampleGame/examplegame', 'Loader', '/runs/2')
    assert params == dict(entry, deviceId='sim:ExampleGame/examplegame', **{
        'script-engine-device-type': 'sim', 'log_folder': '/runs/2'})
    assert entry == {'type': 'sim', 'path': str(pack), 'seed': '5', 'script': 'Other'}


def test_no_pack_is_a_clear_error(tmp_path):
    with pytest.raises(SimulatedDeviceError, match='no sim pack'):
        SimulatedDeviceManager({}, {'path': str(tmp_path)})
