"""Action result files: every action's {prefix}result.json (action_result.py)."""
import glob
import json
import os
import pickle
from pathlib import Path

import numpy as np
import pytest

from ScriptEngine.helpers.color_compare_helper import ColorCompareHelper
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper

from .test_overlay_logging import action_log_json, action_result_json, detect_log_obj, match_shape, system_executor  # noqa: F401 (fixture)
from .test_overlay_parity import screenshot

SCHEMA_PATH = Path(__file__).resolve().parents[4] / 'packages' / 'screenplan-contracts' / 'schemas' / 'script-action-result.schema.json'


def check_against_schema(document):
    """Field names and nesting checked against ScriptActionResult, when the
    contracts package is checked out next to the engine."""
    if not SCHEMA_PATH.exists():
        return
    schema = json.loads(SCHEMA_PATH.read_text())
    defs = schema['$defs']
    variant = None
    for ref in schema['oneOf']:
        candidate = defs[ref['$ref'].split('/')[-1]]
        action = candidate['properties']['action']
        if action.get('const') == document['action'] or document['action'] in action.get('enum', []):
            variant = candidate
    assert variant is not None, 'no ScriptActionResult variant for ' + document['action']
    assert set(variant['required']) <= set(document), sorted(set(variant['required']) - set(document))
    assert set(document) <= set(variant['properties'])
    assert document['format'] == 'screenplan.action-result' and document['version'] == 1

    def check(value, definition, where):
        if '$ref' in definition:
            definition = defs[definition['$ref'].split('/')[-1]]
        if 'anyOf' in definition:
            if value is None:
                return
            definition = next(option for option in definition['anyOf'] if option.get('type') != 'null')
            return check(value, definition, where)
        if isinstance(value, dict) and 'properties' in definition:
            unknown = set(value) - set(definition['properties'])
            assert not unknown, '{} has fields the schema does not define: {}'.format(where, sorted(unknown))
            for key, item in value.items():
                check(item, definition['properties'][key], where + '.' + key)
        elif isinstance(value, list) and 'items' in definition:
            for index, item in enumerate(value):
                check(item, definition['items'], '{}[{}]'.format(where, index))

    check(document['fields'], defs[variant['properties']['fields']['$ref'].split('/')[-1]], 'fields')


def detect_action(group=1, **action_data):
    data = {'detectActionType': 'floatingObject', 'threshold': '0.8', 'maxMatches': 1, 'matchMode': 'bestMatch',
            'inputExpression': '', 'outputVarName': 'detectObject_out'}
    data.update(action_data)
    return {'actionName': 'detectObject', 'actionGroup': group, 'actionData': data, 'input_obj': {'fixed_scale': False}}


def test_every_action_has_one_at_info_and_none_at_error(configure_action, run_folder):
    prefix = configure_action('info', 'sleepStatement', 1)
    document = action_result_json(prefix)
    assert document == {
        'format': 'screenplan.action-result', 'version': 1,
        'action': 'sleepStatement', 'action_group': 1, 'script_counter': 1, 'fields': {}
    }
    check_against_schema(document)
    assert action_log_json(prefix)['supporting_files'] == [{'file_type': 'text', 'file_path': prefix + 'result.json'}]

    prefix = configure_action('error', 'sleepStatement', 2)
    action_log_json(prefix)
    assert not os.path.exists(prefix + 'result.json')


def test_fields_from_separate_copies_of_the_action_log_merge(configure_action):
    # A parallel detect runs in a worker process with a pickled copy of the
    # action log; the parent goes on with its own copy.
    prefix = configure_action('info', 'detectObject', 1)
    parent = configure_action.logger.get_action_log()
    worker = pickle.loads(pickle.dumps(parent))
    worker.update_result({'scene': {'score': 0.5, 'passed': False}, 'template': {'use_color': True}})
    parent.update_result({'template': {'match_count': 2}, 'matched': True})
    worker.update_result({'scene': {'rescaled': False}})

    fields = action_result_json(prefix)['fields']
    assert fields == {
        'scene': {'score': 0.5, 'passed': False, 'rescaled': False},
        'template': {'use_color': True, 'match_count': 2},
        'matched': True,
    }


def test_values_are_made_json_safe(configure_action):
    prefix = configure_action('info', 'colorCompareAction', 1)
    configure_action.logger.get_action_log().update_result({
        'score': np.float32(0.25), 'measured_color': np.array([1.5, 2, 3]), 'area': (1, 2), 'passed': np.bool_(True),
        'threshold': float('nan'),
    })
    assert action_result_json(prefix)['fields'] == {
        'score': 0.25, 'measured_color': [1.5, 2.0, 3.0], 'area': [1, 2], 'passed': True, 'threshold': None
    }


