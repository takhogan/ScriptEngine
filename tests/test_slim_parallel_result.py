"""A parallel detect's worker returns its action without the screenshot and the
template images (input_obj, actionData): the main process still holds the
action it sent and rebuilds the full one from it. The result that crosses the
process pipe shrinks from ~20 MB to a few KB for a 1920 x 1080 detect, and the
action the main thread works with is the same as before."""
import pickle
import sys
from concurrent.futures import CancelledError, Future
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.custom_process_pool import CustomProcessPool
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper
from ScriptEngine.helpers.parallelized_script_executor_helper import (
    SENT_ONLY_ACTION_KEYS,
    ParallelizedScriptExecutorHelper,
    restore_parallel_result,
    slim_parallel_result,
)
from ScriptEngine.parallelized_script_executor import ParallelizedScriptExecutor
from ScriptEngine.script_executor import ScriptExecutor

H, W = 1080, 1920
SCRIPT_MODE = 'test'


@pytest.fixture
def log_folder(tmp_path):
    folder = str(tmp_path) + '/'
    script_logger = ScriptLogger.get_logger()
    script_logger.set_log_folder(folder)
    script_logger.set_log_file_path(folder + 'stdout.txt')
    script_logger.set_log_to_stdout(False)
    # error: no log images, so no io thread reads the result after the test.
    script_logger.set_log_level('error')
    return folder


def _screenshot(seed=0):
    return np.random.default_rng(seed).integers(0, 256, (H, W, 3), dtype=np.uint8)


def _template_obj(img):
    h, w = img.shape[:2]
    return {
        'img': img,
        'mask': np.full((h, w, 3), 255, dtype=np.uint8),
        'mask_single_channel': np.full((h, w), 255, dtype=np.uint8),
        'outputMask': np.full((h, w, 3), 255, dtype=np.uint8),
        'outputMask_single_channel': np.full((h, w), 255, dtype=np.uint8),
        'sourceScreenWidth': W,
        'sourceScreenHeight': H,
    }


def _detect_action(group, template, screen_for_scene):
    return {
        'actionName': 'detectObject',
        'actionGroup': group,
        'actionLabel': 'detect {}'.format(group),
        'childGroups': [],
        'actionRowRowIndex': 0,
        'actionRowActionIndex': group,
        'actionData': {
            'targetSystem': 'desktop',
            'inputExpression': None,
            'detectActionType': 'floatingObject',
            'matchMode': 'bestMatch',
            'detectorName': 'pixelDifference',
            'threshold': '0.95',
            'useColor': True,
            'useImageRescaledToScreenOnly': False,
            'maskLocation': 'null',
            'maxMatches': '1',
            'outputVarName': 'match{}'.format(group),
            'postActionDelay': '',
            'positiveExamples': [{
                'floatingObject': _template_obj(template),
                'fixedObject': _template_obj(screen_for_scene),
            }],
        },
    }


def _sent_action(group=3, matching=False):
    """The action as ParallelizedScriptExecutor.start_processes submits it:
    with its script_logger tuple and input_obj filled in."""
    screen = _screenshot()
    if matching:
        template = screen[400:480, 700:820].copy()
    else:
        template = np.random.default_rng(99).integers(0, 256, (80, 120, 3), dtype=np.uint8)
    action = _detect_action(group, template, _screenshot(1))
    script_logger = ScriptLogger.get_logger()
    action_log = ScriptLogger.configure_action_logger(action, group, None)
    action['script_logger'] = (
        script_logger.get_log_header(),
        script_logger.get_log_folder(),
        script_logger.get_log_level(),
        action_log,
    )
    action['input_obj'] = {
        'screencap_im_bgr': screen,
        'screencap_mask': None,
        'match_point': (0, 0),
        'original_height': H,
        'original_width': W,
        'original_image': screen,
        'original_image_blurred': screen[::-1].copy(),
        'fixed_scale': False,
    }
    return action


def _through_pipe(obj):
    return pickle.loads(pickle.dumps(obj))


