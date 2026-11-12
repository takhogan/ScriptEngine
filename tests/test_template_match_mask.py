"""A template whose mask keeps every pixel is matched without the mask
(ImageMatcher.template_match_mask): OpenCV's masked TM_CCOEFF_NORMED does
several times the work of the unmasked one and scores the same. A real
partial mask, and a flat template, keep it."""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers.detect_scene_helper import script_logger
from ScriptEngine.helpers.image_matcher import ImageMatcher

THRESHOLDS = (0.8, 0.9, 0.95)


class _ActionLog:
    def update_result(self, result):
        pass


@pytest.fixture(autouse=True)
def quiet_logger(monkeypatch):
    # The logger is a singleton with no log file outside a run.
    script_logger.set_log_file_path(os.devnull)
    script_logger.set_log_to_stdout(False)
    monkeypatch.setattr(script_logger, 'get_action_log', lambda: _ActionLog())


def _scene():
    """A 160 x 220 smooth textured BGR screen, the 24 x 36 template cut from it,
    and copies of the template pasted in with noise and a brightness shift, so
    the scores spread across the thresholds."""
    rng = np.random.default_rng(7)
    screen = cv2.GaussianBlur(rng.integers(0, 256, (160, 220, 3), dtype=np.uint8), (7, 7), 0)
    screen = cv2.normalize(screen, None, 0, 255, cv2.NORM_MINMAX)
    template = screen[20:44, 30:66].copy()
    for (y, x), noise, shift in [((90, 20), 6, 0), ((40, 120), 14, 10), ((110, 150), 22, -15), ((10, 170), 30, 5)]:
        noisy = template.astype(np.int16) + rng.normal(0, noise, template.shape).astype(np.int16) + shift
        screen[y:y + template.shape[0], x:x + template.shape[1]] = np.clip(noisy, 0, 255).astype(np.uint8)
    return screen, template


def _detect_obj(template, mask):
    return {
        'img': template,
        'mask_single_channel': mask,
        'outputMask': np.full(template.shape, 255, dtype=np.uint8),
        'sourceScreenHeight': 160,
        'sourceScreenWidth': 220,
    }


def _match(screen, template, mask, threshold, use_color):
    return ImageMatcher.produce_template_matches(
        {'actionData': {'useImageRescaledToScreenOnly': False}},
        screen, _detect_obj(template, mask), check_image_scale=False,
        threshold=threshold, use_color=use_color, use_mask=True,
    )


def _points(matches):
    return [(m.point, round(float(m.score), 3)) for m in matches]


def _thresholded(match_result, threshold):
    return ~np.isnan(match_result) & (match_result < np.inf) & (match_result >= threshold)


@pytest.mark.parametrize('use_color', [True, False])
def test_a_full_mask_finds_the_same_matches_as_before(monkeypatch, use_color):
    screen, template = _scene()
    mask = np.full(template.shape[:2], 255, dtype=np.uint8)
    grey = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    assert ImageMatcher.template_match_mask(template if use_color else grey, mask) is None

    new = {t: _match(screen, template, mask, t, use_color) for t in THRESHOLDS}
    # Before the change: the mask always went to matchTemplate.
    monkeypatch.setattr(ImageMatcher, 'template_match_mask', staticmethod(lambda template, mask: mask))
    old = {t: _match(screen, template, mask, t, use_color) for t in THRESHOLDS}

    for t in THRESHOLDS:
        (new_matches, new_result), (old_matches, old_result) = new[t], old[t]
        assert (_thresholded(new_result, t) == _thresholded(old_result, t)).all()
        assert _points(new_matches) == _points(old_matches)
        assert np.nanmax(np.abs(new_result - old_result)) < 1e-3
    # The scene spreads its matches across the thresholds.
    counts = [len(new[t][0]) for t in THRESHOLDS]
    assert counts[0] > counts[-1] >= 1


def _spy_masks(monkeypatch):
    masks = []
    real = cv2.matchTemplate

    def spy(image, templ, method, result=None, mask=None):
        masks.append(mask)
        return real(image, templ, method, result=result, mask=mask)

    monkeypatch.setattr(cv2, 'matchTemplate', spy)
    return masks


def test_a_full_mask_is_left_out_of_matchtemplate(monkeypatch):
    screen, template = _scene()
    masks = _spy_masks(monkeypatch)
    _match(screen, template, np.full(template.shape[:2], 255, dtype=np.uint8), 0.9, True)
    assert masks == [None]


def test_a_partial_mask_still_goes_to_matchtemplate(monkeypatch):
    screen, template = _scene()
    mask = np.full(template.shape[:2], 255, dtype=np.uint8)
    mask[8:16, 10:26] = 0
    assert ImageMatcher.template_match_mask(template, mask) is mask
    masks = _spy_masks(monkeypatch)
    _match(screen, template, mask, 0.9, True)
    assert len(masks) == 1 and masks[0] is mask


@pytest.mark.parametrize('use_color', [True, False])
def test_a_flat_template_keeps_its_mask(monkeypatch, use_color):
    screen, _ = _scene()
    template = np.full((24, 36, 3), (40, 90, 160), dtype=np.uint8)
    mask = np.full(template.shape[:2], 255, dtype=np.uint8)
    grey = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    assert ImageMatcher.template_match_mask(template if use_color else grey, mask) is mask
    masks = _spy_masks(monkeypatch)
    matches, _ = _match(screen, template, mask, 0.9, use_color)
    assert len(masks) == 1 and masks[0] is mask
    # Masked, a flat template scores inf/NaN and matches nothing; unmasked, a
    # grey one would score 1.0 everywhere.
    assert matches == []


def test_a_template_flat_only_in_grey_keeps_its_mask_for_a_grey_match():
    # Blue and green of the same luminance: the colour template varies, its grey copy does not.
    template = np.zeros((10, 10, 3), dtype=np.uint8)
    template[:, :5, 0] = 255  # blue: grey 29
    template[:, 5:, 1] = 49   # green: grey 29
    grey = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    assert grey.min() == grey.max()
    mask = np.full((10, 10), 255, dtype=np.uint8)
    assert ImageMatcher.template_match_mask(template, mask) is None
    assert ImageMatcher.template_match_mask(grey, mask) is mask


def test_one_flat_channel_matches_the_same_without_the_mask():
    screen, template = _scene()
    template[:, :, 0] = 50
    mask = np.full(template.shape[:2], 255, dtype=np.uint8)
    assert ImageMatcher.template_match_mask(template, mask) is None
    masked = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED, mask=mask)
    unmasked = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    for t in THRESHOLDS:
        assert (_thresholded(masked, t) == _thresholded(unmasked, t)).all()


def test_masks_that_are_kept():
    _, template = _scene()
    assert ImageMatcher.template_match_mask(template, None) is None
    zero = np.zeros(template.shape[:2], dtype=np.uint8)
    assert ImageMatcher.template_match_mask(template, zero) is zero
    wrong_size = np.full((10, 10), 255, dtype=np.uint8)
    assert ImageMatcher.template_match_mask(template, wrong_size) is wrong_size


def test_any_uniform_non_zero_mask_is_left_out():
    _, template = _scene()
    assert ImageMatcher.template_match_mask(template, np.ones(template.shape[:2], dtype=np.uint8)) is None
    assert ImageMatcher.template_match_mask(template, np.full(template.shape, 255, dtype=np.uint8)) is None
