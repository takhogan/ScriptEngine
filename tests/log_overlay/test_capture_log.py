"""Capture records: result version 2's capture (capture_log.py)."""
import re

import numpy as np

from ScriptEngine.common.logging.capture_log import (
    CAPTURE_LOG, CaptureLog, TAKEN_BY_ACTION, TAKEN_BY_LOGGER, note_input_sent, pixel_sha,
)
from ScriptEngine.common.screenshot_failures import ScreenshotFailureTracker
from ScriptEngine.device_controller import DeviceController
from ScriptEngine.helpers.detect_object_helper import DetectObjectHelper

from .test_action_result import check_against_schema, detect_action
from .test_overlay_logging import action_result_json, detect_log_obj  # noqa: F401 (fixture)
from .test_overlay_parity import screenshot

TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')


def test_a_recorded_screenshot_is_found_by_identity(configure_action):
    prefix = configure_action('info', 'detectObject', 7)
    captures = CaptureLog()
    image = screenshot()
    assert captures.record(image) is image
    record = captures.describe(image, prefix + 'capture.png')
    assert TIMESTAMP.match(record['captured_at'])
    assert record['taken_by'] == TAKEN_BY_ACTION
    assert record['taken_in'] == 7
    assert record['sha'] == pixel_sha(image)
    assert (record['width'], record['height']) == (image.shape[1], image.shape[0])


def test_a_copy_is_found_by_its_pixels():
    # A parallel detect's screenshot comes back from its worker as a copy.
    captures = CaptureLog()
    image = screenshot()
    captures.record(image, TAKEN_BY_LOGGER)
    record = captures.describe(image.copy(), '/tmp/x.png')
    assert record['taken_by'] == TAKEN_BY_LOGGER
    assert record['captured_at'] is not None


def test_an_image_that_is_no_screenshot_has_no_time():
    captures = CaptureLog()
    captures.record(screenshot())
    crop = screenshot()[10:50, 10:50].copy()
    record = captures.describe(crop, '/tmp/crop.png')
    assert record['captured_at'] is None and record['taken_by'] is None and record['taken_in'] is None
    assert record['sha'] == pixel_sha(crop)


def test_the_later_of_two_identical_screenshots_wins():
    captures = CaptureLog()
    first, second = screenshot(), screenshot()
    captures.record(first)
    captures.record(second, TAKEN_BY_LOGGER)
    assert captures.describe(first.copy(), '/tmp/x.png')['taken_by'] == TAKEN_BY_LOGGER


def _controller_with(device):
    class Stub:
        def initialize_device(self, device_type, device_params=None):
            return device

        def get_screenshot_failures(self, device_type, device_params=None):
            return ScreenshotFailureTracker('stub', limit_s=None)
    return Stub()


def test_the_device_controller_records_each_screenshot_and_its_taker():
    frames = []

    class Device:
        def screenshot(self):
            frames.append(np.full((20, 30, 3), len(frames) * 40, np.uint8))
            return frames[-1]

    stub = _controller_with(Device())
    for_action = DeviceController.get_device_action(stub, 'adb', 'screenshot')()
    for_logger = DeviceController.get_device_action(stub, 'adb', 'screenshot', taken_by=TAKEN_BY_LOGGER)()
    unrecorded = DeviceController.get_device_action(stub, 'adb', 'screenshot', taken_by=None)()
    assert CAPTURE_LOG.describe(for_action, '/tmp/a.png')['taken_by'] == TAKEN_BY_ACTION
    assert CAPTURE_LOG.describe(for_logger, '/tmp/b.png')['taken_by'] == TAKEN_BY_LOGGER
    assert CAPTURE_LOG.describe(unrecorded, '/tmp/c.png')['captured_at'] is None


def test_a_detect_result_carries_its_capture(configure_action, monkeypatch):
    import ScriptEngine.helpers.detect_object_helper as detect_object_helper_mod
    monkeypatch.setattr(detect_object_helper_mod, 'script_logger', configure_action.logger)
    capture = CAPTURE_LOG.record(screenshot())
    prefix = configure_action('info', 'detectObject', 3)
    DetectObjectHelper.create_detect_action_log_images(
        configure_action.logger, detect_action(group=3),
        detect_log_obj(capture, capture[100:130, 50:90].copy(), [{'point': (50, 100), 'score': 0.95}])
    )
    document = action_result_json(prefix)
    assert document['version'] == 2
    assert document['capture']['taken_by'] == TAKEN_BY_ACTION
    assert document['capture']['sha'] == pixel_sha(capture)
    assert document['capture']['path'].endswith('.png')
    check_against_schema(document)


def test_note_input_sent(configure_action):
    prefix = configure_action('info', 'mouseInteractionAction', 4)
    note_input_sent(configure_action.logger.get_action_log())
    note_input_sent(None)
    assert TIMESTAMP.match(action_result_json(prefix)['fields']['input_at'])
