"""The editor's live view and live drag on the device controller: a device's
captures run beside its inputs (two lanes), and `click_and_drag ... live <ms>`
is a short drag instead of a humanized one. Nothing here touches a device: the
adb shell is replaced by a recorder, and the controller's request handler runs
against a fake DeviceController."""
import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine import device_controller as dc
from ScriptEngine.device_controller import DeviceController, device_lane, process_input
from ScriptEngine.helpers.live_input import (
    LIVE_DRAG_DEFAULT_MS, LIVE_DRAG_MAX_MS, LIVE_DRAG_MIN_MS, LIVE_DRAG_STEPS,
    live_drag_points, parse_live_drag_args
)
from ScriptEngine.managers import adb_device_manager as adb_mod
from ScriptEngine.managers.adb_device_manager import ADBDeviceManager


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """The shared ScriptLogger needs a file, or its writer thread prints a
    traceback after the run (see test_ios_device_manager.py)."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('live-input-logs') / 'test.txt'))
    return logger


# ---- the live drag's arguments and path --------------------------------------

def test_live_drag_args():
    assert parse_live_drag_args([]) is None
    assert parse_live_drag_args(['extra']) is None
    assert parse_live_drag_args(['live']) == LIVE_DRAG_DEFAULT_MS
    assert parse_live_drag_args(['live', '450']) == 450
    assert parse_live_drag_args(['live', '450.7']) == 450
    assert parse_live_drag_args(['live', '20']) == LIVE_DRAG_MIN_MS
    assert parse_live_drag_args(['live', '99999']) == LIVE_DRAG_MAX_MS
    assert parse_live_drag_args(['live', 'soon']) == LIVE_DRAG_DEFAULT_MS


def test_live_drag_path_is_short_and_ends_on_the_target():
    points = live_drag_points(100, 900, 300, 200)
    assert len(points) == LIVE_DRAG_STEPS
    assert points[-1] == (300, 200)
    xs = [x for x, _ in points]
    assert xs == sorted(xs)


# ---- dispatch -------------------------------------------------------------

class RecordingController:
    """Stands in for the device managers behind get_device_action."""

    def __init__(self):
        self.calls = []

    def get_device_action(self, device_type, action_type, device_params=None):
        return lambda *args: self.calls.append((action_type, args))


def dispatch(*inputs):
    controller = DeviceController.__new__(DeviceController)
    recorder = RecordingController()
    controller.get_device_action = recorder.get_device_action
    assert DeviceController.parse_inputs(controller, ['req', 'bluestacks:Pie64_1', *inputs]) == {'data': 'success'}
    return recorder.calls


def test_a_drag_without_live_is_the_script_drag():
    assert dispatch('click_and_drag', '586', '962', '333', '828.6') == [('click_and_drag', (586, 962, 333, 828))]


def test_live_makes_it_a_live_drag_with_its_duration():
    assert dispatch('click_and_drag', '586', '962', '333', '828', 'live', '450') == [('live_drag', (586, 962, 333, 828, 450))]


def test_lanes():
    assert device_lane('screen_capture') == 'capture'
    assert device_lane('check_status') == 'capture'
    for action in ['click', 'click_and_drag', 'send_keys', 'list_applications', 'start_application']:
        assert device_lane(action) == 'input'


# ---- the two lanes ----------------------------------------------------------

class SlowController:
    """parse_inputs as the real one would time it: an input takes `input_s`,
    a capture `capture_s`; each call's start and end are recorded."""

    def __init__(self, input_s=0.4, capture_s=0.05):
        self.input_s = input_s
        self.capture_s = capture_s
        self.spans = {}

    def parse_inputs(self, inputs):
        start = time.monotonic()
        time.sleep(self.capture_s if inputs[2] == 'screen_capture' else self.input_s)
        self.spans[inputs[0]] = (start, time.monotonic())
        return {'data': 'success'}


@pytest.fixture
def fresh_lanes(monkeypatch):
    monkeypatch.setattr(dc, 'device_locks', {})
    monkeypatch.setattr(dc, 'device_locks_lock', asyncio.Lock())
    monkeypatch.setattr(dc, 'response_lock', asyncio.Lock())


