"""A parallel detect's log_objs leave out the images the main process sent.

The worker (DetectObjectHelper.handle_parallel_detect_object) replaces the
screenshot copy and the template dicts in log_objs with SENT_IMAGE, and sends
no log_objs at all below info. The main process puts its own copies back
(restore_sent_images) before writing the log images, which must come out the
same files, byte for byte, as when the worker pickled its own copies back.

The pool is stood in for by a pickle round trip, which is what it does to a
task's result.
"""
import os
import pickle
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import ScriptEngine.helpers.detect_object_helper as detect_object_helper_mod
import ScriptEngine.helpers.detect_scene_helper as detect_scene_helper_mod
import ScriptEngine.helpers.image_matcher as image_matcher_mod
import ScriptEngine.script_executor as script_executor_mod
import ScriptEngine.script_loader as script_loader_mod
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.helpers.detect_object_helper import SENT_IMAGE, DetectObjectHelper
from ScriptEngine.parallelized_script_executor import ParallelizedScriptExecutor
from ScriptEngine.script_executor import ScriptExecutor

HEIGHT, WIDTH = 240, 320


def screen():
    rng = np.random.default_rng(3)
    image = cv2.GaussianBlur(rng.integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8), (5, 5), 0)
    image[60:90, 100:140] = (30, 200, 240)
    image[70:80, 110:130] = (240, 20, 60)
    return image


def detect_action(group, detect_type='floatingObject', match_mode='bestMatch', threshold=0.9, capture=None):
    """A detect as script_loader makes it, with its input_obj filled in as
    ParallelizedScriptExecutor.start_processes does."""
    capture = screen() if capture is None else capture
    template = screen()[60:90, 100:140].copy()
    floating = {
        'img': template,
        'mask': np.full(template.shape, 255, dtype=np.uint8),
        'mask_single_channel': np.full(template.shape[:2], 255, dtype=np.uint8),
        'sourceScreenWidth': WIDTH,
        'sourceScreenHeight': HEIGHT,
    }
    script_loader_mod.set_output_mask(floating, '', False, False)
    scene_mask = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    scene_mask[60:90, 100:140] = 255
    fixed = {
        'img': cv2.bitwise_and(screen(), scene_mask),
        'mask': scene_mask,
        'mask_single_channel': np.uint8(cv2.cvtColor(scene_mask, cv2.COLOR_BGR2GRAY)),
        'sourceScreenWidth': WIDTH,
        'sourceScreenHeight': HEIGHT,
    }
    return {
        'actionName': 'detectObject',
        'actionGroup': group,
        'actionData': {
            'targetSystem': 'desktop',
            'detectActionType': detect_type,
            'matchMode': match_mode,
            'threshold': str(threshold),
            'detectorName': 'pixelDifference',
            'maskLocation': 'null',
            'useColor': True,
            'useImageRescaledToScreenOnly': False,
            'inputExpression': '',
            'maxMatches': 1,
            'outputVarName': 'match',
            'sceneLocation': [[100, 60]],
            'positiveExamples': [{'floatingObject': floating, 'fixedObject': fixed}],
        },
        'input_obj': {
            'screencap_im_bgr': capture,
            'screencap_mask': None,
            'match_point': (0, 0),
            'original_image': capture,
            'original_image_blurred': cv2.GaussianBlur(capture, (31, 31), 0),
            'original_height': HEIGHT,
            'original_width': WIDTH,
            'fixed_scale': False,
        },
    }


# floatingObject bestMatch: the template overlay and score map; fixedObject: the
# scene overlay; floatingObject firstMatch: a scene match whose overlay draws the
# floating template's mask.
CASES = [
    ('floatingObject', 'bestMatch', 0.9),
    ('floatingObject', 'bestMatch', 1.01),
    ('fixedObject', 'bestMatch', 0.9),
    ('floatingObject', 'firstMatch', 0.9),
    ('floatingObject', 'firstMatch', 1.01),
]


@pytest.fixture
def logger(configure_action, monkeypatch):
    for module in (detect_object_helper_mod, detect_scene_helper_mod, image_matcher_mod, script_executor_mod):
        monkeypatch.setattr(module, 'script_logger', configure_action.logger)
    return configure_action


def through_pool(result):
    return pickle.loads(pickle.dumps(result))


