"""score_detects (detect_scorer.py): a script's detects scored on saved images
with the engine's own detection, each on its own, met the threshold or not."""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ScriptEngine import detect_scorer
import ScriptEngine.script_loader as script_loader_mod


@pytest.fixture(autouse=True)
def quiet_logger():
    # The logger is a singleton with no log file outside a run.
    detect_scorer.script_logger.set_log_file_path(os.devnull)
    detect_scorer.script_logger.set_log_to_stdout(False)


def _screen(with_square=True):
    rng = np.random.default_rng(7)
    screen = rng.integers(0, 60, (120, 160, 3), dtype=np.uint8)
    if with_square:
        # A patterned square the template is cut from, at (40, 30).
        patch = np.zeros((20, 24, 3), dtype=np.uint8)
        patch[:, :12] = (200, 40, 90)
        patch[:10, 12:] = (20, 220, 20)
        patch[10:, 12:] = (250, 250, 250)
        screen[30:50, 40:64] = patch
    return screen


def _detect(group, threshold, detect_type='floatingObject', match_mode='bestMatch', input_expression=''):
    template = _screen()[30:50, 40:64].copy()
    mask = np.full(template.shape, 255, dtype=np.uint8)
    floating = {
        'img': template,
        'mask': mask,
        'mask_single_channel': np.full(template.shape[:2], 255, dtype=np.uint8),
        'sourceScreenWidth': 160,
        'sourceScreenHeight': 120,
    }
    script_loader_mod.set_output_mask(floating, '', False, False)
    scene_mask = np.zeros((120, 160, 3), dtype=np.uint8)
    scene_mask[30:50, 40:64] = 255
    fixed = {
        'img': cv2.bitwise_and(_screen(), scene_mask),
        'mask': scene_mask,
        'mask_single_channel': np.uint8(cv2.cvtColor(scene_mask, cv2.COLOR_BGR2GRAY)),
        'sourceScreenWidth': 160,
        'sourceScreenHeight': 120,
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
            'inputExpression': input_expression,
            'maxMatches': 1,
            'outputVarName': 'match',
            'sceneLocation': [[40, 30]],
            'positiveExamples': [{'floatingObject': floating, 'fixedObject': fixed}],
        },
    }


def test_a_template_on_its_screen_matches_where_it_was_cut():
    out = detect_scorer.score_one(_detect(1, 0.9), _screen(), 'train')
    assert out['matched'] is True
    assert out['score'] > 0.99
    assert out['threshold'] == 0.9
    assert (out['location']['x'], out['location']['y']) == (40, 30)
    assert (out['location']['width'], out['location']['height']) == (24, 20)
    assert 'searched' not in out


def test_a_screen_without_it_still_reports_the_best_score_and_where():
    out = detect_scorer.score_one(_detect(1, 0.9), _screen(with_square=False), 'train')
    assert out['matched'] is False
    assert out['matchCount'] == 0
    assert out['score'] is not None and out['score'] < 0.9
    assert out['location'] is not None


def test_a_scene_detect_reports_the_scene_score():
    on = detect_scorer.score_one(_detect(2, 0.8, detect_type='fixedObject'), _screen(), 'train')
    assert on['matched'] is True
    assert on['scene']['passed'] is True
    off = detect_scorer.score_one(_detect(2, 0.8, detect_type='fixedObject'), _screen(with_square=False), 'train')
    assert off['matched'] is False
    assert off['scene']['passed'] is False
    assert off['score'] == off['scene']['score']
    assert (off['location']['x'], off['location']['y']) == (40, 30)


def test_a_detect_on_an_earlier_match_says_it_was_scored_on_the_whole_image():
    out = detect_scorer.score_one(_detect(3, 0.9, input_expression='earlierMatch'), _screen(), 'train')
    assert out['searched'] == 'whole-image'
    assert out['inRunSearches'] == 'earlierMatch'


def test_every_detect_on_every_image_through_the_cli(tmp_path, monkeypatch):
    with_square = tmp_path / 'with.png'
    without = tmp_path / 'without.png'
    cv2.imwrite(str(with_square), _screen())
    cv2.imwrite(str(without), _screen(with_square=False))
    script = {
        'props': {'scriptMode': 'train'},
        'actionRows': [{'actions': [
            _detect(1, 0.9),
            {'actionName': 'sleepStatement', 'actionGroup': 2, 'actionData': {}},
            _detect(4, 0.9, detect_type='fixedObject'),
        ]}],
    }
    monkeypatch.setattr(script_loader_mod, 'parse_script', lambda name, workspace='Default', **_: script)
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({
        'workspace': '.Workspace1.branch1', 'scriptName': 'S', 'actions': None,
        'images': [{'id': 'with', 'path': str(with_square)}, {'id': 'without', 'path': str(without)}, {'id': 'gone', 'path': str(tmp_path / 'gone.png')}],
    }))
    output = tmp_path / 'out.json'
    assert detect_scorer.main(['--score-detects', str(request), '--output', str(output)]) == 0
    result = json.loads(output.read_text())
    assert result['missing'] == []
    by = {(r['action'], r['image']): r for r in result['results']}
    assert sorted({a for a, _ in by}) == ['detectObject-1', 'detectObject-4']
    assert by[('detectObject-1', 'with')]['matched'] is True
    assert by[('detectObject-1', 'without')]['matched'] is False
    assert by[('detectObject-4', 'with')]['matched'] is True
    assert by[('detectObject-1', 'gone')]['error'] == 'the image cannot be read'


def test_a_named_detect_the_script_lacks_is_listed_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(script_loader_mod, 'parse_script', lambda name, workspace='Default', **_: {
        'props': {}, 'actionRows': [{'actions': [_detect(1, 0.9)]}]
    })
    result = detect_scorer.score_detects({'workspace': 'W', 'scriptName': 'S', 'actions': ['detectObject-9'], 'images': []})
    assert result['missing'] == ['detectObject-9']
    assert result['results'] == []
