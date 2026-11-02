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
its result says so (`searched: whole-image`).

The request:

    {"workspace": ".ACG.tcs", "scriptName": "PiKVM_TCS_UnlockToDesktop",
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


def score_one(action, image_bgr, script_mode):
    """One detect on one image, through the engine's detection."""
    data = action['actionData']
    threshold = float(data['threshold'])
    floating = data['positiveExamples'][0]['floatingObject']
    h, w = floating['outputMask_single_channel'].shape[0:2]
    log = _ResultLog()
    script_logger.set_action_log(log)
    scored = dict(action)
    scored['input_obj'] = _input_obj(image_bgr)
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
    if data.get('inputExpression'):
        out['searched'] = 'whole-image'
        out['inRunSearches'] = data['inputExpression']
    scene = log.result.get('scene')
    if scene is not None:
        out['scene'] = {'score': float(scene['score']), 'passed': bool(scene['passed'])}
    if matches:
        best = matches[0]
        out['score'] = float(best['score'])
        out['location'] = _box(best['point'], w, h)
    elif log_objs.get('floatingObject') is not None:
        candidate = ImageMatcher.best_candidate(log_objs['floatingObject'][1])
        if candidate is not None:
            (x, y), score = candidate
            # A match made on the image resized to the template's screen is in that image's pixels.
            if log.result.get('template', {}).get('resized'):
                x *= image_bgr.shape[1] / floating['sourceScreenWidth']
                y *= image_bgr.shape[0] / floating['sourceScreenHeight']
            out['score'] = score
            out['location'] = _box((x, y), w, h)
    elif scene is not None:
        out['score'] = float(scene['score'])
        out['location'] = _box(data['sceneLocation'][0], w, h)
    return out


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
    missing = [label for label in wanted if label not in detects]
    images = []
    for image in request['images']:
        bgr = cv2.imread(image['path'], cv2.IMREAD_COLOR)
        images.append((image, bgr))
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
