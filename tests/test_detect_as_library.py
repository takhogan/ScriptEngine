"""Detect helpers used as a library (UI_MAPPER.md §5.1): ScreenPlanUIMapper
re-scores a script's templates against old screenshots with the engine's own
matching, outside any run. This loads a script folder with the engine's loader
and runs a detect on an image in a fresh interpreter: no device, no run folder,
no logger set up."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import cv2
import numpy as np

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def write_script(folder):
    rng = np.random.default_rng(3)
    screen = rng.integers(0, 255, (200, 120, 3), dtype=np.uint8)
    template = screen[80:110, 40:90].copy()
    mask = np.full_like(template, 255)
    assets = folder / 'assets'
    assets.mkdir(parents=True)
    cv2.imwrite(str(assets / 'template.png'), template)
    cv2.imwrite(str(assets / 'mask.png'), mask)
    cv2.imwrite(str(folder / 'screen.png'), screen)
    action = {
        'actionName': 'detectObject', 'actionGroup': 1, 'childGroups': [], 'parentGroups': [],
        'actionData': {
            'targetSystem': 'adb', 'detectActionType': 'floatingObject', 'matchMode': 'bestMatch',
            'detectorName': 'pixelDifference', 'threshold': '0.9', 'useColor': True, 'maxMatches': 1,
            'useImageRescaledToScreenOnly': False, 'maskLocation': 'null', 'inputExpression': '',
            'outputVarName': 'detectObject_0',
            'positiveExamples': [{'floatingObject': {'img': None, 'mask': None,
                                                     'sourceScreenHeight': 200, 'sourceScreenWidth': 120}}],
        },
        'actionAssets': [
            {'filePath': 'assets/template.png', 'attributePath': 'actionData.positiveExamples.0.floatingObject.img', 'assetType': 'image'},
            {'filePath': 'assets/mask.png', 'attributePath': 'actionData.positiveExamples.0.floatingObject.mask', 'assetType': 'image'},
        ],
    }
    (folder / 'actionRows.json').write_text(json.dumps([{'actions': [action], 'actionRowIndex': 0, 'rowID': 0}]))
    for name, value in (('props.json', {}), ('inputs.json', []), ('outputs.json', [])):
        (folder / name).write_text(json.dumps(value))


RUN = textwrap.dedent('''
    import json, sys
    import cv2
    from ScriptEngine.script_loader import parse_script_file
    from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper
    folder = sys.argv[1]
    script = parse_script_file(
        'library', open(folder + '/actionRows.json'), open(folder + '/props.json'),
        open(folder + '/inputs.json'), open(folder + '/outputs.json'), folder)
    action = script['actionRows'][0]['actions'][0]
    screen = cv2.imread(folder + '/screen.png')
    action['input_obj'] = {
        'screencap_im_bgr': screen, 'match_point': (0, 0), 'fixed_scale': False,
        'original_image': screen, 'original_height': screen.shape[0], 'original_width': screen.shape[1],
    }
    _, matches, _ = DetectObjectHelper.handle_detect_object(action)
    print('MATCHES ' + json.dumps([[int(m['point'][0]), int(m['point'][1]), float(m['score'])] for m in matches]), flush=True)
''')


def test_a_detect_runs_without_a_run(tmp_path):
    write_script(tmp_path / 'script')
    data_root = tmp_path / 'data-root'
    data_root.mkdir()
    env = dict(os.environ, PYTHONPATH=str(ENGINE_ROOT), SCREENPLAN_DATA_ROOT=str(data_root))
    out = subprocess.run([sys.executable, '-c', RUN, str(tmp_path / 'script')], env=env, cwd=tmp_path,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert 'Error in writer thread' not in out.stderr, out.stderr[-2000:]
    line = next(line for line in out.stdout.splitlines() if line.startswith('MATCHES '))
    matches = json.loads(line[len('MATCHES '):])
    assert matches and matches[0][:2] == [40, 80] and matches[0][2] > 0.99
    # Nothing was written under the data root: no logs, no run folder.
    assert list(data_root.rglob('*')) == []
