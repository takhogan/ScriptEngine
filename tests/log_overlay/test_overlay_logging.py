"""What the action log records for overlay-backed post images, per log level."""
import json
import os

import cv2
import numpy as np
import pytest

from ScriptEngine.common.logging import script_action_log as script_action_log_mod
from ScriptEngine.common.logging.log_overlay import (
    OVERLAY_FILE_TYPE, Overlay, overlay_html, read_overlay_document,
)
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.helpers.click_action_helper import ClickActionHelper
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper

from .test_overlay_parity import screenshot

POINT_LIST = {'input_type': 'rectangle', 'point': (100, 50), 'width': 60, 'height': 40}


def action_log_json(prefix):
    script_action_log_mod._log_executor.submit(lambda: None).result()
    with open(prefix + 'action-log.json') as action_log_file:
        return json.load(action_log_file)


def test_info_keeps_the_screenshot_and_an_overlay(configure_action):
    prefix = configure_action('info', 'mouseInteractionAction', 1)
    ClickActionHelper.draw_click(screenshot(), (120, 70), POINT_LIST)

    log = action_log_json(prefix)
    assert log['pre_file'] == {'file_type': 'image', 'file_path': prefix + 'capture.png'}
    assert log['post_file'] == {'file_type': OVERLAY_FILE_TYPE, 'file_path': prefix + 'clickLocation.overlay.html'}
    assert log['supporting_files'] == []
    assert np.array_equal(cv2.imread(prefix + 'capture.png'), screenshot())
    assert not os.path.exists(prefix + 'clickLocation.png')

    document = read_overlay_document(prefix + 'clickLocation.overlay.html')
    assert document['images']['capture']['href'] == os.path.basename(prefix) + 'capture.png'


def test_debug_also_keeps_the_rendered_png(configure_action):
    prefix = configure_action('debug', 'mouseInteractionAction', 1)
    ClickActionHelper.draw_click(screenshot(), (120, 70), POINT_LIST)

    log = action_log_json(prefix)
    assert log['post_file']['file_type'] == OVERLAY_FILE_TYPE
    assert {'file_type': 'image', 'file_path': prefix + 'clickLocation.png'} in log['supporting_files']
    assert cv2.imread(prefix + 'clickLocation.png') is not None


def test_error_writes_no_images(configure_action, run_folder):
    prefix = configure_action('error', 'mouseInteractionAction', 1)
    ClickActionHelper.draw_click(screenshot(), (120, 70), POINT_LIST)

    log = action_log_json(prefix)
    assert log['pre_file'] == {} and log['post_file'] == {}
    assert not [name for name in os.listdir(run_folder) if name.endswith(('.png', '.html'))]


def test_actions_sharing_a_screenshot_store_it_once(configure_action, run_folder):
    capture = screenshot()
    first_prefix = configure_action('info', 'mouseInteractionAction', 1)
    ClickActionHelper.draw_click(capture, (120, 70), POINT_LIST)
    second_prefix = configure_action('info', 'mouseInteractionAction', 2)
    ClickActionHelper.draw_click(capture, (10, 10), POINT_LIST)

    assert action_log_json(second_prefix)['pre_file']['file_path'] == first_prefix + 'capture.png'
    document = read_overlay_document(second_prefix + 'clickLocation.overlay.html')
    assert document['images']['capture']['href'] == os.path.basename(first_prefix) + 'capture.png'
    assert [name for name in os.listdir(run_folder) if name.endswith('.png')] == [os.path.basename(first_prefix) + 'capture.png']