def _worker(sent_action, slim):
    """What a pool worker returns for sent_action, after both pipe crossings."""
    worker_args = _through_pipe((sent_action, SCRIPT_MODE))
    if slim:
        helper = ParallelizedScriptExecutorHelper(DetectObjectHelper.handle_detect_object)
        result = helper.handle_parallel_action(worker_args)
    else:
        # Before this change the helper returned the handler's result as it was.
        ScriptLogger.configure_action_logger_from_strs(*worker_args[0]['script_logger'])
        result = DetectObjectHelper.handle_detect_object(*worker_args)
    return pickle.dumps(result)


def assert_same(a, b, path='result'):
    assert type(a) is type(b), path
    if isinstance(a, np.ndarray):
        assert a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b), path
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for key in a:
            assert_same(a[key], b[key], '{}[{!r}]'.format(path, key))
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            assert_same(x, y, '{}[{}]'.format(path, i))
    elif hasattr(a, '__dict__') and not isinstance(a, type):
        assert_same(vars(a), vars(b), path + '.__dict__')
    else:
        assert a == b, path


@pytest.mark.parametrize('matching', [False, True])
def test_the_worker_result_leaves_out_the_sent_arrays(log_folder, matching):
    sent = _sent_action(matching=matching)
    full = _worker(sent, slim=False)
    slim = _worker(sent, slim=True)

    slim_action = pickle.loads(slim)[0]
    assert not any(key in slim_action for key in SENT_ONLY_ACTION_KEYS)
    assert set(slim_action) == set(sent) - set(SENT_ONLY_ACTION_KEYS)
    # The worker's ActionLog comes back.
    assert isinstance(slim_action['script_logger'][3], ScriptActionLog)
    assert slim_action['script_logger'][3].id == sent['script_logger'][3].id

    assert len(pickle.dumps(slim_action)) < 64 * 1024
    # The result now costs what matches and log_objs cost on their own. Those
    # still hold arrays: log_objs a copy of the screenshot and the match
    # heatmap, a match its screenshot (ScreenPlanImage.original_image) and the
    # template's output mask. Pickle writes an object shared with the action
    # once, so the old result saved those, and the saving is the sent arrays
    # less what matches and log_objs point at.
    matches_and_log_objs = len(pickle.dumps(pickle.loads(slim)[1:]))
    assert len(slim) < matches_and_log_objs + 64 * 1024
    assert len(full) - len(slim) > 16 * 1024 * 1024


@pytest.mark.parametrize('matching', [False, True])
def test_the_main_side_rebuilds_the_old_full_result(log_folder, matching):
    sent = _sent_action(matching=matching)
    sent_before = dict(sent)
    old = pickle.loads(_worker(sent, slim=False))
    new = restore_parallel_result(sent, pickle.loads(_worker(sent, slim=True)))

    assert_same(old, new)
    assert len(new[1]) == (1 if matching else 0)
    # The arrays are the ones the main process sent, not copies of them.
    assert new[0]['input_obj'] is sent['input_obj']
    assert new[0]['actionData'] is sent['actionData']
    # The sent action is left as it was: the rebuilt one is a copy.
    assert new[0] is not sent
    assert sent.keys() == sent_before.keys()
    assert all(sent[key] is sent_before[key] for key in sent)


def test_results_without_the_action_pass_through():
    action = {'actionName': 'detectObject', 'input_obj': {}, 'actionData': {}}
    other = ({'actionName': 'detectObject', 'input_obj': {}}, [], None)
    assert slim_parallel_result(action, other) is other
    assert slim_parallel_result(action, None) is None
    assert slim_parallel_result(action, ()) == ()

    slim = slim_parallel_result(action, (action, [], None))
    assert restore_parallel_result(None, slim) is slim
    assert restore_parallel_result(action, None) is None
    assert restore_parallel_result(action, ('not an action', [])) == ('not an action', [])


class PicklingPool:
    """Runs a submitted task at once, with its arguments and its result
    pickled the way they cross a process pool's pipe."""

    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args):
        future = Future()
        try:
            result = pickle.loads(pickle.dumps(fn(*_through_pipe(args))))
        except Exception as e:
            future.set_exception(e)
        else:
            future.set_result(result)
        self.submitted.append(future)
        return future


