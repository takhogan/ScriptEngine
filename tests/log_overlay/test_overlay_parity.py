"""Overlays must render to exactly the post images the engine used to write.

Each case builds the overlay with the engine's builder, renders it with the
Python renderer, and compares it pixel for pixel with the pre-overlay drawing
code in legacy_drawing.py. The cases also go through a saved .overlay.html and
back, so the stored PNGs and the JSON round trip are covered too.
"""
import cv2
import numpy as np
import pytest

from ScriptEngine.common.logging.log_overlay import (
    LogImageStore, read_overlay_document, render_overlay, render_overlay_file, write_overlay,
)
from ScriptEngine.helpers.image_matcher import ImageMatcher
from ScriptEngine.helpers.click_action_helper import ClickActionHelper
from ScriptEngine.helpers.color_compare_helper import ColorCompareHelper

from . import legacy_drawing as legacy


def screenshot(height=240, width=320, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    image = np.stack([(xx * 255 // width), (yy * 255 // height), ((xx + yy) % 256)], axis=2)
    image = image + rng.integers(0, 40, size=(height, width, 3))
    return np.clip(image, 0, 255).astype(np.uint8)


def assert_parity(overlay, expected, tmp_path):
    rendered = render_overlay(overlay)
    assert rendered.shape == expected.shape
    diff = np.argwhere(np.any(rendered != expected, axis=2))
    assert diff.size == 0, 'pixels differ at {} (first of {})'.format(diff[0].tolist(), len(diff))

    html_path = str(tmp_path / 'case.overlay.html')
    write_overlay(
        overlay, html_path,
        {key: str(tmp_path / (key + '.png')) for key in overlay.images},
        store=LogImageStore()
    )
    assert np.array_equal(render_overlay_file(html_path), expected)
    return read_overlay_document(html_path)


def detect_action(detect_type, threshold=0.8, max_matches=1, input_obj=None):
    return {
        'actionData': {'detectActionType': detect_type, 'threshold': str(threshold), 'maxMatches': max_matches},
        'input_obj': input_obj or {'fixed_scale': False},
    }


def match(x, y, score):
    return {'point': (x, y), 'score': score}


# ---------------------------------------------------------------------------
# detectObject
# ---------------------------------------------------------------------------

def test_floating_matches(tmp_path):
    capture = screenshot()
    template = capture[100:130, 50:90].copy()
    matches = [match(50, 100, 0.97), match(200, 40, 0.91), match(295, 220, 0.85), match(10, 10, 0.5)]
    action = detect_action('floatingObject', max_matches=2)
    overlay = ImageMatcher.create_result_overlay(action, capture, (0, 0), template, matches, None)
    expected = legacy.create_result_im(action, capture.copy(), (0, 0), template, matches, None)
    assert_parity(overlay, expected, tmp_path)
    assert overlay.result['best'] == {'x': 50, 'y': 100, 'score': 0.97}
    assert [(m['x'], m['y']) for m in overlay.result['matches']] == [(50, 100), (200, 40), (295, 220)]


def test_floating_gray_template_and_max_matches_expression(tmp_path):
    capture = screenshot(seed=3)
    template = capture[20:60, 20:44, 1].copy()
    matches = [match(20, 20, 0.99), match(120, 150, 0.95)]
    action = detect_action('floatingObject', max_matches='{{n}}')
    overlay = ImageMatcher.create_result_overlay(action, capture, (0, 0), template, matches, None)
    expected = legacy.create_result_im(action, capture.copy(), (0, 0), template, matches, None)
    assert_parity(overlay, expected, tmp_path)


def test_floating_no_match_shows_best_candidate(tmp_path):
    capture = screenshot(seed=1)
    template = capture[60:100, 100:150].copy()
    rng = np.random.default_rng(1)
    match_result = rng.uniform(-1, 0.6, size=(240 - 40 + 1, 320 - 50 + 1)).astype(np.float32)
    match_result[5, 7] = np.nan
    match_result[9, 9] = np.inf
    match_result[200, 260] = 0.75  # best point, near the bottom-right edge
    action = detect_action('floatingObject')
    overlay = ImageMatcher.create_result_overlay(action, capture, (0, 0), template, [], match_result)
    expected = legacy.create_result_im(action, capture.copy(), (0, 0), template, [], match_result)
    assert_parity(overlay, expected, tmp_path)
    assert overlay.result['best']['x'] == 260 and overlay.result['best']['y'] == 200
    assert overlay.result['matches'] == []


def test_floating_no_valid_scores(tmp_path):
    capture = screenshot(seed=2)
    template = capture[0:10, 0:10].copy()
    match_result = np.full((231, 311), np.nan, np.float32)
    action = detect_action('floatingObject')
    overlay = ImageMatcher.create_result_overlay(action, capture, (0, 0), template, [], match_result)
    expected = legacy.create_result_im(action, capture.copy(), (0, 0), template, [], match_result)
    document = assert_parity(overlay, expected, tmp_path)
    assert 'template' not in document['images']


def test_fixed_object(tmp_path):
    capture = screenshot(seed=4)
    mask = np.zeros((80, 120), np.uint8)
    action = detect_action('fixedObject', threshold=0.7)
    for matches in ([match(30, 40, 0.9)], [match(30, 40, 0.4)]):
        overlay = ImageMatcher.create_result_overlay(action, capture, (0, 0), mask, matches, None)
        expected = legacy.create_result_im(action, capture.copy(), (0, 0), mask, matches, None)
        assert_parity(overlay, expected, tmp_path)


@pytest.mark.parametrize('blurred', [True, False])
def test_input_expression_composites_into_screenshot(tmp_path, blurred):
    original = screenshot(seed=5)
    ix, iy = 40, 30
    input_area = original[iy:iy + 120, ix:ix + 160]
    template = original[60:90, 70:100].copy()
    input_obj = {
        'fixed_scale': True,
        'original_image': original,
        'original_image_blurred': legacy.blur_like_executor(original) if blurred else None,
    }
    action = detect_action('floatingObject', input_obj=input_obj)
    matches = [match(70, 60, 0.95), match(185, 135, 0.9)]
    overlay = ImageMatcher.create_result_overlay(action, input_area, (ix, iy), template, matches, None)
    expected = legacy.create_result_im(action, input_area.copy(), (ix, iy), template, matches, None)
    document = assert_parity(overlay, expected, tmp_path)
    # The pre image is the input the detect consumed (the earlier match), with
    # the screenshot kept for context.
    assert document['pre'] == 'input'
    assert np.array_equal(cv2.imread(document['images']['input']['path']), input_area)
    assert np.array_equal(cv2.imread(document['images']['capture']['path']), original)


def test_input_expression_from_a_masked_match(tmp_path):
    original = screenshot(seed=6)
    ix, iy = 10, 20
    input_area = original[iy:iy + 100, ix:ix + 100].copy()
    input_area[:, :30] = 0  # masked by the earlier match
    input_obj = {'fixed_scale': True, 'original_image': original,
                 'original_image_blurred': legacy.blur_like_executor(original)}
    action = detect_action('fixedObject', threshold=0.5, input_obj=input_obj)
    mask = np.zeros((40, 40), np.uint8)
    matches = [match(50, 60, 0.8)]
    overlay = ImageMatcher.create_result_overlay(action, input_area, (ix, iy), mask, matches, None)
    expected = legacy.create_result_im(action, input_area.copy(), (ix, iy), mask, matches, None)
    document = assert_parity(overlay, expected, tmp_path)
    assert np.array_equal(cv2.imread(document['images']['input']['path']), input_area)


def test_builder_does_not_draw_on_the_input():
    # The old fixedObject branch drew its box onto the caller's input image.
    capture = screenshot(seed=7)
    before = capture.copy()
    action = detect_action('fixedObject')
    ImageMatcher.create_result_overlay(action, capture, (0, 0), np.zeros((20, 20), np.uint8), [match(5, 5, 0.9)], None)
    assert np.array_equal(capture, before)


# ---------------------------------------------------------------------------
# mouseInteractionAction / mouseMoveAction
# ---------------------------------------------------------------------------

def shape_point_list(seed=0):
    rng = np.random.default_rng(seed)
    mask = np.zeros((50, 70), np.uint8)
    mask[10:40, 5:30] = 255
    mask[rng.integers(0, 50, 30), rng.integers(0, 70, 30)] = 255
    mask[0, 0] = 1  # not > 1, so not part of the shape
    return {'input_type': 'shape', 'point': (260, 200), 'output_mask': mask}


POINT_LISTS = {
    'point_list': {'input_type': 'point_list', 'point_list': [(10, 10), (0, 0), (319, 239), (150, 100)]},
    'rectangle': {'input_type': 'rectangle', 'point': (100, 50), 'width': 60, 'height': 40},
    'shape': shape_point_list(),
    'unknown': {'input_type': 'none'},
}


@pytest.mark.parametrize('kind', sorted(POINT_LISTS))
def test_click(tmp_path, kind):
    capture = screenshot(seed=8)
    point_list = POINT_LISTS[kind]
    overlay = ClickActionHelper.create_click_overlay(capture, (123.7, 88.2), point_list)
    expected = legacy.draw_point_choice(capture.copy(), (123.7, 88.2), point_list)
    assert_parity(overlay, expected, tmp_path)


def test_drag(tmp_path):
    capture = screenshot(seed=9)
    deltas = [(12.4, 3.3), (30.9, -7.5), (0.6, 0.6), (55.1, 40.2)]
    overlay = ClickActionHelper.create_click_and_drag_overlay(
        capture, (20.5, 30.5), POINT_LISTS['shape'], (140, 100), POINT_LISTS['rectangle'], iter(deltas)
    )
    expected = legacy.draw_click_and_drag(
        capture.copy(), (20.5, 30.5), POINT_LISTS['shape'], (140, 100), POINT_LISTS['rectangle'], iter(deltas)
    )
    assert_parity(overlay, expected, tmp_path)
    assert len(overlay.result['path']) == 5


# ---------------------------------------------------------------------------
# colorCompareAction
# ---------------------------------------------------------------------------

def test_color_compare_without_input_expression(tmp_path):
    capture = screenshot(seed=10)
    blurred = legacy.blur_like_executor(capture)
    colors = [200.6, 10.2, 99.9]
    overlay = ColorCompareHelper.create_color_compare_overlay(capture, capture, blurred, (0, 0), colors)
    expected = legacy.create_color_compare_post_image(capture, capture, blurred, (0, 0), colors)
    document = assert_parity(overlay, expected, tmp_path)
    # Without an input expression the input is the screenshot: one file.
    assert document['pre'] == 'input'
    assert document['images']['input'] == document['images']['capture']


@pytest.mark.parametrize('point', [(50, 40), (300, 225)])
def test_color_compare_with_input_expression(tmp_path, point):
    original = screenshot(seed=11)
    blurred = legacy.blur_like_executor(original)
    x, y = point
    area = original[y:y + 60, x:x + 80]
    colors = [4, 128, 252]
    overlay = ColorCompareHelper.create_color_compare_overlay(area, original, blurred, point, colors)
    expected = legacy.create_color_compare_post_image(area, original, blurred, point, colors)
    assert_parity(overlay, expected, tmp_path)


def test_color_compare_without_screenshot(tmp_path):
    area = screenshot(80, 90, seed=12)
    blurred = legacy.blur_like_executor(screenshot(seed=13))
    for original_blurred, point in ((None, (0, 0)), (blurred, (30, 20))):
        overlay = ColorCompareHelper.create_color_compare_overlay(area, None, original_blurred, point, [1, 2, 3])
        expected = legacy.create_color_compare_post_image(area, None, original_blurred, point, [1, 2, 3])
        assert_parity(overlay, expected, tmp_path)
