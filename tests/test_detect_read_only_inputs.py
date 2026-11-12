"""A parallel detect's worker gets its screenshot and template arrays as
read-only views of shared memory (ScriptEngine/shared_memory_args.py), so the
detect code must never write into them. This runs every detect path on
read-only inputs; a write raises "assignment destination is read-only"."""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper, script_logger


class _ActionLog:
    def update_result(self, result):
        pass


@pytest.fixture(autouse=True)
def quiet_logger(monkeypatch):
    # The logger is a singleton with no log file outside a run.
    script_logger.set_log_file_path(os.devnull)
    script_logger.set_log_to_stdout(False)
    monkeypatch.setattr(script_logger, 'get_action_log', lambda: _ActionLog())


H, W = 120, 160          # the screen the template was recorded on
TOP, LEFT, TH, TW = 30, 40, 24, 32


def _read_only(arr):
    arr = np.ascontiguousarray(arr)
    arr.flags.writeable = False
    return arr


def _action(detect_type, match_mode='bestMatch', screen_shape=(H, W), skip=False, use_color=True):
    rng = np.random.default_rng(3)
    recorded = cv2.GaussianBlur(rng.integers(0, 256, (H, W, 3), dtype=np.uint8), (5, 5), 0)
    template = recorded[TOP:TOP + TH, LEFT:LEFT + TW]
    screen = cv2.resize(recorded, (screen_shape[1], screen_shape[0])) if screen_shape != (H, W) else recorded
    canvas_mask = np.zeros((H, W, 3), dtype=np.uint8)
    canvas_mask[TOP:TOP + TH, LEFT:LEFT + TW] = 255
    canvas_img = cv2.bitwise_and(recorded, canvas_mask)
    floating = {
        'img': template, 'mask': np.full((TH, TW, 3), 255, np.uint8),
        'mask_single_channel': np.full((TH, TW), 255, np.uint8),
        'outputMask': np.full((TH, TW, 3), 255, np.uint8),
        'outputMask_single_channel': np.full((TH, TW), 255, np.uint8),
        'sourceScreenHeight': H, 'sourceScreenWidth': W,
    }
    fixed = {
        'img': canvas_img, 'mask': canvas_mask, 'mask_single_channel': canvas_mask[:, :, 0],
        'outputMask': canvas_mask, 'outputMask_single_channel': canvas_mask[:, :, 0],
        'sourceScreenHeight': H, 'sourceScreenWidth': W,
    }
    floating = {k: _read_only(v) if isinstance(v, np.ndarray) else v for k, v in floating.items()}
    fixed = {k: _read_only(v) if isinstance(v, np.ndarray) else v for k, v in fixed.items()}
    screen = _read_only(screen)
    return {
        'actionName': 'detectObject', 'actionGroup': 1,
        'input_obj': {
            'screencap_im_bgr': screen, 'screencap_mask': None, 'match_point': (0, 0),
            'original_image': screen, 'original_image_blurred': _read_only(cv2.GaussianBlur(screen, (31, 31), 0)),
            'original_height': screen.shape[0], 'original_width': screen.shape[1], 'fixed_scale': False,
        },
        'actionData': {
            'detectActionType': detect_type, 'matchMode': match_mode, 'threshold': 0.9,
            'skipDetection': skip, 'outputVarName': 'match', 'detectorName': 'pixelDifference',
            'useColor': use_color, 'useImageRescaledToScreenOnly': False,
            'maskLocation': [[0, 0], [TW - 1, TH - 1]], 'excludeMatchedAreaFromOutput': True,
            'sceneLocation': [[LEFT, TOP]],
            'positiveExamples': [{'floatingObject': floating, 'fixedObject': fixed}],
        },
    }


@pytest.mark.parametrize('detect_type,match_mode,screen_shape,skip,use_color', [
    ('floatingObject', 'bestMatch', (H, W), False, True),
    ('floatingObject', 'bestMatch', (H, W), False, False),
    ('floatingObject', 'bestMatch', (H * 2, W * 2), False, True),    # resized match
    ('floatingObject', 'firstMatch', (H, W), False, True),           # fixed location first
    ('floatingObject', 'firstMatch', (H * 2, W * 2), False, True),
    ('fixedObject', 'bestMatch', (H, W), False, True),
    ('fixedObject', 'bestMatch', (H * 2, W * 2), False, True),       # rescaled scene
    ('fixedObject', 'bestMatch', (H, W), True, True),                # skipDetection
    ('floatingObject', 'bestMatch', (H, W), True, True),
])
def test_detect_paths_never_write_into_their_inputs(detect_type, match_mode, screen_shape, skip, use_color):
    action = _action(detect_type, match_mode, screen_shape, skip, use_color)
    _, matches, log_objs = DetectObjectHelper.handle_detect_object(action)
    assert matches, 'the template is on the screen; the detect should find it'
    assert log_objs['base'][0] is not None
