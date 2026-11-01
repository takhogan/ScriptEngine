"""A screenshot that cannot be taken fails the action that needed it, for up to
SCREENSHOT_FAILURE_LIMIT_SECONDS per device, and then ends the run.

These go through the real DeviceController and PiKVMDeviceManager, with only
pikvm_lib's PiKVM client replaced: a PiKVM whose target sends no HDMI signal is
the case that used to kill runs, and there is no way to produce one on demand.
The clock is the tracker's own, set by hand.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.screenshot_failures import (
    SCREENSHOT_FAILURE_LIMIT_SECONDS,
    ScreenshotFailedError,
    ScreenshotFailureLimitError,
    ScreenshotFailureTracker,
)
from ScriptEngine.device_controller import DeviceController
import ScriptEngine.helpers.device_action_interpreter as dai_mod
import ScriptEngine.managers.desktop_device_manager as desktop_mod
import ScriptEngine.managers.pikvm_device_manager as pikvm_mod
import ScriptEngine.parallelized_script_executor as pse_mod
import ScriptEngine.script_action_executor as sae_mod
import ScriptEngine.script_executor as se_mod
from ScriptEngine.parallelized_script_executor import ParallelizedScriptExecutor
from ScriptEngine.script_executor import ScriptExecutor


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """Give the shared ScriptLogger a file, as in test_ios_device_manager.py:
    DeviceController logs through it, and with no file its writer thread raises."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('screenshot-logs') / 'test.txt'))
    return logger


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakePiKVM:
    """pikvm_lib's PiKVM, with the no-video failure it raises after 30s."""

    def __init__(self, hostname, username, password):
        self.video = False
        self.snapshots = 0
        self.pressed = []
        self.clicks = []

    def get_streamer_image(self):
        self.snapshots += 1
        if not self.video:
            raise Exception('Failed to initialize streamer')
        return Image.new('RGB', (30, 20))

    def press(self, key):
        self.pressed.append(key)

    def send_mouse_move_event(self, x, y):
        pass

    def send_click(self, button):
        self.clicks.append(button)


@pytest.fixture
def kvm(device_executor, monkeypatch):
    """A run's DeviceController with a PiKVM attached whose target has no video."""
    executor, _, _, logger = device_executor
    monkeypatch.setattr(pikvm_mod, 'PiKVM', FakePiKVM)
    monkeypatch.setattr(dai_mod, 'script_logger', logger)
    controller = DeviceController(
        {'width': None, 'height': None, 'scriptMode': 'test', 'dir_path': '/tmp'},
        {'ip': '10.0.0.2', 'username': 'admin', 'passwordName': 'kvm-password'},
        None,
        SimpleNamespace(get_secret=lambda name: 'unused'),
    )
    executor.device_controller = controller
    device = controller.initialize_device('kvm')
    clock = FakeClock()
    controller.get_screenshot_failures('kvm').clock = clock
    return SimpleNamespace(executor=executor, controller=controller, pikvm=device.instance, clock=clock, logger=logger)


def detect_action(action_group=1):
    return {'actionName': 'detectObject', 'actionGroup': action_group, 'actionData': {'targetSystem': 'kvm', 'inputExpression': ''}}


def click_action():
    return {
        'actionName': 'mouseInteractionAction',
        'actionGroup': 2,
        'actionData': {
            'targetSystem': 'kvm',
            'sourceDetectTypeData': {'inputExpression': ''},
            'sourcePointList': [],
            'mouseActionType': 'click',
            'clickCount': 1,
            'betweenClickDelay': False,
            'randomVariableTypeData': {},
            'mouseButton': 'left',
        },
    }


def key_action():
    return {
        'actionName': 'keyboardAction',
        'actionGroup': 4,
        'actionData': {'targetSystem': 'kvm', 'keyboardActionType': 'keyPress', 'keyboardExpression': 'a'},
    }


