"""Learned multi-scale template matching (docs/multiscale-template-matching.md):
a capture of another size than the template's source screen is searched at
other template scales, and what works is learned per device."""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers import scale_memory
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper, script_logger
from ScriptEngine.helpers.scale_memory import ScaleMemory

SOURCE_W, SOURCE_H = 480, 360
TOP, LEFT, TH, TW = 120, 160, 48, 96


class _ActionLog:
    def __init__(self):
        self.result = {}

    def update_result(self, result):
        for key, value in result.items():
            if isinstance(value, dict):
                self.result.setdefault(key, {}).update(value)
            else:
                self.result[key] = value


@pytest.fixture
def action_log(monkeypatch):
    log = _ActionLog()
    script_logger.set_log_file_path(os.devnull)
    script_logger.set_log_to_stdout(False)
    monkeypatch.setattr(script_logger, 'get_action_log', lambda: log)
    return log


@pytest.fixture(autouse=True)
def scratch_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(scale_memory, 'engine_assets_path', lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.delenv('SCREENPLAN_SCALE_MATCH', raising=False)
    ScaleMemory.reset()
    yield
    ScaleMemory.reset()


def _recorded():
    """A smooth textured screen with a distinct element (the template) on it."""
    rng = np.random.default_rng(11)
    screen = cv2.GaussianBlur(rng.integers(0, 256, (SOURCE_H, SOURCE_W, 3), dtype=np.uint8), (9, 9), 0)
    element = np.zeros((TH, TW, 3), dtype=np.uint8)
    element[:, :] = (40, 40, 200)
    cv2.rectangle(element, (6, 6), (TW - 7, TH - 7), (240, 240, 240), 3)
    cv2.putText(element, 'OK', (28, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    screen[TOP:TOP + TH, LEFT:LEFT + TW] = element
    return screen


def _screen(size, element_scale=None):
    """The recorded screen as a device of `size` shows it: the whole picture
    resized (a KVM, a scaled screenshot)."""
    recorded = _recorded()
    if size == (SOURCE_W, SOURCE_H):
        return recorded
    interpolation = cv2.INTER_AREA if size[0] * size[1] < SOURCE_W * SOURCE_H else cv2.INTER_CUBIC
    return cv2.resize(recorded, size, interpolation=interpolation)


def _blank(size):
    rng = np.random.default_rng(5)
    return cv2.GaussianBlur(rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8), (9, 9), 0)


def _action(screen, device='bench:test', threshold=0.9, output_mask=None, fixed_scale=False, original=None):
    recorded = _recorded()
    template = recorded[TOP:TOP + TH, LEFT:LEFT + TW].copy()
    out_mask = output_mask if output_mask is not None else np.full((TH, TW), 255, np.uint8)
    floating = {
        'img': template, 'mask': np.full((TH, TW, 3), 255, np.uint8),
        'mask_single_channel': np.full((TH, TW), 255, np.uint8),
        'outputMask': cv2.cvtColor(out_mask, cv2.COLOR_GRAY2BGR),
        'outputMask_single_channel': out_mask,
        'sourceScreenHeight': SOURCE_H, 'sourceScreenWidth': SOURCE_W,
    }
    original = original if original is not None else screen
    action = {
        'actionName': 'detectObject', 'actionGroup': 1,
        'input_obj': {
            'screencap_im_bgr': screen, 'screencap_mask': None, 'match_point': (0, 0),
            'original_image': original, 'original_image_blurred': original,
            'original_height': original.shape[0], 'original_width': original.shape[1], 'fixed_scale': fixed_scale,
        },
        'actionData': {
            'detectActionType': 'floatingObject', 'matchMode': 'bestMatch', 'threshold': threshold,
            'skipDetection': False, 'outputVarName': 'match', 'detectorName': 'pixelDifference',
            'useColor': True, 'useImageRescaledToScreenOnly': False, 'maskLocation': 'null',
            'sceneLocation': [[LEFT, TOP]], 'inputExpression': '', 'maxMatches': 1,
            'positiveExamples': [{'floatingObject': floating, 'fixedObject': None}],
        },
    }
    if device is not None:
        action['scale_device'] = device
    return action


def _detect(action):
    _, matches, log_objs = DetectObjectHelper.handle_detect_object(action)
    return matches, log_objs


# -- the learning state ------------------------------------------------------

def test_a_set_is_learned_once_three_observations_agree():
    pair = scale_memory.new_pair()
    scale_memory.observe(pair, 0.6667, 0.6667)
    scale_memory.observe(pair, 0.67, 0.665)        # the same scale, within 2 %
    assert pair['learned'] == []
    scale_memory.observe(pair, 0.6667, 0.6667)
    assert len(pair['learned']) == 1
    assert pair['learned'][0][0] == pytest.approx(0.668, abs=0.002)


def test_scattered_observations_learn_nothing():
    pair = scale_memory.new_pair()
    for s in (0.5, 0.8, 1.25, 1.6, 2.0):
        scale_memory.observe(pair, s, s)
    assert pair['learned'] == []


def test_two_scales_can_be_learned_together():
    pair = scale_memory.new_pair()
    for _ in range(4):
        scale_memory.observe(pair, 1.0, 1.0)
        scale_memory.observe(pair, 0.6667, 0.6667)
    assert sorted(map(tuple, pair['learned'])) == [(0.6667, 0.6667), (1.0, 1.0)]


def test_observations_age():
    pair = scale_memory.new_pair()
    for _ in range(61):
        scale_memory.observe(pair, 1.0, 1.0)
    assert sum(o['n'] for o in pair['observations']) <= scale_memory.AGE_ABOVE


def test_explorations_outside_the_set_send_the_pair_back_to_searching():
    pair = scale_memory.new_pair()
    for _ in range(5):
        scale_memory.observe(pair, 1.0, 1.0)
    assert pair['learned'] == [[1.0, 1.0]]
    scale_memory.outside_found(pair, 0.8, 0.8)
    assert pair['learned'] == [[1.0, 1.0]] and pair['outside'] == 1
    scale_memory.learned_hit(pair, 1.0, 1.0)
    assert pair['outside'] == 0
    scale_memory.outside_found(pair, 0.8, 0.8)
    scale_memory.outside_found(pair, 0.8, 0.8)
    # Only what was seen outside the old set is kept: its 3 observations of 0.8.
    assert [(o['sx'], o['n']) for o in pair['observations']] == [(0.8, 3.0)]
    assert pair['learned'] == [[0.8, 0.8]]


def test_two_processes_writing_the_same_device_file_keep_both_changes(tmp_path):
    path = str(tmp_path / 'device.json')
    a, b = ScaleMemory(path), ScaleMemory(path)
    a.record('observe', 'k', 1.0, 1.0)
    b.record('observe', 'k', 1.0, 1.0)      # b has not re-read a's write before it changes
    a.record('observe', 'k', 1.0, 1.0)
    with open(path) as f:
        document = json.load(f)
    assert document['pairs']['k']['observations'][0]['n'] == 3.0
    assert document['pairs']['k']['learned'] == [[1.0, 1.0]]
    assert ScaleMemory(path).learned('k') == [(1.0, 1.0)]


def test_hits_on_a_learned_scale_are_written_in_batches(tmp_path):
    path = str(tmp_path / 'device.json')
    memory = ScaleMemory(path)
    memory.record('learned_hit', 'k', 1.0, 1.0, urgent=False)
    assert memory.pending and not os.path.exists(path)
    memory.flush()
    assert not memory.pending and os.path.exists(path)


def test_a_still_image_learns_in_memory_only():
    assert ScaleMemory.for_device('file:/tmp/x.png').path is None
    assert ScaleMemory.for_device('file').path is None
    assert ScaleMemory.for_device('pikvm:02-host').path.endswith(os.path.join('deviceScales', 'pikvm_02-host.json'))


def test_learned_scales_live_under_engine_assets(monkeypatch, tmp_path):
    from ScriptEngine.helpers import data_persistence_helper
    monkeypatch.setattr(data_persistence_helper, 'data_path', lambda *parts: str(tmp_path.joinpath(*parts)))
    path = data_persistence_helper.engine_assets_path('deviceScales', 'host.json')
    assert path == str(tmp_path / 'engineAssets' / 'deviceScales' / 'host.json')


# -- detection ---------------------------------------------------------------

def test_same_size_matches_as_before(action_log):
    matches, _ = _detect(_action(_screen((SOURCE_W, SOURCE_H))))
    assert matches and tuple(map(int, matches[0]['point'])) == (LEFT, TOP)
    assert action_log.result['template']['scale_mode'] == 'same-size'
    assert (matches[0]['width'], matches[0]['height']) == (TW, TH)


@pytest.mark.parametrize('size', [(320, 240), (400, 300), (720, 540), (320, 360), (480, 270)])
def test_a_resized_screen_is_found_at_the_right_place_and_size(action_log, size):
    rx, ry = size[0] / SOURCE_W, size[1] / SOURCE_H
    matches, log_objs = _detect(_action(_screen(size), device=None))
    assert matches, action_log.result['template']
    x, y = matches[0]['point']
    assert abs(x - LEFT * rx) <= 2 and abs(y - TOP * ry) <= 2
    assert abs(matches[0]['width'] - TW * rx) <= 2 and abs(matches[0]['height'] - TH * ry) <= 2
    # The click area is the template's output mask at the matched size.
    assert matches[0]['output_mask'].shape == (matches[0]['height'], matches[0]['width'])
    assert matches[0]['matched_area'].shape[:2] == matches[0]['output_mask'].shape
    sx, sy = action_log.result['template']['scale']
    assert abs(sx - rx) < 0.04 and abs(sy - ry) < 0.04
    assert log_objs['floatingObject'][2] == pytest.approx((sx, sy), abs=1e-3)


def test_the_click_area_follows_the_scale(action_log):
    """A mask that keeps only the right half of the template keeps the right
    half of the matched element."""
    half = np.zeros((TH, TW), np.uint8)
    half[:, TW // 2:] = 255
    matches, _ = _detect(_action(_screen((320, 240)), device=None, output_mask=half))
    ys, xs = np.where(matches[0]['output_mask'] > 1)
    assert xs.min() == pytest.approx(matches[0]['width'] / 2, abs=1)
    assert xs.max() == matches[0]['width'] - 1


def test_a_device_learns_its_scale_then_stops_searching(action_log):
    size = (320, 240)
    modes = []
    for _ in range(4):
        matches, _ = _detect(_action(_screen(size)))
        assert matches
        modes.append(action_log.result['template']['scale_mode'])
    assert modes[:3] == ['searching'] * 3 and modes[3] == 'learned'
    # A miss now tries only the learned scale.
    matches, _ = _detect(_action(_blank(size)))
    assert not matches
    assert action_log.result['template']['scale_mode'] == 'learned'
    assert action_log.result['template']['scales_tried'] <= 1 + 3   # with its whole-pixel neighbours
    # Persisted for later runs.
    ScaleMemory.reset()
    assert ScaleMemory.for_device('bench:test').learned('480x360->320x240')


def test_explorations_back_off():
    explored = [n for n in range(1, 200) if scale_memory.should_explore(n)]
    assert explored == [8, 16, 32, 64, 128, 192]


def test_a_learned_pair_explores_on_the_eighth_miss_in_a_row(action_log):
    size = (320, 240)
    for _ in range(3):
        _detect(_action(_screen(size)))
    modes = []
    for _ in range(scale_memory.EXPLORE_EVERY):
        _detect(_action(_blank(size)))
        modes.append(action_log.result['template']['scale_mode'])
    assert modes[-1] == 'exploring' and set(modes[:-1]) == {'learned'}


def test_learned_scales_are_per_device(action_log):
    for _ in range(3):
        _detect(_action(_screen((320, 240)), device='kvm:a'))
    _detect(_action(_screen((320, 240)), device='kvm:b'))
    assert action_log.result['template']['scale_mode'] == 'searching'


def _changed(size):
    """The element at its source size on a capture of `size`: the device's
    display scaling changed (it no longer shrinks the picture)."""
    changed = _blank(size)
    changed[60:60 + TH, 100:100 + TW] = _recorded()[TOP:TOP + TH, LEFT:LEFT + TW]
    return changed


def test_a_changed_device_relearns(action_log):
    """Learned well at 2/3; the device then shows elements at full size.
    Explorations find them outside the set; RELEARN_AFTER of them send the
    pair back to searching, which then learns the new scale."""
    size = (320, 240)
    for _ in range(10):
        _detect(_action(_screen(size)))
    assert ScaleMemory.for_device('bench:test').learned('480x360->320x240') == [(0.6667, 0.6667)]
    found = []
    for _ in range(16):     # explorations on the 8th and 16th miss
        matches, _ = _detect(_action(_changed(size)))
        found.append(bool(matches))
    # Only the explorations found it, and then the pair searches again.
    assert sum(found) == scale_memory.RELEARN_AFTER
    assert ScaleMemory.for_device('bench:test').learned('480x360->320x240') == []
    for _ in range(3):
        matches, _ = _detect(_action(_changed(size)))
        assert matches and tuple(map(int, matches[0]['point'])) == (100, 60)
    assert action_log.result['template']['scale_mode'] == 'learned'
    assert ScaleMemory.for_device('bench:test').learned('480x360->320x240') == [(1.0, 1.0)]


def test_a_device_newly_seen_at_a_second_scale_learns_both(action_log):
    """Barely learned at 2/3, a second scale found by exploration joins the set."""
    size = (320, 240)
    for _ in range(3):
        _detect(_action(_screen(size)))
    for _ in range(16):
        _detect(_action(_changed(size)))
    assert sorted(ScaleMemory.for_device('bench:test').learned('480x360->320x240')) == [(0.6667, 0.6667), (1.0, 1.0)]
    matches, _ = _detect(_action(_changed(size)))
    assert matches and action_log.result['template']['scale_mode'] == 'learned'


def test_legacy_mode_restores_the_stretched_capture(action_log, monkeypatch):
    monkeypatch.setenv('SCREENPLAN_SCALE_MATCH', 'legacy')
    matches, _ = _detect(_action(_screen((320, 240))))
    assert action_log.result['template']['scale_mode'] == 'legacy'
    assert action_log.result['template']['resized'] is True
    assert matches and (matches[0]['width'], matches[0]['height']) == (TW, TH)


def test_a_nested_detect_uses_the_capture_size_of_its_screenshot(action_log):
    """The input is an earlier match's area (fixed_scale): its own size says
    nothing; the screenshot it came from is 320x240."""
    full = _screen((320, 240))
    area = full[60:140, 80:220]
    action = _action(area, device=None, fixed_scale=True, original=full)
    matches, _ = _detect(action)
    assert matches
    assert action_log.result['template']['scale_mode'] == 'searching'
    x, y = matches[0]['point']
    assert abs(x - (LEFT * 2 / 3 - 80)) <= 2 and abs(y - (TOP * 2 / 3 - 60)) <= 2


def test_a_searching_pair_backs_off_its_searches_on_misses(action_log):
    """Nothing learned and nothing found: the first 4 misses search, then the 8th."""
    searched = []
    for _ in range(8):
        _detect(_action(_blank((320, 240))))
        searched.append(action_log.result['template']['searched'])
    assert searched == [True] * 4 + [False] * 3 + [True]


def test_a_searching_pair_tries_its_observed_scale_before_searching(action_log):
    _detect(_action(_screen((320, 240))))           # one observation of 2/3
    for _ in range(4):
        _detect(_action(_blank((320, 240))))        # use up the searches
    matches, _ = _detect(_action(_screen((320, 240))))
    assert matches and action_log.result['template']['scale_mode'] == 'searching'
    assert not action_log.result['template']['searched']


def test_high_compatibility_option_reaches_the_matcher(action_log, monkeypatch):
    from ScriptEngine.helpers.image_matcher import ImageMatcher, SCALE_MATCH_ENV
    monkeypatch.delenv(SCALE_MATCH_ENV, raising=False)
    assert ImageMatcher.scale_match_mode() == 'learned'          # on by default
    ImageMatcher.set_high_compatibility(False)
    assert os.environ[SCALE_MATCH_ENV] == 'legacy'               # spawned workers inherit it
    _detect(_action(_screen((320, 240))))
    assert action_log.result['template']['scale_mode'] == 'legacy'
    ImageMatcher.set_high_compatibility(None)                    # not given: left as it is
    assert ImageMatcher.scale_match_mode() == 'legacy'
    ImageMatcher.set_high_compatibility(True)
    _detect(_action(_screen((320, 240))))
    assert action_log.result['template']['scale_mode'] == 'searching'


def test_the_engine_accepts_the_option(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, SCREENPLAN_DATA_ROOT=str(tmp_path))
    out = subprocess.run([sys.executable, '-m', 'ScriptEngine.script_manager', '--help'],
                         cwd=root, env=env, capture_output=True, text=True, timeout=120).stdout
    assert '--high-compatibility, --no-high-compatibility' in out
