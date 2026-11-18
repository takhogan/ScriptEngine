"""Benchmark of template matching on screens of another size
(docs/multiscale-template-matching.md, "Measurements").

Runs a script's floatingObject detects through the engine's own detection
(DetectObjectHelper.handle_detect_object) on captures of another size, once
per mode (SCREENPLAN_SCALE_MATCH=legacy, then the learned multi-scale
matching from an empty device), in one shuffled order, as a run on a new
device would meet them. Reports, per mode: detects that matched, matched at
the right place (synthetic captures only), scores, and time per detect.

Captures:
  --synthetic 1280x720,1600x900  each detect's own source screenshot
      (srcImg), resized: the true place is its sceneLocation, scaled.
      Each detect is also run on N other detects' captures (--others), where
      the template may or may not be: those count toward time, not accuracy.
  --captures WORKSPACE/SCRIPT,...  the source screenshots of other scripts,
      as they are (real captures of the same screens at another size); no
      true place is known. glob:PATTERN reads image files instead.

Point SCREENPLAN_DATA_ROOT at a scratch folder whose scripts/ links to a
script library: the learned scales are written to its deviceScales/.

    SCREENPLAN_DATA_ROOT=/tmp/bench python -m tools.scale_bench \\
        --templates Workspace1/ScriptA,Workspace1/ScriptB --synthetic 1280x720 --out result.json
"""
import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from ScriptEngine.common.logging.script_logger import ScriptLogger  # noqa: E402
from ScriptEngine import detect_scorer  # noqa: E402
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper  # noqa: E402
from ScriptEngine.helpers.scale_memory import ScaleMemory  # noqa: E402

DEVICE = 'bench:device'


def load_detects(spec):
    from ScriptEngine.script_loader import parse_script
    workspace, script_name = spec.split('/', 1)
    script = parse_script(script_name, workspace=workspace)
    detects = []
    for row in script['actionRows']:
        for action in row['actions']:
            data = action['actionData']
            if action['actionName'] != 'detectObject' or data['detectActionType'] != 'floatingObject':
                continue
            if data.get('inputExpression') or data.get('skipDetection') in (True, 'true'):
                continue
            if not data.get('positiveExamples') or data.get('srcImg') is None:
                continue
            action['bench_id'] = '{}#{}'.format(script_name, action['actionGroup'])
            detects.append(action)
    return detects


def image_id(image):
    return hashlib.sha1(image.tobytes()[::97]).hexdigest()[:10]


def resize(image, size):
    h, w = image.shape[:2]
    shrink = size[0] * size[1] < w * h
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA if shrink else cv2.INTER_CUBIC)


def build_tasks(detects, synthetic_sizes, capture_specs, others, seed):
    rng = random.Random(seed)
    tasks = []
    if synthetic_sizes:
        sources = {}
        for d in detects:
            sources.setdefault(image_id(d['actionData']['srcImg']), d['actionData']['srcImg'])
        for size in synthetic_sizes:
            captures = {key: resize(img, size) for key, img in sources.items()}
            keys = sorted(captures)
            for d in detects:
                src = d['actionData']['srcImg']
                own = image_id(src)
                sx, sy = size[0] / src.shape[1], size[1] / src.shape[0]
                (x, y) = d['actionData']['sceneLocation'][0]
                tasks.append({'detect': d, 'capture': captures[own], 'set': 'synthetic {}x{}'.format(*size),
                              'truth': (x * sx, y * sy), 'own': True})
                for key in rng.sample([k for k in keys if k != own], min(others, len(keys) - 1)):
                    tasks.append({'detect': d, 'capture': captures[key], 'set': 'synthetic {}x{}'.format(*size),
                                  'truth': None, 'own': False})
    for spec in capture_specs:
        images = {}
        if spec.startswith('glob:'):
            import glob
            for path in sorted(glob.glob(spec[len('glob:'):], recursive=True)):
                image = cv2.imread(path, cv2.IMREAD_COLOR)
                if image is not None:
                    images.setdefault(image_id(image), image)
            spec = 'images'
        else:
            for d in load_detects(spec):
                images.setdefault(image_id(d['actionData']['srcImg']), d['actionData']['srcImg'])
        for d in detects:
            for key, img in sorted(images.items()):
                tasks.append({'detect': d, 'capture': img, 'set': 'real {}'.format(spec), 'truth': None, 'own': False,
                              'capture_id': key})
    rng.shuffle(tasks)
    return tasks


