"""Input on the Mac's own screen fails loudly when macOS denies the process
Accessibility. macOS then drops every posted click and key without an error,
so the engine used to log them as done. Now host_input asks AXIsProcessTrusted
once, the desktop driver refuses input with HostInputDeniedError, check_status
reports `input: denied`, and screenshots go on working. macOS itself is never
asked here: the check is mocked."""
import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine import device_controller as dc
from ScriptEngine.device_controller import DeviceController, process_input
from ScriptEngine.helpers import host_input
from ScriptEngine.helpers.host_input import HOST_INPUT_DENIED_CODE, HostInputDeniedError
from ScriptEngine.managers import adb_device_manager as adb_mod
from ScriptEngine.managers import desktop_device_manager as desktop_mod


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """The shared ScriptLogger needs a file, or its writer thread prints a
    traceback after the run (see test_ios_device_manager.py)."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('accessibility-logs') / 'test.txt'))
    return logger


@pytest.fixture(autouse=True)
def allowed(monkeypatch):
    """Input counts as allowed unless a test denies it: this very test run may
    have been started from an app without Accessibility."""
    monkeypatch.setattr(host_input, '_accessibility_trusted', True)


@pytest.fixture
def denied(monkeypatch, allowed):
    monkeypatch.setattr(host_input, '_accessibility_trusted', False)


class RecordingInput:
    """pyautogui / pydirectinput: records every call, sends nothing."""

    def __init__(self):
        self.calls = []

    def position(self):
        return (0, 0)

    def size(self):
        return (100, 100)

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append(name)


class FakeApplicationServices:
    def __init__(self, trusted):
        self.trusted = trusted
        self.asked = 0
        outer = self

        class AXIsProcessTrusted:
            argtypes = None
            restype = None

            def __call__(self):
                outer.asked += 1
                return outer.trusted
        self.AXIsProcessTrusted = AXIsProcessTrusted()


# ---- the check ---------------------------------------------------------------

def test_off_macos_input_is_always_allowed(monkeypatch):
    monkeypatch.setattr(host_input, 'IS_MAC', False)
    monkeypatch.setattr(host_input.ctypes.cdll, 'LoadLibrary', lambda path: pytest.fail('macOS only'))
    assert host_input.accessibility_trusted() is True


@pytest.mark.parametrize('trusted', [True, False])
def test_on_macos_it_asks_ax_is_process_trusted(monkeypatch, trusted):
    library = FakeApplicationServices(trusted)
    loaded = []
    monkeypatch.setattr(host_input, 'IS_MAC', True)
    monkeypatch.setattr(host_input.ctypes.cdll, 'LoadLibrary', lambda path: loaded.append(path) or library)
    assert host_input.accessibility_trusted() is trusted
    assert loaded == ['/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices']


def test_a_mac_that_cannot_be_asked_still_takes_input(monkeypatch):
    def no_library(path):
        raise OSError('image not found')
    monkeypatch.setattr(host_input, 'IS_MAC', True)
    monkeypatch.setattr(host_input.ctypes.cdll, 'LoadLibrary', no_library)
    monkeypatch.setattr(host_input, '_accessibility_trusted', host_input._UNCHECKED)
    assert host_input.accessibility_trusted() is None
    assert host_input.input_denied() is False


def test_it_asks_once_per_process(monkeypatch):
    library = FakeApplicationServices(False)
    monkeypatch.setattr(host_input, 'IS_MAC', True)
    monkeypatch.setattr(host_input.ctypes.cdll, 'LoadLibrary', lambda path: library)
    monkeypatch.setattr(host_input, '_accessibility_trusted', host_input._UNCHECKED)
    assert host_input.input_denied() and host_input.input_denied()
    assert library.asked == 1


def test_the_error_says_what_happened_and_both_fixes(denied):
    with pytest.raises(HostInputDeniedError) as raised:
        host_input.require_input()
    message = str(raised.value)
    assert 'macOS denied Accessibility to the app that launched the controller' in message
    assert 'Start the controller from a terminal app that has Accessibility' in message
    assert 'System Settings → Privacy & Security → Accessibility' in message
    assert raised.value.code == HOST_INPUT_DENIED_CODE


def test_input_status(monkeypatch):
    assert host_input.input_status() == {'input': 'ok'}
    monkeypatch.setattr(host_input, '_accessibility_trusted', False)
    assert host_input.input_status() == {
        'input': 'denied',
        'inputError': host_input.HOST_INPUT_DENIED_MESSAGE,
        'inputErrorCode': HOST_INPUT_DENIED_CODE,
    }


# ---- the desktop driver ------------------------------------------------------

def desktop_manager(monkeypatch, dummy_mode=False):
    recorder = RecordingInput()
    monkeypatch.setattr(desktop_mod, '_input_module', recorder)
    monkeypatch.setattr(desktop_mod.host_input, 'press_key', lambda key: recorder.calls.append('press') or True)
    manager = desktop_mod.DesktopDeviceManager.__new__(desktop_mod.DesktopDeviceManager)
    manager.dummy_mode = dummy_mode
    manager.scale_factor = 1
    manager.click_width = manager.click_height = 100
    manager.width = manager.height = 100
    manager.click_path_generator = SimpleNamespace(generate_click_path=lambda *args: ([1, 1], [1, 1]))
    manager.ensure_device_initialized = lambda: None
    manager._mss_thread_local = None
    frame = np.zeros((4, 4, 4), dtype=np.uint8)
    manager.sct = SimpleNamespace(monitors=[None, 'monitor'], grab=lambda monitor: frame)
    return manager, recorder


INPUTS = {
    'click': lambda m: m.click(10, 10, 'left'),
    'mouse_down': lambda m: m.mouse_down(10, 10),
    'mouse_up': lambda m: m.mouse_up(10, 10),
    'scroll': lambda m: m.scroll(10, 10, -3),
    'smooth_move': lambda m: m.smooth_move(0, 0, 10, 10),
    'click_and_drag': lambda m: m.click_and_drag(0, 0, 10, 10),
    'live_drag': lambda m: m.live_drag(0, 0, 10, 10, 100),
    'key_press': lambda m: m.key_press('a'),
    'key_down': lambda m: m.key_down('shift'),
    'key_up': lambda m: m.key_up('shift'),
    'hotkey': lambda m: m.hotkey(['ctrl', 'c']),
}


@pytest.mark.parametrize('name', sorted(INPUTS))
def test_every_input_fails_and_sends_nothing_when_denied(monkeypatch, denied, name):
    manager, recorder = desktop_manager(monkeypatch)
    with pytest.raises(HostInputDeniedError):
        INPUTS[name](manager)
    assert recorder.calls == []


@pytest.mark.parametrize('name', sorted(INPUTS))
def test_every_input_still_goes_out_when_allowed(monkeypatch, name):
    manager, recorder = desktop_manager(monkeypatch)
    monkeypatch.setattr(desktop_mod.time, 'sleep', lambda seconds: None)
    INPUTS[name](manager)
    assert recorder.calls


def test_screenshots_still_work_when_denied(monkeypatch, denied):
    manager, _ = desktop_manager(monkeypatch)
    assert manager.screenshot().shape == (4, 4, 3)
    assert manager.get_status() == 'online'
    assert manager.get_input_status()['input'] == 'denied'


def test_a_replay_in_dummy_mode_is_not_refused(monkeypatch, denied):
    manager, _ = desktop_manager(monkeypatch, dummy_mode=True)
    manager.click(10, 10, 'left')
    assert manager.get_input_status() == {'input': 'ok'}


def test_the_driver_warns_once_as_it_starts(monkeypatch, denied):
    logged = []
    monkeypatch.setattr(desktop_mod, 'script_logger', SimpleNamespace(
        log=lambda *args, **kwargs: logged.append((' '.join(str(a) for a in args), kwargs.get('level')))))
    monkeypatch.setattr(desktop_mod.mss, 'mss', lambda: None)
    monkeypatch.setattr(desktop_mod.DesktopDeviceManager, 'list_applications', lambda self: {})
    desktop_mod.DesktopDeviceManager({'width': None, 'height': None}, None)
    warnings = [line for line, level in logged if 'macOS denied Accessibility' in line]
    assert len(warnings) == 1 and ('Warning' in warnings[0])
    assert [level for line, level in logged if line == warnings[0]] == ['error']


def test_adb_keys_sent_to_the_host_keyboard_are_refused_too(monkeypatch, denied):
    recorder = RecordingInput()
    monkeypatch.setattr(adb_mod.host_input, 'input_module', recorder)
    manager = adb_mod.ADBDeviceManager.__new__(adb_mod.ADBDeviceManager)
    for send in (lambda: manager.key_up('a'), lambda: manager.key_down('a'), lambda: manager.hotkey(['ctrl', 'v'])):
        with pytest.raises(HostInputDeniedError):
            send()
    assert recorder.calls == []


# ---- the device controller: check_status and the editor's clicks -------------

def controller_with_host_screen(manager):
    controller = DeviceController.__new__(DeviceController)
    controller._initialize_device_lock = threading.Lock()
    controller.devices = {'host': manager}
    return controller


def test_check_status_says_the_host_screen_takes_no_input(monkeypatch, denied):
    manager, _ = desktop_manager(monkeypatch)
    answer = controller_with_host_screen(manager).parse_inputs(['r1', 'host', 'check_status'])
    assert answer == {
        'data': 'online',
        'input': 'denied',
        'inputError': host_input.HOST_INPUT_DENIED_MESSAGE,
        'inputErrorCode': HOST_INPUT_DENIED_CODE,
    }


def test_check_status_of_a_screen_that_takes_input(monkeypatch):
    manager, _ = desktop_manager(monkeypatch)
    assert controller_with_host_screen(manager).parse_inputs(['r1', 'host', 'check_status']) == {
        'data': 'online', 'input': 'ok'}


def test_a_device_without_an_input_status_answers_as_before(monkeypatch):
    device = SimpleNamespace(get_status=lambda: 'offline')
    controller = controller_with_host_screen(None)
    controller.devices = {'bluestacks:Pie64_1': device}
    assert controller.parse_inputs(['r1', 'bluestacks:Pie64_1', 'check_status']) == {'data': 'offline'}


def test_an_editor_click_answers_the_error_not_success(monkeypatch, denied, capsys):
    manager, recorder = desktop_manager(monkeypatch)
    controller = controller_with_host_screen(manager)
    responses = []
    monkeypatch.setattr(dc, 'device_locks', {})
    monkeypatch.setattr(dc, 'device_locks_lock', asyncio.Lock())
    monkeypatch.setattr(dc, 'response_lock', asyncio.Lock())
    real_log = dc.script_logger.log

    def capture(*args, **kwargs):
        if args and isinstance(args[0], str) and args[0].startswith('<--r1-->'):
            responses.append(json.loads(args[0][len('<--r1-->'):-len('<--r1-->')]))
        return real_log(*args, **kwargs)
    monkeypatch.setattr(dc.script_logger, 'log', capture)

    asyncio.run(process_input(controller, ['r1', 'host', 'click', '10', '10']))
    assert responses == [{'data': None, 'error': host_input.HOST_INPUT_DENIED_MESSAGE, 'code': HOST_INPUT_DENIED_CODE}]
    assert recorder.calls == []
