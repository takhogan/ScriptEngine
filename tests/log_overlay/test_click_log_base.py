"""Click and drag logs are drawn on the screenshot their target was chosen from.

A target from an input expression is drawn on that match's screenshot, in its
coordinates, however it got there (directly from a detect, through a nested
detect, or through an imageTransformation). Only targets from the action's own
point list need a new screenshot, and their device coordinates are scaled to
it.
"""
import os

import cv2
import numpy as np
import pytest

import ScriptEngine.helpers.click_action_helper as click_action_helper_mod
from ScriptEngine.common.logging.log_overlay import read_overlay_document
from ScriptEngine.helpers.click_action_helper import ClickActionHelper
from ScriptEngine.script_action_executor import ScriptActionExecutor

from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper

from .test_overlay_logging import action_log_json, action_result_json, detect_log_obj, match_shape
from .test_overlay_parity import screenshot


class DeviceController:
    def __init__(self, width, height, screenshot_bgr=None, xmax=None, ymax=None):
        self.attrs = {'width': width, 'height': height, 'xmax': xmax or width, 'ymax': ymax or height}
        self.screenshot_bgr = screenshot_bgr
        self.screenshots_taken = 0

    def get_device_attribute(self, target, attr):
        return self.attrs[attr]

    def get_device_action(self, target, action_name):
        assert action_name == 'screenshot'

        def take_screenshot():
            self.screenshots_taken += 1
            return self.screenshot_bgr
        return take_screenshot


@pytest.fixture
def executor_for(configure_action, monkeypatch):
    monkeypatch.setattr(click_action_helper_mod, 'script_logger', configure_action.logger)

    def make(device_controller):
        return ScriptActionExecutor(
            device_controller=device_controller, io_executor=None,
            props={'scriptMode': 'test', 'script_name': 'script', 'dir_path': '/tmp'},
            screen_plan_server_attached=False,
        )
    return make


CLICK = {'actionName': 'mouseInteractionAction', 'actionData': {'targetSystem': 'desktop'}}


def choose(state, expression='', point_list=(), source_width=0, source_height=0, width=640, height=480, result_key='target'):
    detect_type_data = {
        'detectActionType': 'floatingObject',
        'positiveExamples': [{'floatingObject': {'sourceScreenWidth': source_width, 'sourceScreenHeight': source_height}}],
    }
    return ClickActionHelper.get_point_choice(
        detect_type_data, expression, list(point_list), state, width, height, 1, result_key=result_key
    )


def reorder(choice):
    """get_point_choice's result in the order draw_click takes it."""
    point_choice, log_point_choice, point_list, log_point_list = choice
    return point_choice, point_list, log_point_choice, log_point_list


def overlay_of(prefix, name='clickLocation'):
    log = action_log_json(prefix)
    return log, read_overlay_document(prefix + name + '.overlay.html')


def test_click_on_a_match_uses_its_screenshot_and_coordinates(configure_action, executor_for):
    # The match was found on a 320x240 screenshot; the device is 640x480, so
    # the click itself lands at twice the coordinates.
    capture = screenshot()
    state = {'match': match_shape(capture, 60, 40, 30, 20)}
    prefix = configure_action('info', 'mouseInteractionAction', 1)
    point_choice, log_point_choice, point_list, log_point_list = choose(state, 'match')
    assert point_choice[0] >= 120

    device = DeviceController(640, 480)
    executor_for(device).draw_click(CLICK, configure_action.logger, point_choice, point_list, log_point_choice, log_point_list)

    assert device.screenshots_taken == 0
    log, document = overlay_of(prefix)
    assert log['pre_file']['file_path'] == prefix + 'capture.png'
    assert (document['width'], document['height']) == (320, 240)
    target = action_result_json(prefix)['fields']['target']
    x, y = target['screenshot_point']['x'], target['screenshot_point']['y']
    assert 60 <= x < 90 and 40 <= y < 60
    assert target['input_type'] == 'shape' and target['source'] == 'expression'
    # The device point is the screenshot point scaled to the device.
    assert target['remapped'] is True
    assert target['point'] == {'x': point_choice[0], 'y': point_choice[1]}
    assert target['source_screen'] == {'width': 320, 'height': 240}
    assert target['device_screen'] == {'width': 640, 'height': 480}


def test_click_reuses_the_detects_screenshot_file(configure_action, executor_for):
    capture = screenshot()
    detect_prefix = configure_action('info', 'detectObject', 1)
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger,
        {'actionGroup': 1, 'actionData': {'detectActionType': 'floatingObject', 'threshold': '0.8', 'maxMatches': 1},
         'input_obj': {'fixed_scale': False}},
        detect_log_obj(capture, capture[40:60, 60:90].copy(), [{'point': (60, 40), 'score': 0.9}])
    )

    state = {'match': match_shape(capture, 60, 40, 30, 20)}
    prefix = configure_action('info', 'mouseInteractionAction', 2)
    executor_for(DeviceController(320, 240)).draw_click(CLICK, configure_action.logger, *reorder(choose(state, 'match', width=320, height=240)))

    log, document = overlay_of(prefix)
    assert log['pre_file']['file_path'] == detect_prefix + 'capture.png'
    assert document['images']['capture']['path'] == detect_prefix + 'capture.png'