@pytest.fixture
def no_detect_input(monkeypatch):
    """The detect has no input expression, so it needs a screenshot. What it does
    with one does not matter here: it reports SUCCESS whenever it gets one."""
    monkeypatch.setattr(sae_mod.DetectObjectHelper, 'get_detect_area', lambda *_: {'screencap_im_bgr': None})
    monkeypatch.setattr(sae_mod.DetectObjectHelper, 'handle_detect_object', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sae_mod.DetectObjectHelper,
        'handle_detect_action_result',
        lambda io, result, state, context, run_queue: (None, ScriptExecutionState.SUCCESS, state, context, run_queue),
    )


def test_limit_is_five_minutes():
    assert SCREENSHOT_FAILURE_LIMIT_SECONDS == 300


def test_detect_without_video_fails_instead_of_raising(kvm, no_detect_input, base_context, run_queue):
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)

    assert status == ScriptExecutionState.FAILURE
    summary = kvm.logger.action_log.summary
    assert 'could not take a screenshot of kvm' in summary
    assert 'no HDMI signal' in summary


def test_click_that_cannot_initialize_fails_instead_of_raising(kvm, base_context, run_queue):
    _, status, _, _, _, _ = kvm.executor.execute_action(click_action(), {}, base_context, run_queue)

    assert status == ScriptExecutionState.FAILURE
    assert kvm.pikvm.clicks == []
    assert 'no HDMI signal' in kvm.logger.action_log.summary


def test_keyboard_works_while_screenshots_fail(kvm, no_detect_input, base_context, run_queue):
    kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)

    _, status, _, _, _, _ = kvm.executor.execute_action(key_action(), {}, base_context, run_queue)

    assert status == ScriptExecutionState.SUCCESS
    assert kvm.pikvm.pressed == ['a']


def test_failing_for_five_minutes_ends_the_run(kvm, no_detect_input, base_context, run_queue):
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE

    kvm.clock.now += 299
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE

    kvm.clock.now += 1
    with pytest.raises(ScreenshotFailureLimitError, match='Screenshots of kvm have failed for 5 minutes'):
        kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)


def test_a_successful_screenshot_resets_the_timer(kvm, no_detect_input, base_context, run_queue):
    kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    kvm.clock.now += 290

    kvm.pikvm.video = True
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS

    kvm.pikvm.video = False
    kvm.clock.now += 10
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE

    kvm.clock.now += 299
    _, status, _, _, _, _ = kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.FAILURE