def run_requests(controller, requests, gap_s=0.05):
    async def go():
        tasks = []
        for request in requests:
            tasks.append(asyncio.create_task(process_input(controller, request)))
            await asyncio.sleep(gap_s)
        await asyncio.gather(*tasks)
    asyncio.run(go())


def test_a_capture_is_not_held_up_by_a_drag_on_the_same_device(fresh_lanes):
    controller = SlowController()
    run_requests(controller, [
        ['drag', 'bluestacks:Pie64_1', 'click_and_drag', '1', '2', '3', '4'],
        ['frame', 'bluestacks:Pie64_1', 'screen_capture'],
    ])
    drag_start, drag_end = controller.spans['drag']
    frame_start, frame_end = controller.spans['frame']
    assert frame_end < drag_end, 'the frame came back while the drag was still running'


def test_two_inputs_on_one_device_still_take_turns(fresh_lanes):
    controller = SlowController(input_s=0.2)
    run_requests(controller, [
        ['first', 'bluestacks:Pie64_1', 'click', '1', '2'],
        ['second', 'bluestacks:Pie64_1', 'click_and_drag', '1', '2', '3', '4'],
    ], gap_s=0.02)
    assert controller.spans['second'][0] >= controller.spans['first'][1]


def test_two_captures_on_one_device_still_take_turns(fresh_lanes):
    controller = SlowController(capture_s=0.2)
    run_requests(controller, [
        ['first', 'bluestacks:Pie64_1', 'screen_capture'],
        ['second', 'bluestacks:Pie64_1', 'screen_capture'],
    ], gap_s=0.02)
    assert controller.spans['second'][0] >= controller.spans['first'][1]


# ---- ADB --------------------------------------------------------------------

def adb_manager(emulator_type='bluestacks', touch_slot_protocol=True):
    """An ADBDeviceManager with a known screen and touch device, and no adb."""
    manager = ADBDeviceManager.__new__(ADBDeviceManager)
    manager.emulator_type = emulator_type
    manager.width, manager.height = 1080, 1920
    manager.xmax, manager.ymax = 32767, 32767
    manager.touch_slot_protocol = touch_slot_protocol
    manager.touch_is_down = False
    manager.touch_has_btn_touch = True
    manager.event_counter = 0
    manager.dummy_mode = False
    manager.adb_path = 'adb'
    manager.full_ip = '127.0.0.1:5555'
    manager.sendevent_command = 'sendevent /dev/input/event5 {} {} {};'
    manager.commands = {
        "x_command_func": manager.x_command_func,
        "y_command_func": manager.y_command_func,
        "action_terminate_command": manager.sendevent_command.format(0, 0, 0),
        "tracking_id_mouseup": manager.sendevent_command.format(3, int('39', 16), '-1'),
        "syn_mt_report": manager.sendevent_command.format(0, 2, 0),
        "btn_touch_down": manager.sendevent_command.format(1, int('14a', 16), 1),
        "btn_touch_up": manager.sendevent_command.format(1, int('14a', 16), 0),
    }
    manager.device_init_lock = threading.RLock()
    manager._input_activity_condition = threading.Condition()
    manager._inputs_running = 0
    manager.ensure_device_initialized = lambda reinitialize=False: None
    return manager


@pytest.mark.parametrize('slot_protocol', [True, False])
def test_a_bluestacks_live_drag_is_a_few_dozen_sendevents(slot_protocol):
    manager = adb_manager(touch_slot_protocol=slot_protocol)
    commands = manager.live_drag_commands(586, 962, 333, 828, 450)
    script = ''.join(commands)
    assert script.count('sendevent') <= 5 * (LIVE_DRAG_STEPS + 2)
    assert script.count('sleep 0.045;') == LIVE_DRAG_STEPS
    if slot_protocol:
        assert script.endswith(manager.commands['action_terminate_command'])
        assert manager.commands['btn_touch_up'] in script
        assert manager.touch_is_down is False
    # Ends on the target, mapped into the touch device's range.
    assert manager.x_command_func(int(333 / 1080 * 32767)) in script
    assert manager.y_command_func(int(828 / 1920 * 32767)) in script


def test_a_fast_live_drag_has_no_sleeps():
    commands = adb_manager().live_drag_commands(586, 962, 333, 828, 100)
    assert not any(command.startswith('sleep') for command in commands)