def test_detect_log_images_at_info(configure_action):
    prefix = configure_action('info', 'detectObject', 1)
    capture = screenshot()
    template = capture[100:130, 50:90].copy()
    action = {
        'actionGroup': 1,
        'actionData': {'detectActionType': 'floatingObject', 'threshold': '0.8', 'maxMatches': 1},
        'input_obj': {'fixed_scale': False},
    }
    log_obj = {
        'base': (capture, {'img': template, 'mask_single_channel': np.zeros((30, 40), np.uint8)}, (0, 0)),
        'fixedObject': None,
        'floatingObject': ([{'point': (50, 100), 'score': 0.95}], None),
    }
    DetectObjectHelper.create_detect_action_log_images(ScriptLogger.get_logger(), action, log_obj)

    log = action_log_json(prefix)
    assert log['pre_file']['file_path'] == prefix + 'capture.png'
    assert log['post_file']['file_path'] == prefix + 'detectObject-matchOverlayed.overlay.html'
    document = read_overlay_document(log['post_file']['file_path'])
    assert set(document['images']) == {'capture', 'template'}
    assert os.path.exists(prefix + 'template.png')
    # templateImage.png is still debug-only.
    assert not os.path.exists(prefix + 'templateImage.png')


def test_html_data_block_survives_script_end_tags(tmp_path):
    overlay = Overlay('test', 2, 2)
    overlay.meta = {'note': '</script><script>alert(1)</script>'}
    html = overlay_html(overlay.to_document({}), 'a <b> & c')
    assert html.count('</script>') == 2  # the data block's and the renderer's
    assert '<title>a &lt;b> &amp; c</title>' in html
    path = tmp_path / 'test.overlay.html'
    path.write_text(html, encoding='utf-8')
    assert read_overlay_document(str(path))['meta']['note'] == overlay.meta['note']


def test_store_never_overwrites_a_referenced_file(tmp_path):
    from ScriptEngine.common.logging.log_overlay import LogImageStore
    store = LogImageStore()
    first, second = screenshot(seed=1), screenshot(seed=2)
    path = str(tmp_path / 'capture.png')
    assert store.write(first, path) == path
    assert store.write(first, path) == path
    other_path = store.write(second, path)
    assert other_path == str(tmp_path / 'capture-2.png')
    assert np.array_equal(cv2.imread(path), first)
    assert np.array_equal(cv2.imread(other_path), second)


# ---------------------------------------------------------------------------
# Chained inputs: an action whose input is an earlier action's output records
# that output as its pre_file, not the screenshot behind it.
# ---------------------------------------------------------------------------

def detect_log_obj(input_image, template, matches, match_point=(0, 0)):
    return {
        'base': (input_image, {'img': template, 'mask_single_channel': np.zeros(template.shape[:2], np.uint8)}, match_point),
        'fixedObject': None,
        'floatingObject': (matches, None),
    }


def chained_detect(input_area, point, capture):
    return {
        'actionGroup': 2,
        'actionData': {'detectActionType': 'floatingObject', 'threshold': '0.8', 'maxMatches': 1},
        'input_obj': {
            'fixed_scale': True,
            'original_image': capture,
            'original_image_blurred': cv2.GaussianBlur(capture, (31, 31), 0, borderType=cv2.BORDER_REPLICATE),
        },
    }


def match_shape(capture, x, y, w, h):
    """A detect match as it is stored in state for later actions."""
    return {
        'input_type': 'shape', 'point': (x, y),
        'matched_area': capture[y:y + h, x:x + w],
        'output_mask': np.full((h, w), 255, np.uint8),
        'height': h, 'width': w,
        'original_image': capture, 'original_image_blurred': None,
        'original_height': capture.shape[0], 'original_width': capture.shape[1],
    }


def test_detect_on_an_earlier_detects_match(configure_action):
    capture = screenshot()
    first_prefix = configure_action('info', 'detectObject', 1)
    first = {
        'actionGroup': 1,
        'actionData': {'detectActionType': 'floatingObject', 'threshold': '0.8', 'maxMatches': 1},
        'input_obj': {'fixed_scale': False},
    }
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger, first,
        detect_log_obj(capture, capture[40:120, 60:180].copy(), [{'point': (60, 40), 'score': 0.9}])
    )

    shape = match_shape(capture, 60, 40, 120, 80)
    second_prefix = configure_action('info', 'detectObject', 2)
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger, chained_detect(shape['matched_area'], (60, 40), capture),
        detect_log_obj(shape['matched_area'], capture[50:70, 70:100].copy(), [{'point': (70, 50), 'score': 0.95}], (60, 40))
    )

    assert action_log_json(first_prefix)['pre_file']['file_path'] == first_prefix + 'capture.png'
    second = action_log_json(second_prefix)
    # The second detect consumed the first one's match, so that is its input.
    assert second['pre_file']['file_path'] == second_prefix + 'input.png'
    assert np.array_equal(cv2.imread(second_prefix + 'input.png'), shape['matched_area'])
    # The screenshot behind it is the first detect's file, referenced for context.
    document = read_overlay_document(second['post_file']['file_path'])
    assert document['images']['capture']['path'] == first_prefix + 'capture.png'