def test_initializing_an_initialized_device_does_not_reset_the_timer(kvm, no_detect_input, base_context, run_queue, monkeypatch):
    """ensure_device_initialized on a device that already knows its size takes no
    screenshot, so it succeeding says nothing about the screen."""
    monkeypatch.setattr(
        sae_mod.ClickActionHelper, 'get_point_choice',
        lambda *args, **kwargs: ((10, 11), (10, 11), [(10, 11)], [(10, 11)]),
    )
    kvm.pikvm.video = True
    kvm.executor.execute_action(click_action(), {}, base_context, run_queue)
    kvm.pikvm.video = False

    kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)
    kvm.clock.now += 200
    _, status, _, _, _, _ = kvm.executor.execute_action(click_action(), {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS

    kvm.clock.now += 100
    with pytest.raises(ScreenshotFailureLimitError):
        kvm.executor.execute_action(detect_action(), {}, base_context, run_queue)


def test_interactive_controller_has_no_limit():
    clock = FakeClock()
    tracker = ScreenshotFailureTracker('pikvm:10.0.0.2', limit_s=None, clock=clock)

    def fail():
        raise OSError('gone')

    for _ in range(3):
        with pytest.raises(ScreenshotFailedError):
            tracker.capture(fail)
        clock.now += 3600


class DispatchLogger:
    def __init__(self, action_log):
        self.action_log = action_log
        self.configured = []

    def log(self, *args, **kwargs):
        pass

    def configure_action_logger(self, action, script_counter, parent_action_log):
        return 'action-log-{}'.format(action['actionGroup'])

    def configure_action_logger_from_strs(self, *args):
        self.configured.append(args)

    def get_action_log(self):
        return self.action_log

    def get_log_header(self):
        return 'header'

    def get_log_folder(self):
        return '/tmp/'

    def get_log_level(self):
        return 'info'

    def set_log_header(self, header):
        pass


def test_parallel_detects_share_one_failed_screenshot(kvm, no_detect_input, monkeypatch):
    """firstMatch runs consecutive detects as one parallel group off a single
    screenshot. When that screenshot fails every detect in the group fails with
    it, and the device is asked once, not once per detect."""
    monkeypatch.setattr(pse_mod, 'script_logger', DispatchLogger(kvm.logger.action_log))
    parallel = ParallelizedScriptExecutor(kvm.controller, process_executor=None)
    script_executor = SimpleNamespace(
        parent_action_log=None,
        context={'script_counter': 0},
        state={},
        handle_action=lambda *args, **kwargs: pytest.fail('a detect without a screenshot was dispatched'),
    )
    actions = [detect_action(1), detect_action(3)]

    parallel.start_processes(script_executor, actions)

    assert kvm.pikvm.snapshots == 1
    assert parallel.get_process(1) is None and parallel.get_process(3) is None
    assert isinstance(parallel.get_screenshot_failure(1), ScreenshotFailedError)
    assert parallel.get_screenshot_failure(3) is parallel.get_screenshot_failure(1)

    # ScriptExecutor.execute_action then records each one as a FAILURE in the
    # action log that was created for it at dispatch.
    status_log = SimpleNamespace(status=None, summary=None)
    status_log.set_status = lambda status: setattr(status_log, 'status', status)
    status_log.set_summary = lambda summary: setattr(status_log, 'summary', summary)
    executor_logger = DispatchLogger(status_log)
    monkeypatch.setattr(se_mod, 'script_logger', executor_logger)
    monkeypatch.setattr(sae_mod, 'script_logger', executor_logger)
    fake_self = SimpleNamespace(
        parallelized_executor=parallel,
        script_action_executor=kvm.executor,
        log_action_details=lambda action: None,
        parse_update_queue=lambda update_queue: None,
        props={'script_name': 'script'},
        status=ScriptExecutionState.STARTING,
        state={},
        context={},
        run_queue=[],
    )

    ScriptExecutor.execute_action(fake_self, actions[1], {})

    assert fake_self.status == ScriptExecutionState.FAILURE
    assert status_log.status == 'FAILURE'
    assert 'no HDMI signal' in status_log.summary
    assert executor_logger.configured == [actions[1]['script_logger']]


def test_desktop_keyboard_does_not_need_the_screen(monkeypatch):
    """The desktop manager initializes (and so takes a screenshot) before every
    key; a screen it cannot capture must not stop the key."""
    sent = []
    monkeypatch.setattr(desktop_mod, '_input_module', SimpleNamespace(
        keyDown=lambda key: sent.append(('down', key)),
        keyUp=lambda key: sent.append(('up', key)),
        hotkey=lambda *keys: sent.append(('hotkey', keys)),
    ))
    monkeypatch.setattr(desktop_mod.pyautogui, 'press', lambda key: sent.append(('press', key)))
    monkeypatch.setattr(desktop_mod, 'script_logger', SimpleNamespace(log=lambda *args, **kwargs: None))
    desktop = desktop_mod.DesktopDeviceManager.__new__(desktop_mod.DesktopDeviceManager)
    desktop.dummy_mode = False

    def no_screen():
        raise OSError('screen capture not permitted')
    desktop.ensure_device_initialized = no_screen

    desktop.key_down('shift')
    desktop.key_up('shift')
    desktop.key_press('a')
    desktop.hotkey(['ctrl', 'c'])

    assert sent == [('down', 'shift'), ('up', 'shift'), ('press', 'a'), ('hotkey', ('ctrl', 'c'))]