class FakeDeviceController:
    def __init__(self, screen):
        self.screen = screen

    def get_device_action(self, target_system, action_name):
        assert action_name == 'screenshot'
        return lambda: self.screen


class FakeScriptExecutor:
    def __init__(self):
        self.context = {'script_counter': 0}
        self.state = {}
        self.parent_action_log = None

    def handle_action(self, action, lazy_eval=False):
        assert lazy_eval
        return DetectObjectHelper.handle_detect_object, (action, SCRIPT_MODE)


def _group(screen):
    return [
        _detect_action(group, screen[100:180, 200:320].copy() if group == 2 else
                       np.zeros((80, 120, 3), dtype=np.uint8), screen)
        for group in (1, 2, 3)
    ]


def _script_executor(parallelized_executor):
    """A ScriptExecutor with only what execute_action needs for a parallel detect."""
    executor = ScriptExecutor.__new__(ScriptExecutor)
    executor.parallelized_executor = parallelized_executor
    executor.props = {'script_name': 'SlimResultTest'}
    executor.status = ScriptExecutionState.STARTING
    executor.state = {}
    executor.context = {}
    executor.run_queue = []
    executor.io_executor = None
    executor.log_action_details = lambda action: None
    return executor


def test_start_processes_keeps_each_sent_action_until_its_result_is_used(log_folder):
    screen = _screenshot()
    pool = PicklingPool()
    parallelized = ParallelizedScriptExecutor(FakeDeviceController(screen), pool)
    actions = _group(screen)
    parallelized.start_processes(FakeScriptExecutor(), actions)

    assert set(parallelized.sent_actions) == {1, 2, 3}
    assert all(parallelized.sent_actions[a['actionGroup']] is a for a in actions)
    # What crossed back from each worker is the slim action.
    for future in pool.submitted:
        assert not any(key in future.result()[0] for key in SENT_ONLY_ACTION_KEYS)

    executor = _script_executor(parallelized)
    executor.execute_action(actions[0], {})
    assert executor.status == ScriptExecutionState.FAILURE
    assert set(parallelized.sent_actions) == {2, 3}

    executor.execute_action(actions[1], {})
    assert executor.status == ScriptExecutionState.SUCCESS
    assert executor.state['match2']['point'] == (200, 100)
    assert executor.state['match2']['original_image'].shape == (H, W, 3)
    assert set(parallelized.sent_actions) == {3}

    parallelized.clear_processes()
    assert parallelized.sent_actions == {}


def test_a_worker_exception_still_raises_and_drops_the_sent_action(log_folder):
    screen = _screenshot()
    actions = _group(screen)
    del actions[0]['actionData']['positiveExamples'][0]['floatingObject']['img']
    parallelized = ParallelizedScriptExecutor(FakeDeviceController(screen), PicklingPool())
    parallelized.start_processes(FakeScriptExecutor(), actions)

    with pytest.raises(KeyError, match="'img'"):
        _script_executor(parallelized).execute_action(actions[0], {})
    assert set(parallelized.sent_actions) == {2, 3}


def test_a_cancelled_future_still_raises_and_drops_the_sent_action(log_folder):
    action = _sent_action(group=4)
    future = Future()
    assert future.cancel()
    parallelized = ParallelizedScriptExecutor(None, None)
    parallelized.processes[4] = future
    parallelized.sent_actions[4] = action

    with pytest.raises(CancelledError):
        _script_executor(parallelized).execute_action(action, {})
    assert parallelized.sent_actions == {}


def test_through_a_real_process_pool(log_folder):
    screen = _screenshot()
    pool = CustomProcessPool(max_workers=1)
    try:
        parallelized = ParallelizedScriptExecutor(FakeDeviceController(screen), pool)
        actions = _group(screen)
        parallelized.start_processes(FakeScriptExecutor(), actions)
        executor = _script_executor(parallelized)
        executor.execute_action(actions[1], {})
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    assert executor.status == ScriptExecutionState.SUCCESS
    assert executor.state['match2']['point'] == (200, 100)
    assert set(parallelized.sent_actions) == {1, 3}