def test_an_avd_live_drag_is_one_input_swipe_with_the_duration(monkeypatch):
    manager = adb_manager(emulator_type='avd')
    sent = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            sent.append(args)

        def communicate(self, data, timeout=None):
            sent.append(data.decode())
            # A reinitialize now has to wait for this input.
            assert manager._inputs_running == 1
            return b'', b''

    monkeypatch.setattr(adb_mod.subprocess, 'Popen', FakePopen)
    manager.live_drag(586, 962, 333, 828, 450)
    assert sent == [['adb', '-s', '127.0.0.1:5555', 'shell'], 'input swipe 586 962 333 828 450;']
    assert manager._inputs_running == 0


def test_a_reinitialize_waits_for_the_input_in_progress():
    manager = adb_manager()
    reinitialized_at = []
    manager._initialize_device_unlocked = lambda reinitialize=False: reinitialized_at.append(time.monotonic())
    input_done = []

    def slow_input():
        with manager._input_activity():
            time.sleep(0.3)
            input_done.append(time.monotonic())

    worker = threading.Thread(target=slow_input)
    worker.start()
    time.sleep(0.05)
    ADBDeviceManager._initialize_device(manager, reinitialize=True)
    worker.join()
    assert reinitialized_at[0] >= input_done[0]


def test_a_first_initialize_does_not_wait_for_inputs():
    manager = adb_manager()
    initialized_at = []
    manager._initialize_device_unlocked = lambda reinitialize=False: initialized_at.append(time.monotonic())
    release = threading.Event()

    def held_input():
        with manager._input_activity():
            release.wait(2)

    worker = threading.Thread(target=held_input)
    worker.start()
    time.sleep(0.05)
    started = time.monotonic()
    ADBDeviceManager._initialize_device(manager, reinitialize=False)
    release.set()
    worker.join()
    assert initialized_at[0] - started < 0.2


# ---- desktop and PiKVM --------------------------------------------------------

class RecordingInput:
    """pyautogui / pydirectinput, or a PiKVM instance: records every call."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


def test_a_desktop_live_drag_presses_moves_straight_and_releases(monkeypatch):
    from ScriptEngine.managers import desktop_device_manager as desktop_mod
    from ScriptEngine.managers.desktop_device_manager import DesktopDeviceManager

    recorder = RecordingInput()
    monkeypatch.setattr(desktop_mod, '_input_module', recorder)
    monkeypatch.setattr(desktop_mod.time, 'sleep', lambda seconds: None)
    manager = DesktopDeviceManager.__new__(DesktopDeviceManager)
    manager.dummy_mode = False
    manager.scale_factor = 0.5
    manager.ensure_device_initialized = lambda: None
    manager.smooth_move = lambda *args, **kwargs: pytest.fail('a live drag takes no humanized path')

    manager.live_drag(200, 400, 1000, 400, 300)
    names = [name for name, _, _ in recorder.calls]
    assert names[0:2] == ['moveTo', 'mouseDown'] and names[-1] == 'mouseUp'
    moves = [args for name, args, _ in recorder.calls[2:-1]]
    assert len(moves) == LIVE_DRAG_STEPS
    assert moves[-1][:2] == (500, 200), 'scaled from screenshot pixels to input points'
    assert all(kwargs.get('_pause') is False for _, _, kwargs in recorder.calls)


def test_a_pikvm_live_drag_is_down_a_few_moves_up(monkeypatch):
    from ScriptEngine.managers import pikvm_device_manager as pikvm_mod
    from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager

    monkeypatch.setattr(pikvm_mod.time, 'sleep', lambda seconds: None)
    manager = PiKVMDeviceManager.__new__(PiKVMDeviceManager)
    manager.dummy_mode = False
    manager.instance = RecordingInput()
    manager.live_drag(10, 10, 110, 60, 300)
    calls = [(name, args) for name, args, _ in manager.instance.calls]
    assert calls[0:2] == [('send_mouse_move_event', (10, 10)), ('send_mouse_event', ('left', 'true'))]
    assert calls[-2:] == [('send_mouse_move_event', (110, 60)), ('send_mouse_event', ('left', 'false'))]
    assert sum(1 for name, _ in calls if name == 'send_mouse_move_event') == LIVE_DRAG_STEPS + 2