def run_both_paths(logger, tmp_path, monkeypatch, level, actions):
    """Log images of the same detects through the old path (the worker sends its
    own log_objs) and the new one (placeholders, restored on the main side), each
    into its own run folder. Returns {path: {counter: images}}."""
    written = {}
    for path in ('old', 'new'):
        folder = tmp_path / path
        folder.mkdir()
        monkeypatch.setattr(logger.logger, 'log_file_path', str(folder / 'stdout.txt'))
        for counter, action in enumerate(actions, start=1):
            logger(level, 'detectObject', counter)
            if path == 'old':
                result = through_pool(DetectObjectHelper.handle_detect_object(action))
            else:
                returned_action, matches, log_objs = through_pool(DetectObjectHelper.handle_parallel_detect_object(action))
                result = (returned_action, matches, DetectObjectHelper.restore_sent_images(log_objs, action))
            run_folder = str(folder) + '/'
            logger.logger.set_log_folder(run_folder)
            header = '{:05}-detectObject-{}'.format(counter, counter)
            logger.logger.set_log_header(header)
            logger.logger.set_log_path_prefix(run_folder + header + '-')
            DetectObjectHelper.create_detect_action_log_images(logger.logger, result[0], result[2])
        written[path] = folder
    return written


def png_arrays(folder):
    return {
        name: cv2.imread(os.path.join(folder, name), cv2.IMREAD_UNCHANGED)
        for name in sorted(os.listdir(folder)) if name.endswith('.png')
    }


@pytest.mark.parametrize('detect_type, match_mode, threshold', CASES)
@pytest.mark.parametrize('level', ['info', 'debug'])
def test_log_images_match_the_old_path(logger, tmp_path, monkeypatch, level, detect_type, match_mode, threshold):
    action = detect_action(1, detect_type, match_mode, threshold)
    written = run_both_paths(logger, tmp_path, monkeypatch, level, [action])

    old, new = png_arrays(written['old']), png_arrays(written['new'])
    assert old and list(old) == list(new)
    for name in old:
        assert old[name].shape == new[name].shape and np.array_equal(old[name], new[name]), name
    for name in old:
        with open(os.path.join(written['old'], name), 'rb') as old_file, open(os.path.join(written['new'], name), 'rb') as new_file:
            assert old_file.read() == new_file.read(), name


def test_detects_sharing_a_screenshot_still_write_one_capture_each(logger, tmp_path, monkeypatch):
    """The detects of one parallel group share one screenshot (and a looped
    action reuses its templates). Restoring copies them, so the log image store,
    which writes an array once per run, still writes each detect its own files."""
    capture = screen()
    actions = [detect_action(1, capture=capture), detect_action(3, capture=capture)]
    actions[1]['input_obj'] = actions[0]['input_obj']
    actions[1]['actionData']['positiveExamples'] = actions[0]['actionData']['positiveExamples']
    written = run_both_paths(logger, tmp_path, monkeypatch, 'debug', actions)

    old, new = png_arrays(written['old']), png_arrays(written['new'])
    assert list(old) == list(new)
    assert '00002-detectObject-2-capture.png' in new and '00002-detectObject-2-template.png' in new
    for name in old:
        assert np.array_equal(old[name], new[name]), name


@pytest.mark.parametrize('detect_type, match_mode, threshold', CASES)
def test_worker_log_objs_leave_out_what_it_was_sent(logger, detect_type, match_mode, threshold):
    logger('info', 'detectObject', 1)
    action = detect_action(1, detect_type, match_mode, threshold)
    _, full_matches, full = DetectObjectHelper.handle_detect_object(action)
    _, sent_matches, sent = DetectObjectHelper.handle_parallel_detect_object(action)

    assert sent['base'][0] is SENT_IMAGE and sent['base'][1] is SENT_IMAGE
    assert sent['base'][2] == full['base'][2]
    if full['fixedObject'] is not None:
        assert sent['fixedObject'][2] is SENT_IMAGE
        assert np.array_equal(sent['fixedObject'][1], full['fixedObject'][1])
    # The images the worker made itself still come back.
    assert (sent['floatingObject'] is None) == (full['floatingObject'] is None)

    # What log_objs add to the pickled result. The result's action and matches
    # hold the screenshot and templates already (a match's original_image is
    # the screenshot), and pickle stores each object once, so only the copies
    # count: today's 'base' screenshot copy, and the worker's own images.
    def added_bytes(matches, log_objs):
        return len(pickle.dumps((action, matches, log_objs))) - len(pickle.dumps((action, matches, None)))

    worker_made = 0
    if full['floatingObject'] is not None:
        worker_made += full['floatingObject'][1].nbytes
    if full['fixedObject'] is not None:
        worker_made += full['fixedObject'][1].nbytes
    assert added_bytes(full_matches, full) >= worker_made + action['input_obj']['screencap_im_bgr'].nbytes
    # On top of the worker's own images: flags, the point, the placeholders,
    # and a failed scene match, which is in log_objs but not in the result.
    assert added_bytes(sent_matches, sent) < worker_made + 16 * 1024