def run_task(task, mode):
    os.environ['SCREENPLAN_SCALE_MATCH'] = mode
    action = dict(task['detect'])
    action['scale_device'] = DEVICE
    action['input_obj'] = detect_scorer._input_obj(task['capture'])
    log = detect_scorer._ResultLog()
    detect_scorer.script_logger.set_action_log(log)
    start = time.perf_counter()
    _, matches, log_objs = DetectObjectHelper.handle_detect_object(action, script_mode='test')
    elapsed = time.perf_counter() - start
    template = log.result.get('template') or {}
    data = task['detect']['actionData']
    out = {
        'detect': task['detect']['bench_id'], 'set': task['set'], 'own': task['own'],
        'capture': '{}x{}'.format(task['capture'].shape[1], task['capture'].shape[0]),
        'capture_id': task.get('capture_id'),
        'threshold': float(data['threshold']), 'matched': len(matches) > 0,
        'score': float(matches[0]['score']) if matches else None,
        'point': [round(float(v), 1) for v in matches[0]['point']] if matches else None,
        'size': [int(matches[0]['width']), int(matches[0]['height'])] if matches else None,
        'scale': template.get('scale'), 'scale_mode': template.get('scale_mode'),
        'scales_tried': template.get('scales_tried'), 'seconds': round(elapsed, 4),
    }
    if matches and task['truth'] is not None:
        tx, ty = task['truth']
        w, h = out['size']
        out['correct'] = abs(out['point'][0] - tx) <= max(3, 0.25 * w) and abs(out['point'][1] - ty) <= max(3, 0.25 * h)
    if not matches and log_objs and log_objs.get('floatingObject') is not None:
        from ScriptEngine.helpers.image_matcher import ImageMatcher
        candidate = ImageMatcher.best_candidate(log_objs['floatingObject'][1])
        out['best_score'] = candidate[1] if candidate else None
    else:
        out['best_score'] = out['score']
    return out


def summarize(rows):
    def stats(values):
        values = sorted(values)
        if not values:
            return None
        return {'n': len(values), 'mean': round(statistics.mean(values), 4), 'median': round(statistics.median(values), 4),
                'p90': round(values[int(0.9 * (len(values) - 1))], 4), 'total': round(sum(values), 2)}
    own = [r for r in rows if r['own']]
    return {
        'detects': len(rows),
        'matched': sum(r['matched'] for r in rows),
        'own_screen': {
            'n': len(own),
            'matched': sum(r['matched'] for r in own),
            'correct': sum(bool(r.get('correct')) for r in own),
            'mean_best_score': round(statistics.mean([r['best_score'] for r in own if r['best_score'] is not None]), 4) if own else None,
        },
        'seconds': stats([r['seconds'] for r in rows]),
        'seconds_hit': stats([r['seconds'] for r in rows if r['matched']]),
        'seconds_miss': stats([r['seconds'] for r in rows if not r['matched']]),
        'by_scale_mode': {
            m: stats([r['seconds'] for r in rows if r['scale_mode'] == m])
            for m in sorted({r['scale_mode'] for r in rows if r['scale_mode']})
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--templates', required=True, help='WORKSPACE/SCRIPT,... whose detects are scored')
    parser.add_argument('--synthetic', default='', help='WxH,... sizes to resize each detect\'s own screenshot to')
    parser.add_argument('--captures', default='', help='WORKSPACE/SCRIPT,... whose screenshots are the captures')
    parser.add_argument('--others', type=int, default=2, help='other captures per detect (synthetic)')
    parser.add_argument('--modes', default='legacy,learned')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    logger = ScriptLogger()
    logger.set_log_file_path(os.devnull)
    logger.set_log_to_stdout(False)

    detects = [d for spec in args.templates.split(',') if spec for d in load_detects(spec)]
    sizes = [tuple(int(v) for v in s.split('x')) for s in args.synthetic.split(',') if s]
    tasks = build_tasks(detects, sizes, [s for s in args.captures.split(',') if s], args.others, args.seed)
    print('{} detects, {} tasks'.format(len(detects), len(tasks)), file=sys.stderr)

    from ScriptEngine.common.constants.script_engine_constants import data_path
    report = {'templates': args.templates, 'synthetic': args.synthetic, 'captures': args.captures, 'modes': {}}
    for mode in args.modes.split(','):
        # A new device: nothing learned.
        ScaleMemory.reset()
        scales_file = data_path('deviceScales', 'bench_device.json')
        if os.path.exists(scales_file):
            os.remove(scales_file)
        rows = [run_task(task, mode) for task in tasks]
        by_set = {}
        for row in rows:
            by_set.setdefault(row['set'], []).append(row)
        report['modes'][mode] = {
            'summary': {name: summarize(set_rows) for name, set_rows in sorted(by_set.items())},
            'rows': rows,
        }
        ScaleMemory.reset()
        if os.path.exists(scales_file):
            with open(scales_file) as f:
                report['modes'][mode]['learned'] = json.load(f)
        print(mode, json.dumps(report['modes'][mode]['summary'], indent=1), file=sys.stderr)
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=1)


if __name__ == '__main__':
    main()