def test_detect_records_its_input_and_matches(configure_action, monkeypatch):
    import ScriptEngine.helpers.detect_object_helper as detect_object_helper_mod
    monkeypatch.setattr(detect_object_helper_mod, 'script_logger', configure_action.logger)
    capture = screenshot()
    prefix = configure_action('info', 'detectObject', 2)

    # An input expression pointing at an earlier match, and one that is blank.
    state = {'match': match_shape(capture, 60, 40, 120, 80), 'empty': {}}
    DetectObjectHelper.get_detect_area(detect_action(inputExpression='match'), state)
    assert action_result_json(prefix)['fields']['input'] == {
        'source': 'expression', 'expression': 'match', 'area': {'x': 60, 'y': 40, 'width': 120, 'height': 80}
    }
    DetectObjectHelper.get_detect_area(detect_action(inputExpression='empty'), state)
    assert action_result_json(prefix)['fields']['input']['source'] == 'blank'
    DetectObjectHelper.get_detect_area(detect_action(), state)
    assert action_result_json(prefix)['fields']['input'] == {'source': 'screenshot', 'expression': None, 'area': None}

    action = detect_action(group=2)
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger, action,
        detect_log_obj(capture, capture[100:130, 50:90].copy(),
                       [{'point': (50, 100), 'score': 0.95}, {'point': (200, 40), 'score': 0.9}])
    )
    document = action_result_json(prefix)
    assert document['fields']['matches'] == [
        {'x': 50, 'y': 100, 'width': 40, 'height': 30, 'score': 0.95},
        {'x': 200, 'y': 40, 'width': 40, 'height': 30, 'score': 0.9},
    ]
    assert document['fields']['best'] == {'x': 50, 'y': 100, 'score': 0.95}
    check_against_schema(document)


def test_detect_outcome_and_truncation(configure_action, monkeypatch):
    import ScriptEngine.helpers.detect_object_helper as detect_object_helper_mod
    monkeypatch.setattr(detect_object_helper_mod, 'script_logger', configure_action.logger)

    class IO:
        def submit(self, *args):
            return None

    prefix = configure_action('info', 'detectObject', 1)
    action = detect_action(maxMatches=1)
    matches = [{'point': (1, 1), 'score': 0.9}, {'point': (50, 50), 'score': 0.85}]
    DetectObjectHelper.handle_detect_action_result(IO(), (action, matches, {}), {}, {}, [])
    fields = action_result_json(prefix)['fields']
    assert (fields['matched'], fields['max_matches'], fields['excess_matches']) == (True, 1, 1)

    prefix = configure_action('info', 'detectObject', 2)
    DetectObjectHelper.handle_detect_action_result(IO(), (detect_action(), [], {}), {}, {}, [])
    assert action_result_json(prefix)['fields'] == {'matched': False}


def test_color_compare_records_the_colours_and_score(configure_action, monkeypatch):
    import ScriptEngine.helpers.color_compare_helper as color_compare_helper_mod
    monkeypatch.setattr(color_compare_helper_mod, 'script_logger', configure_action.logger)

    class IO:
        def submit(self, *args):
            return None

    prefix = configure_action('info', 'colorCompareAction', 1)
    area = np.full((10, 20, 3), (30, 60, 200), np.uint8)  # BGR
    action = {
        'actionData': {'compareMode': 'mean', 'referenceColor': [200, 60, 30]},
        'input_obj': {'screencap_im_bgr': area, 'match_point': (5, 7)},
    }
    score = ColorCompareHelper.handle_color_compare(action, IO())
    configure_action.logger.get_action_log().update_result({'threshold': 0.9, 'passed': score > 0.9})

    document = action_result_json(prefix)
    assert document['fields'] == {
        'compare_mode': 'mean',
        'reference_color': [200, 60, 30],
        'measured_color': [200.0, 60.0, 30.0],
        'score': pytest.approx(1.0),
        'area': {'x': 5, 'y': 7, 'width': 20, 'height': 10},
        'threshold': 0.9,
        'passed': True,
    }
    check_against_schema(document)


def test_ocr_runs_are_parsed_from_the_engine_lines():
    from ScriptEngine.helpers.image_to_text_action_helper import ImageToTextActionHelper
    lines = ('Running with psm 8 (word) characterWhiteList none and output was: 42\n'
             'Running easyOCR model with characterWhiteList 0123 and output was  12 3\n')
    assert ImageToTextActionHelper.ocr_runs(lines) == [
        {'settings': 'Running with psm 8 (word) characterWhiteList none', 'output': '42'},
        {'settings': 'Running easyOCR model with characterWhiteList 0123', 'output': ' 12 3'},
    ]


def test_written_results_match_the_schema(configure_action, run_folder, system_executor):
    """Every result file the other tests in this run folder produced."""
    capture = screenshot()
    state = {'match': match_shape(capture, 60, 40, 120, 80)}
    context = {'script_counter': 1, 'script_timer': 0}
    configure_action('info', 'imageToTextAction', 1)
    system_executor.handle_action({
        'actionName': 'imageToTextAction', 'actionGroup': 1,
        'actionData': {
            'targetSystem': 'none', 'inputExpression': 'match', 'outputVarName': 'text',
            'conversionEngine': 'tesseractOCR', 'characterWhiteList': '', 'targetType': 'word',
            'increaseContrast': True, 'invertColors': False,
        },
    }, state, context, [])
    action_log_json(configure_action('info', 'sleepStatement', 9))
    documents = [json.load(open(path)) for path in glob.glob(run_folder + '*result.json')]
    ocr = next(document for document in documents if document['action'] == 'imageToTextAction')
    assert ocr['fields']['engine'] == 'tesseractOCR'
    assert ocr['fields']['text'] == '42'
    assert ocr['fields']['preprocessing'][:2] == ['converted to grayscale', 'increased contrast']
    assert ocr['fields']['input']['source'] == 'expression'
    for document in documents:
        check_against_schema(document)
