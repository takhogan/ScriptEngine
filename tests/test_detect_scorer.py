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

from ScriptEngine import agent_tools, detect_scorer
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


def test_every_detect_on_every_image_through_the_agent_tools_entry_point(tmp_path, monkeypatch):
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
    assert agent_tools.main(['score-detects', '--request', str(request), '--output', str(output)]) == 0
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


def test_an_unknown_tool_exits_2_and_writes_nothing(tmp_path, capsys):
    request = tmp_path / 'request.json'
    request.write_text('{}')
    output = tmp_path / 'out.json'
    assert agent_tools.main(['no-such-tool', '--request', str(request), '--output', str(output)]) == agent_tools.EXIT_UNKNOWN_TOOL
    assert not output.exists()
    assert 'score-detects' in capsys.readouterr().err


def test_a_missing_script_is_the_tools_answer_not_a_failure(tmp_path, monkeypatch):
    def missing(name, workspace='Default', **_):
        raise FileNotFoundError('no scripts/scriptLibrary/W/S/actionRows.json')
    monkeypatch.setattr(script_loader_mod, 'parse_script', missing)
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'workspace': 'W', 'scriptName': 'S', 'actions': None, 'images': []}))
    output = tmp_path / 'out.json'
    assert agent_tools.main(['score-detects', '--request', str(request), '--output', str(output)]) == 0
    assert json.loads(output.read_text())['error'] == 'not-found'


def test_the_entry_point_runs_as_a_module(tmp_path):
    import subprocess
    request = tmp_path / 'request.json'
    request.write_text('{}')
    done = subprocess.run(
        [sys.executable, '-m', 'ScriptEngine.agent_tools', 'no-such-tool', '--request', str(request), '--output', str(tmp_path / 'o.json')],
        cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == agent_tools.EXIT_UNKNOWN_TOOL
    assert 'unknown tool no-such-tool' in done.stderr


# firstMatch's `within`: a child detect searches inside its parent's match, as in a run.

def _patch_q():
    """A gradient block, distinct from the square, that a parent detect looks for."""
    q = np.zeros((30, 36, 3), dtype=np.uint8)
    q[:, :, 0] = np.linspace(0, 255, 36, dtype=np.uint8)[None, :]
    q[:, :, 2] = np.linspace(255, 0, 30, dtype=np.uint8)[:, None]
    q[12:18, :] = (0, 255, 255)
    return q


def _detect_of(group, template, threshold, output, input_expression=''):
    """A floatingObject bestMatch detect for `template`, cut from a 160x120 screen."""
    action = _detect(group, threshold, input_expression=input_expression)
    floating = {
        'img': template,
        'mask': np.full(template.shape, 255, dtype=np.uint8),
        'mask_single_channel': np.full(template.shape[:2], 255, dtype=np.uint8),
        'sourceScreenWidth': 160,
        'sourceScreenHeight': 120,
    }
    script_loader_mod.set_output_mask(floating, '', False, False)
    action['actionData']['positiveExamples'][0]['floatingObject'] = floating
    action['actionData']['outputVarName'] = output
    return action


def _within_script(parent, child):
    return {'props': {'scriptMode': 'train'}, 'actionRows': [{'actions': [parent]}, {'actions': [child]}]}


def _score(monkeypatch, tmp_path, script, images, actions, within):
    monkeypatch.setattr(script_loader_mod, 'parse_script', lambda name, workspace='Default', **_: script)
    paths = []
    for name, image in images.items():
        file = tmp_path / '{}.png'.format(name)
        cv2.imwrite(str(file), image)
        paths.append({'id': name, 'path': str(file)})
    return detect_scorer.score_detects({'workspace': 'W', 'scriptName': 'S', 'actions': actions, 'within': within, 'images': paths})


def test_within_a_parents_match_the_child_searches_only_inside_it(tmp_path, monkeypatch):
    screen = _screen()
    parent = _detect_of(1, screen[20:60, 30:80].copy(), 0.9, 'panel')
    child = _detect(2, 0.9, input_expression='panel')
    result = _score(monkeypatch, tmp_path, _within_script(parent, child), {'s': screen}, ['detectObject-2'], ['detectObject-1'])
    assert result['within'] == ['detectObject-1']
    assert result['withinResults'][0]['matched'] is True
    [out] = result['results']
    assert out['matched'] is True
    assert out['input']['source'] == 'expression'
    assert out['input']['area'] == {'x': 30, 'y': 20, 'width': 50, 'height': 40}
    assert 'searched' not in out
    # The location is on the screen, not in the parent's match.
    assert (out['location']['x'], out['location']['y']) == (40, 30)


def test_a_child_whose_template_is_outside_its_parents_match_misses_though_the_screen_has_it(tmp_path, monkeypatch):
    screen = _screen()
    screen[70:100, 100:136] = _patch_q()
    parent = _detect_of(1, _patch_q(), 0.9, 'panel')
    child = _detect(2, 0.9, input_expression='panel')
    result = _score(monkeypatch, tmp_path, _within_script(parent, child), {'s': screen}, ['detectObject-2'], ['detectObject-1'])
    [out] = result['results']
    assert out['input']['source'] == 'expression'
    assert out['matched'] is False
    assert out['location']['x'] >= 100 and out['location']['y'] >= 70
    # On its own, on the whole screen, it matches.
    assert detect_scorer.score_one(child, screen, 'train')['matched'] is True


def test_where_the_parent_finds_nothing_the_child_is_not_reached(tmp_path, monkeypatch):
    parent = _detect_of(1, _patch_q(), 0.9, 'panel')
    child = _detect(2, 0.9, input_expression='panel')
    result = _score(monkeypatch, tmp_path, _within_script(parent, child), {'s': _screen()}, ['detectObject-2'], ['detectObject-1'])
    assert result['withinResults'][0]['matched'] is False
    assert result['results'] == [{'action': 'detectObject-2', 'image': 's', 'reached': False, 'stoppedAt': 'detectObject-1'}]


def test_a_child_without_an_input_searches_the_whole_screen_within_a_chain(tmp_path, monkeypatch):
    screen = _screen()
    screen[70:100, 100:136] = _patch_q()
    parent = _detect_of(1, _patch_q(), 0.9, 'panel')
    child = _detect(2, 0.9)
    result = _score(monkeypatch, tmp_path, _within_script(parent, child), {'s': screen}, ['detectObject-2'], ['detectObject-1'])
    [out] = result['results']
    assert out['matched'] is True
    assert out['input'] == {'source': 'screenshot', 'expression': None}
