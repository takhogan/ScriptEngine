"""maskLocation, the area a template encloses, crops a match's output with its
right and bottom included: [[left, top], [right, bottom]] from the template's
top left, as the compiler (fillContainedAreaMask) writes it."""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers.detect_scene_helper import apply_output_mask, crop_to_mask_location, script_logger
from ScriptEngine.helpers.image_matcher import ImageMatcher


@pytest.fixture(autouse=True)
def quiet_logger():
    # The logger is a singleton with no log file outside a run.
    script_logger.set_log_file_path(os.devnull)
    script_logger.set_log_to_stdout(False)


def _numbered(h, w):
    """An h x w BGR image whose pixel (x, y) holds (x, y, 0), to read back where a crop came from."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :, 0] = np.arange(w)[None, :]
    img[:, :, 1] = np.arange(h)[:, None]
    return img


def test_crop_includes_the_right_column_and_bottom_row():
    # A 30 x 20 frame enclosing x 4-25, y 4-15 (the hollow-frame test's maskLocation).
    cropped = crop_to_mask_location(_numbered(20, 30), [[4, 4], [25, 15]])
    assert cropped.shape[:2] == (12, 22)
    assert tuple(cropped[0, 0, :2]) == (4, 4)
    assert tuple(cropped[-1, -1, :2]) == (25, 15)


def test_a_template_that_encloses_nothing_crops_to_nothing():
    assert crop_to_mask_location(_numbered(20, 30), [[30, 20], [0, 0]]).size == 0


def test_apply_output_mask_crops_the_match_to_the_enclosed_area():
    screen = _numbered(60, 80)
    mask = np.full((20, 30, 3), 255, dtype=np.uint8)
    out = apply_output_mask(screen, (10, 8), mask, [[4, 4], [25, 15]])
    assert out.shape[:2] == (12, 22)
    assert tuple(out[0, 0, :2]) == (14, 12)
    assert tuple(out[-1, -1, :2]) == (35, 23)


class _ActionLog:
    def update_result(self, result):
        pass


def test_filter_matches_crops_each_match_to_the_enclosed_area(monkeypatch):
    monkeypatch.setattr(script_logger, 'get_action_log', lambda: _ActionLog())
    screen = _numbered(60, 80)
    template = screen[8:28, 10:40].copy()
    mask = np.full(template.shape, 255, dtype=np.uint8)
    match_result = np.zeros((41, 51), dtype=np.float32)
    match_result[8, 10] = 1.0
    matches, _ = ImageMatcher.filter_matches(
        {}, match_result, np.where(match_result >= 0.9), screen, template, mask,
        output_cropping=[[4, 4], [25, 15]],
    )
    assert len(matches) == 1
    area = matches[0].matched_area
    assert area.shape[:2] == (12, 22)
    assert tuple(area[0, 0, :2]) == (14, 12)
    assert tuple(area[-1, -1, :2]) == (35, 23)
