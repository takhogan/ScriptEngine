# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""Scores a script's detectObject actions against saved images, without a run.

The controller's score_detects tool runs this through the agent tools
entry point, `agent_tools score-detects --request REQUEST.json --output
RESULT.json` (agent_tools.py). Each detect is scored on each image with the engine's own detection
(DetectObjectHelper.handle_detect_object, as a run calls it), so a score
here is the score a run would get on that screen. Every detect is scored on
its own: in a run, the first of a firstMatch group to succeed cancels its
siblings, so their scores cannot be compared there.

A detect whose inputExpression names an earlier detect's match searches only
inside that match in a run. Here it is scored against the whole image, and
its result says so (`searched: whole-image`), unless the request names that
earlier detect in `within`.

`within` (the controller's firstMatch mode) lists detects to run first on
each image, outermost first, as a run reaches them: each searches its input
(the whole image, or the match of one before it), and its first match is
kept under its outputVarName, as a run keeps it in state. The detects of
`actions` then take their input the way a run does
(DetectObjectHelper.get_detect_area): inside the match their inputExpression
names, or the whole image without one. Their results say which
(`input`). When a detect of `within` finds nothing on an image, the others
are not reached there: each result for that image is `reached: false` with
the detect that stopped it, under `withinResults` the scores of the chain.

The request:

    {"workspace": ".Workspace1.branch1", "scriptName": "PiKVM_Laptop_UnlockToDesktop",
     "actions": ["detectObject-21"] | null,
     "images": [{"id": "cap_x", "path": "/abs/cap_x.png"}, ...]}

`actions` null scores every detectObject of the script (not its includes).
The result, per detect and image: matched, score (the best score, met the
threshold or not), threshold, location (where that score is), and for a
detect that compares a scene first, the scene's score as well.
"""

import cv2

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.action_result import merge
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper
from ScriptEngine.helpers.image_matcher import ImageMatcher

script_logger = ScriptLogger()


class _ResultLog:
    """Stands in for the action log while scoring: keeps the result fields
    the detection records (scene score, template options) and writes no
    files."""

    def __init__(self):
        self.result = {}

    def update_result(self, fields):
        merge(self.result, fields)

    def __getattr__(self, name):
        # set_summary, add_post_file, ...: nothing to write.
        return lambda *args, **kwargs: None


def _label(action):
    return '{}-{}'.format(action['actionName'], action['actionGroup'])


def _input_obj(image_bgr):
    """What the executor builds from a fresh screenshot (script_action_executor)."""
    blurred = cv2.copyMakeBorder(image_bgr.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
    blurred = cv2.GaussianBlur(blurred, (31, 31), 0)
    return {
        'screencap_im_bgr': image_bgr,
        'screencap_mask': None,
        'match_point': (0, 0),
        'original_image': image_bgr,
        'original_image_blurred': blurred[15:-15, 15:-15],
        'original_height': image_bgr.shape[0],
        'original_width': image_bgr.shape[1],
        'fixed_scale': False,
    }


def _box(point, width, height):
    return {'x': round(float(point[0]), 1), 'y': round(float(point[1]), 1), 'width': int(width), 'height': int(height)}


def _run_input(action, image_bgr, state, log):
    """The input a run gives the detect (script_action_executor): the match
    its inputExpression names when `state` holds it, else the whole screen.
    Returns the input and how it was searched, for the result."""
    expression = action['actionData'].get('inputExpression') or ''
    if not expression or expression not in state:
        return _input_obj(image_bgr), {'source': 'screenshot', 'expression': expression or None}
    area = DetectObjectHelper.get_detect_area(action, state)
    if area['screencap_im_bgr'] is None:
        return _input_obj(image_bgr), {'source': 'screenshot', 'expression': expression}
    return area, dict(log.result.get('input') or {'source': 'expression', 'expression': expression})


def score_one(action, image_bgr, script_mode, state=None, keep_match=None):
    """One detect on one image, through the engine's detection. With
    `state` (firstMatch's chain of earlier matches), the input is the one a
    run gives it; `keep_match` then receives the first match."""
    data = action['actionData']
    threshold = float(data['threshold'])
    floating = data['positiveExamples'][0]['floatingObject']
    h, w = floating['outputMask_single_channel'].shape[0:2]
    log = _ResultLog()
    script_logger.set_action_log(log)
    scored = dict(action)
    searched = None
    if state is None:
        scored['input_obj'] = _input_obj(image_bgr)
    else:
        scored['input_obj'], searched = _run_input(action, image_bgr, state, log)
    offset = scored['input_obj']['match_point']
    try:
        _, matches, log_objs = DetectObjectHelper.handle_detect_object(scored, script_mode=script_mode)
    except SystemExit as e:
        # Some engine error paths exit the process; one detect must not end the others.
        return {'error': 'the detection exited ({})'.format(e.code)}
    out = {
        'detectType': data['detectActionType'],
        'matchMode': data.get('matchMode'),
        'threshold': threshold,
        'matched': len(matches) > 0,
        'matchCount': len(matches),
        'score': None,
        'location': None,
    }
    if searched is not None:
        out['input'] = searched
    if data.get('inputExpression') and (searched is None or searched['source'] != 'expression'):
        out['searched'] = 'whole-image'
        out['inRunSearches'] = data['inputExpression']
    scene = log.result.get('scene')
    if scene is not None:
        out['scene'] = {'score': float(scene['score']), 'passed': bool(scene['passed'])}
    if matches:
        best = matches[0]
        out['score'] = float(best['score'])
        out['location'] = _box(best['point'], w, h)
        if keep_match is not None:
            keep_match.append(best)
    elif log_objs.get('floatingObject') is not None:
        candidate = ImageMatcher.best_candidate(log_objs['floatingObject'][1])
        if candidate is not None:
            (x, y), score = candidate
            # A match made on the image resized to the template's screen is in that image's pixels.
            if log.result.get('template', {}).get('resized'):
                x *= image_bgr.shape[1] / floating['sourceScreenWidth']
                y *= image_bgr.shape[0] / floating['sourceScreenHeight']
            # Inside an earlier match the candidate is in the match's pixels.
            out['score'] = score
            out['location'] = _box((x + offset[0], y + offset[1]), w, h)
    elif scene is not None:
        out['score'] = float(scene['score'])
        scene_xy = data['sceneLocation'][0]
        out['location'] = _box((scene_xy[0] + offset[0], scene_xy[1] + offset[1]), w, h)
    return out


def _run_within(chain, detects, bgr, script_mode):
    """The detects of `within` on one image, in order, each match kept in a
    state as a run keeps it. Returns the state, each one's result, and the
    label of the one that found nothing (None when all matched)."""
    state = {}
    results = []
    for label in chain:
        action = detects[label]
        kept = []
        result = score_one(action, bgr, script_mode, state=state, keep_match=kept)
        results.append(dict(result, action=label))
        if not kept:
            return state, results, label
        output = action['actionData'].get('outputVarName')
        if output:
            state[output] = kept[0]
    return state, results, None


def score_detects(request):
    from ScriptEngine.script_loader import parse_script
    script = parse_script(request['scriptName'], workspace=request['workspace'])
    script_mode = script['props'].get('scriptMode', 'train')
    detects = {
        _label(action): action
        for row in script['actionRows'] for action in row['actions']
        if action['actionName'] == 'detectObject'
    }
    wanted = request.get('actions') or sorted(detects)
    within = request.get('within')
    missing = [label for label in wanted + (within or []) if label not in detects]
    images = []
    for image in request['images']:
        bgr = cv2.imread(image['path'], cv2.IMREAD_COLOR)
        images.append((image, bgr))
    if within is not None:
        return _score_within(request, detects, wanted, within, images, missing, script_mode)
    results = []
    for label in wanted:
        if label not in detects:
            continue
        for image, bgr in images:
            entry = {'action': label, 'image': image['id']}
            if bgr is None:
                entry['error'] = 'the image cannot be read'
            else:
                entry.update(score_one(detects[label], bgr, script_mode))
            results.append(entry)
    return {'scriptName': request['scriptName'], 'workspace': request['workspace'], 'missing': missing, 'results': results}


def _score_within(request, detects, wanted, within, images, missing, script_mode):
    """firstMatch: each image's chain of `within`, then `actions` with the input a run gives them."""
    chain = [label for label in within if label in detects]
    results = []
    within_results = []
    for image, bgr in images:
        if bgr is None:
            results.extend({'action': label, 'image': image['id'], 'error': 'the image cannot be read'} for label in wanted if label in detects)
            continue
        state, chain_results, stopped = _run_within(chain, detects, bgr, script_mode)
        within_results.extend(dict(r, image=image['id']) for r in chain_results)
        for label in wanted:
            if label not in detects:
                continue
            entry = {'action': label, 'image': image['id']}
            if stopped is not None:
                entry.update({'reached': False, 'stoppedAt': stopped})
            else:
                entry.update(score_one(detects[label], bgr, script_mode, state=state))
            results.append(entry)
    return {'scriptName': request['scriptName'], 'workspace': request['workspace'], 'missing': missing,
            'within': chain, 'results': results, 'withinResults': within_results}