def test_click_on_a_transformed_match_uses_the_original_screenshot(configure_action, executor_for):
    capture = screenshot()
    match = match_shape(capture, 60, 40, 30, 20)
    # What imageTransformation stores: a copy of the match with a new matched_area.
    transformed = dict(match, matched_area=np.zeros((40, 60, 3), np.uint8), height=40, width=60)
    prefix = configure_action('info', 'mouseInteractionAction', 1)
    executor_for(DeviceController(320, 240)).draw_click(
        CLICK, configure_action.logger, *reorder(choose({'t': transformed}, 't', width=320, height=240))
    )

    log, document = overlay_of(prefix)
    assert np.array_equal(cv2.imread(log['pre_file']['file_path']), capture)
    point = action_result_json(prefix)['fields']['target']['screenshot_point']
    x, y = point['x'], point['y']
    assert 60 <= x < 90 and 40 <= y < 60


@pytest.mark.parametrize('screenshot_size', [(640, 480), (1280, 960)])
def test_click_from_a_point_list_draws_device_coordinates_on_a_new_screenshot(configure_action, executor_for, screenshot_size):
    # Authored on a 320x240 screen, run on a 640x480 device. The screenshot
    # can be larger than the device's coordinate space (HiDPI).
    points = [(10, 10), (20, 30), (40, 50)]
    prefix = configure_action('info', 'mouseInteractionAction', 1)
    point_choice, log_point_choice, point_list, log_point_list = choose(
        {}, point_list=points, source_width=320, source_height=240
    )
    width, height = screenshot_size
    device = DeviceController(640, 480, screenshot_bgr=screenshot(height, width))
    executor_for(device).draw_click(CLICK, configure_action.logger, point_choice, point_list, log_point_choice, log_point_list)

    assert device.screenshots_taken == 1
    log, document = overlay_of(prefix)
    scale = width / 640
    target = action_result_json(prefix)['fields']['target']
    assert target['screenshot_point'] == {'x': int(point_choice[0] * scale), 'y': int(point_choice[1] * scale)}
    assert target['source'] == 'point_list' and target['candidate_count'] == 3 and target['remapped'] is True
    group = next(layer for layer in document['layers'] if layer['op'] == 'group')
    assert [layer['center'] for layer in group['layers']] == [
        [int(x * 2 * scale), int(y * 2 * scale)] for x, y in points
    ]


def test_click_without_a_point_logs_nothing(configure_action, executor_for, run_folder):
    prefix = configure_action('info', 'mouseInteractionAction', 1)
    executor_for(DeviceController(320, 240, screenshot())).draw_click(
        CLICK, configure_action.logger, (None, None), [], (None, None), []
    )
    assert action_log_json(prefix)['post_file'] == {}
    assert not [name for name in os.listdir(run_folder) if name.endswith('.html')]


def test_drag_from_a_match_to_a_point_list(configure_action, executor_for):
    # Match on a 320x240 screenshot; the device is 640x480 and reports drag
    # deltas in input units up to 1280x960, so one unit is half a screen pixel.
    capture = screenshot()
    state = {'match': match_shape(capture, 60, 40, 30, 20)}
    prefix = configure_action('info', 'mouseMoveAction', 1)
    source = reorder(choose(state, 'match', result_key='source'))
    target = reorder(choose({}, point_list=[(200, 150)], source_width=640, source_height=480))
    # The device moved from the source to the target in two steps, in input units.
    total_x = (target[0][0] - source[0][0]) * 2
    total_y = (target[0][1] - source[0][1]) * 2
    delta_x, delta_y = [total_x / 2, total_x / 2], [total_y / 2, total_y / 2]

    device = DeviceController(640, 480, xmax=1280, ymax=960)
    executor_for(device).draw_click_and_drag(
        {'actionName': 'mouseMoveAction', 'actionData': {'targetSystem': 'desktop'}},
        configure_action.logger, source, target, delta_x, delta_y
    )

    assert device.screenshots_taken == 0
    log, document = overlay_of(prefix, 'dragPath')
    assert log['pre_file']['file_path'] == prefix + 'capture.png'
    fields = action_result_json(prefix)['fields']
    path = fields['path']
    # Starts at the match's own point, ends at the target scaled into the screenshot.
    assert path[0] == {'x': int(source[2][0]), 'y': int(source[2][1])}
    assert abs(path[-1]['x'] - 100) <= 1 and abs(path[-1]['y'] - 75) <= 1
    assert fields['target']['screenshot_point'] == {'x': 100, 'y': 75}
    assert fields['source']['source'] == 'expression' and fields['target']['source'] == 'point_list'