@pytest.fixture
def system_executor(configure_action, monkeypatch):
    import ScriptEngine.system_script_action_executor as ssae_mod
    import ScriptEngine.helpers.detect_object_helper as detect_object_helper_mod
    import ScriptEngine.helpers.image_to_text_action_helper as image_to_text_mod
    from ScriptEngine.system_script_action_executor import SystemScriptActionExecutor

    for module in (ssae_mod, detect_object_helper_mod, image_to_text_mod):
        monkeypatch.setattr(module, 'script_logger', configure_action.logger)
    monkeypatch.setattr(
        image_to_text_mod.ImageToTextActionHelper, 'run_tesseract_ocr',
        staticmethod(lambda action, image, debug: (['42'], '', ''))
    )

    class IOExecutor:
        def submit(self, fn, *args):
            return None

    return SystemScriptActionExecutor(
        base_script_name='script', props={'dir_path': '/tmp'}, io_executor=IOExecutor(), screen_plan_server_attached=False
    )


def test_actions_on_an_image_transformation_output(configure_action, system_executor):
    capture = screenshot()
    state = {'match': match_shape(capture, 60, 40, 120, 80)}
    context = {'script_counter': 1, 'script_timer': 0}

    transform_prefix = configure_action('info', 'imageTransformationAction', 1)
    system_executor.handle_action({
        'actionName': 'imageTransformationAction', 'actionGroup': 1,
        'actionData': {
            'targetSystem': 'none', 'inputExpression': 'match', 'outputVarName': 'transformed',
            'transformationType': 'resize', 'resizeScaleFactor': '2',
        },
    }, state, context, [])
    transform_log = action_log_json(transform_prefix)
    assert transform_log['pre_file']['file_path'] == transform_prefix + 'imageTransformationAction-input.png'
    output_path = transform_log['post_file']['file_path']
    assert np.array_equal(cv2.imread(output_path), state['transformed']['matched_area'])

    # OCR on the transformed image: its input file is the transformation's output.
    ocr_prefix = configure_action('info', 'imageToTextAction', 2)
    system_executor.handle_action({
        'actionName': 'imageToTextAction', 'actionGroup': 2,
        'actionData': {
            'targetSystem': 'none', 'inputExpression': 'transformed', 'outputVarName': 'text',
            'conversionEngine': 'tesseractOCR', 'characterWhiteList': '', 'targetType': 'word',
            'increaseContrast': False, 'invertColors': False,
        },
    }, state, context, [])
    assert state['text'] == '42'
    assert action_log_json(ocr_prefix)['pre_file']['file_path'] == output_path

    # A detect on the transformed image: the same file again, with the
    # original screenshot for context.
    transformed = state['transformed']
    detect_prefix = configure_action('info', 'detectObject', 3)
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger, chained_detect(transformed['matched_area'], transformed['point'], capture),
        detect_log_obj(transformed['matched_area'], transformed['matched_area'][10:40, 10:50].copy(),
                       [{'point': (70, 50), 'score': 0.95}], transformed['point'])
    )
    detect_log = action_log_json(detect_prefix)
    assert detect_log['pre_file']['file_path'] == output_path
    document = read_overlay_document(detect_log['post_file']['file_path'])
    assert document['images']['input']['path'] == output_path
    assert np.array_equal(cv2.imread(document['images']['capture']['path']), capture)