def test_sent_image_comes_back_as_the_same_placeholder():
    assert pickle.loads(pickle.dumps(SENT_IMAGE)) is SENT_IMAGE
    assert len(pickle.dumps(SENT_IMAGE)) < 100
    # The pool pickles the handler too.
    assert pickle.loads(pickle.dumps(DetectObjectHelper.handle_parallel_detect_object)) is \
        DetectObjectHelper.handle_parallel_detect_object


def test_restore_copies_the_screenshot(logger):
    """The overlay builder does not draw on 'base', but the log image store keys
    by array identity, and the main thread keeps using the screenshot."""
    logger('info', 'detectObject', 1)
    action = detect_action(1)
    _, _, sent = through_pool(DetectObjectHelper.handle_parallel_detect_object(action))
    restored = DetectObjectHelper.restore_sent_images(sent, action)

    shot, template, _ = restored['base']
    assert shot is not action['input_obj']['screencap_im_bgr']
    assert np.array_equal(shot, action['input_obj']['screencap_im_bgr'])
    sent_template = action['actionData']['positiveExamples'][0]['floatingObject']
    assert template['img'] is not sent_template['img'] and np.array_equal(template['img'], sent_template['img'])


def test_below_info_the_worker_sends_no_log_objs(logger):
    logger('error', 'detectObject', 1)
    action = detect_action(1)
    _, matches, log_objs = DetectObjectHelper.handle_parallel_detect_object(action)
    assert log_objs is None
    assert len(matches) == 1
    assert DetectObjectHelper.restore_sent_images(None, action) is None

    class NoImages:
        def submit(self, *args):
            pytest.fail('no log images below info')

    _, status, state, _, _ = DetectObjectHelper.handle_detect_action_result(
        NoImages(), (action, matches, log_objs), {}, {}, []
    )
    assert status == ScriptExecutionState.SUCCESS and state['match'] is matches[0]


def test_inline_detect_keeps_its_log_objs(logger):
    """A detect run on the main thread (not in the pool) is not changed."""
    logger('info', 'detectObject', 1)
    action = detect_action(1)
    _, _, log_objs = DetectObjectHelper.handle_detect_object(action)
    shot = log_objs['base'][0]
    assert isinstance(shot, np.ndarray) and shot is not action['input_obj']['screencap_im_bgr']
    assert log_objs['base'][1] is action['actionData']['positiveExamples'][0]['floatingObject']


class DoneFuture:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result

    def cancel(self):
        pass


def test_execute_action_restores_and_drops_the_sent_action(logger):
    """ScriptExecutor.execute_action takes a parallel detect's result: it pops
    the action it sent and restores log_objs from it before handling them."""
    logger('info', 'detectObject', 1)
    actions = [detect_action(1), detect_action(3)]
    parallel = ParallelizedScriptExecutor(device_controller=None, process_executor=None)
    for action in actions:
        action['script_logger'] = ('header', '/tmp/', 'info', logger.logger.get_action_log())
        parallel.processes[action['actionGroup']] = DoneFuture(
            through_pool(DetectObjectHelper.handle_parallel_detect_object(action))
        )
        parallel.sent_actions[action['actionGroup']] = action

    handled = []

    def handle_handle_action_result(result, status, state, context, run_queue):
        handled.append(result)
        return result[0], ScriptExecutionState.SUCCESS, state, context, run_queue, []

    fake_self = SimpleNamespace(
        parallelized_executor=parallel,
        log_action_details=lambda action: None,
        handle_handle_action_result=handle_handle_action_result,
        parse_update_queue=lambda update_queue: None,
        props={'script_name': 'script'},
        status=ScriptExecutionState.STARTING,
        state={},
        context={},
        run_queue=[],
    )

    ScriptExecutor.execute_action(fake_self, actions[0], {})

    (_, _, log_objs), = handled
    assert isinstance(log_objs['base'][0], np.ndarray)
    assert np.array_equal(log_objs['base'][0], actions[0]['input_obj']['screencap_im_bgr'])
    assert log_objs['base'][1]['img'].shape == (30, 40, 3)
    assert list(parallel.sent_actions) == [3]

    parallel.clear_processes()
    assert parallel.sent_actions == {}
