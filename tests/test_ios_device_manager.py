"""Unit tests for the read-only iOS device manager.

Nothing here talks to a device. The pymobiledevice3 services are patched out at
the manager's own seams (_connect, _capture_png, usbmux.list_devices), which is
the only way to cover the paths that matter without an iPhone on the bench.
"""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from ScriptEngine.device_controller import DeviceController
from ScriptEngine.managers.ios_device_manager import IOSDeviceManager, IOSInputUnsupportedError

UDID = '00008030-001A2B3C4D5E6F70'
DEVICE_ID = 'ios:' + UDID


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """Give the shared ScriptLogger a file to write to.

    It is a singleton whose writer thread starts on first use with log_file_path
    unset, so the manager's own log lines make that thread raise and print a
    traceback after the run. The failure is in the logger, not in what is being
    tested, but it is noisy enough to hide a real one.
    """
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('ios-logs') / 'test.txt'))
    return logger


def base_props():
    return {'width': None, 'height': None, 'scriptMode': 'train', 'dir_path': '.'}


def png_bytes(width, height, rgb=(255, 0, 0)):
    """A solid-colour PNG, as the screenshot services return one."""
    buffer = BytesIO()
    Image.new('RGB', (width, height), rgb).save(buffer, format='PNG')
    return buffer.getvalue()


def offline_manager(device_params=None, **kwargs):
    """A manager that never connects, for the paths that do not need a device."""
    return IOSDeviceManager(base_props(), device_params or {'deviceId': DEVICE_ID}, **kwargs)


# --------------------------------------------------------------------- identity


def test_udid_comes_from_the_device_id_prefix():
    assert offline_manager().udid == UDID


def test_an_explicit_udid_field_wins_over_the_device_id():
    manager = offline_manager({'deviceId': 'ios:stale-id', 'udid': UDID})

    assert manager.udid == UDID


def test_a_human_device_name_is_never_treated_as_a_udid():
    # The controller stores a nickname on an iOS record; the adb manager uses
    # deviceName for an emulator name. Accepting it here would drive whatever
    # device a nickname happened to match.
    manager = offline_manager({'deviceId': DEVICE_ID, 'deviceName': "Tak's iPhone"})

    assert manager.udid == UDID


def test_a_device_id_without_a_udid_is_refused():
    with pytest.raises(Exception, match='could not work out which device'):
        offline_manager({'deviceId': 'ios'})


def test_a_run_with_no_device_configuration_is_refused():
    # The message has to name the requirement, not the empty params dict it
    # produced: this is what a script with iOS actions and no attached device hits.
    with pytest.raises(Exception, match='requires an iOS device'):
        IOSDeviceManager(base_props(), {})


# ------------------------------------------------------------------- dummy mode


def dummy_input_source(width=390, height=844):
    image = np.zeros((height, width, 3), dtype=np.uint8)
    return {'width': width, 'height': height, 'screenshot': lambda: image}


def test_dummy_mode_takes_its_dimensions_from_the_input_source():
    manager = IOSDeviceManager(base_props(), {}, input_source=dummy_input_source())

    assert manager.dummy_mode is True
    assert (manager.width, manager.height) == (390, 844)


def test_dummy_mode_screenshot_returns_the_input_source_image():
    input_source = dummy_input_source()
    manager = IOSDeviceManager(base_props(), {}, input_source=input_source)

    assert manager.screenshot() is input_source['screenshot']()


def test_dummy_mode_never_reaches_the_device():
    manager = IOSDeviceManager(base_props(), {}, input_source=dummy_input_source())

    assert manager.get_status() == 'online'
    assert manager.list_applications() == {}
    # Both are no-ops rather than errors, so a mock run of a script that launches
    # an app still exercises the rest of the script.
    assert manager.start_application('com.example.app', None) is None
    assert manager.stop_application('com.example.app') is None


# ---------------------------------------------------------------- image decoding


def test_png_is_decoded_to_a_bgr_array():
    # Pure red arrives as RGB and has to come out as BGR, because every consumer
    # of screenshot() is OpenCV code that indexes channel 2 for red.
    image = IOSDeviceManager._png_to_bgr(png_bytes(4, 7, rgb=(255, 0, 0)))

    assert image.shape == (7, 4, 3)
    assert tuple(image[0][0]) == (0, 0, 255)


# --------------------------------------------------------------- initialization


@pytest.fixture
def connected_manager(monkeypatch):
    """A manager whose connection is stubbed out and whose screen is 1170x2532.

    1170x2532 is an iPhone 13 Pro: a 3x device, so the pixel dimensions the engine
    works in are deliberately not the point dimensions WebDriverAgent would report.
    """
    manager = offline_manager()
    monkeypatch.setattr(manager, '_connect', lambda: setattr(manager, 'service_provider', object()))
    monkeypatch.setattr(manager, '_capture_png', lambda: png_bytes(1170, 2532))
    monkeypatch.setattr(manager, 'get_screen_orientation', lambda: 1)
    return manager


def test_initialization_takes_the_screen_size_from_the_screenshot(connected_manager):
    connected_manager.ensure_device_initialized()

    assert (connected_manager.width, connected_manager.height) == (1170, 2532)


def test_initialization_fills_in_unset_props(connected_manager):
    connected_manager.ensure_device_initialized()

    assert connected_manager.props['width'] == 1170
    assert connected_manager.props['height'] == 2532


def test_initialization_leaves_props_the_script_already_set(connected_manager):
    connected_manager.props['width'] = 1125
    connected_manager.props['height'] = 2436

    connected_manager.ensure_device_initialized()

    assert (connected_manager.props['width'], connected_manager.props['height']) == (1125, 2436)


def test_the_pixel_to_point_scale_is_left_unset(connected_manager):
    # Phase 1 has no input and no WebDriverAgent to ask for the point size, so the
    # scale is None rather than a guess. Phase 2 fills it in; this test is here so
    # that a later change has to say so deliberately.
    connected_manager.ensure_device_initialized()

    assert connected_manager.scale_factor is None


def test_initialization_only_captures_once(connected_manager, monkeypatch):
    captures = []
    monkeypatch.setattr(
        connected_manager, '_capture_png', lambda: captures.append(1) or png_bytes(1170, 2532)
    )

    connected_manager.ensure_device_initialized()
    connected_manager.ensure_device_initialized()

    assert len(captures) == 1


def test_reinitialize_drops_the_cached_connection(connected_manager, monkeypatch):
    resets = []
    connected_manager.ensure_device_initialized()
    monkeypatch.setattr(connected_manager, '_reset_connection', lambda: resets.append(1))

    connected_manager.ensure_device_initialized(reinitialize=True)

    assert len(resets) == 1


def test_reset_closes_an_rsd_provider():
    # On iOS 17+ the provider is an RSD whose close() is a coroutine; left
    # unawaited it leaks the tunnel connection on every reconnect.
    closed = []

    class FakeRsd:
        async def close(self):
            closed.append(1)

    manager = offline_manager()
    manager.service_provider = FakeRsd()

    manager._reset_connection()

    assert closed == [1]
    assert manager.service_provider is None


def test_reset_does_not_double_close_a_lockdown_provider():
    # Below iOS 17 the provider *is* the lockdown client, which the loop above
    # already closed, and whose close() is not a coroutine.
    closed = []

    class FakeLockdown:
        def close(self):
            closed.append(1)

    manager = offline_manager()
    manager.lockdown = FakeLockdown()
    manager.service_provider = manager.lockdown

    manager._reset_connection()

    assert closed == [1]


# ------------------------------------------------------------------- screenshots


def test_screenshot_returns_a_bgr_frame(connected_manager):
    frame = connected_manager.screenshot()

    assert frame.shape == (2532, 1170, 3)


def test_a_failed_capture_reconnects_and_retries(connected_manager, monkeypatch):
    # A DVT channel going stale after the device locks or the tunnel restarts is
    # the common failure, and it clears on reconnect.
    connected_manager.ensure_device_initialized()
    attempts = []

    def flaky_capture():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('stale channel')
        return png_bytes(1170, 2532)

    monkeypatch.setattr(connected_manager, '_capture_png', flaky_capture)
    monkeypatch.setattr(connected_manager, '_reset_connection', lambda: None)

    frame = connected_manager.screenshot()

    assert len(attempts) == 2
    assert frame.shape == (2532, 1170, 3)


def test_a_capture_that_keeps_failing_fails_the_run(connected_manager, monkeypatch):
    connected_manager.ensure_device_initialized()

    def dead_capture():
        raise OSError('device gone')

    monkeypatch.setattr(connected_manager, '_capture_png', dead_capture)
    monkeypatch.setattr(connected_manager, '_reset_connection', lambda: None)

    with pytest.raises(OSError, match='device gone'):
        connected_manager.screenshot()


# ------------------------------------------------------------------------ status


def test_status_is_offline_when_the_device_is_not_attached(monkeypatch):
    import ScriptEngine.managers.ios_device_manager as ios_mod

    manager = offline_manager()
    monkeypatch.setattr(ios_mod.usbmux, 'list_devices', lambda: [])

    assert manager.get_status() == 'offline'


def test_status_is_online_when_the_device_is_attached_and_reachable(monkeypatch):
    import ScriptEngine.managers.ios_device_manager as ios_mod

    class FakeMuxDevice:
        serial = UDID

    manager = offline_manager()
    monkeypatch.setattr(ios_mod.usbmux, 'list_devices', lambda: [FakeMuxDevice()])
    monkeypatch.setattr(manager, '_connect', lambda: setattr(manager, 'service_provider', object()))

    assert manager.get_status() == 'online'


def test_status_is_offline_when_the_services_cannot_be_reached(monkeypatch):
    # An iOS 17+ device whose tunnel has gone away is still listed by usbmux, so
    # reporting on the listing alone would say online and then fail every capture.
    import ScriptEngine.managers.ios_device_manager as ios_mod

    class FakeMuxDevice:
        serial = UDID

    def no_tunnel():
        raise Exception('no tunneld is running')

    manager = offline_manager()
    monkeypatch.setattr(ios_mod.usbmux, 'list_devices', lambda: [FakeMuxDevice()])
    monkeypatch.setattr(manager, '_connect', no_tunnel)

    assert manager.get_status() == 'offline'


# ------------------------------------------------------------------- input: n/a


@pytest.mark.parametrize('call', [
    lambda m: m.click(10, 20, 'left'),
    lambda m: m.click_and_drag(10, 20, 30, 40),
    lambda m: m.smooth_move(10, 20, 30, 40),
    lambda m: m.mouse_down(10, 20),
    lambda m: m.mouse_up(10, 20),
    lambda m: m.scroll(10, 20, 5),
    lambda m: m.key_press('a'),
    lambda m: m.key_down('a'),
    lambda m: m.key_up('a'),
    lambda m: m.hotkey(['ctrl', 'a']),
])
def test_input_actions_name_webdriveragent(call):
    # Its own exception type, and a message that names the prerequisite: silently
    # falling back to pyautogui here would drive the host desktop, not the phone.
    manager = offline_manager()

    with pytest.raises(IOSInputUnsupportedError, match='WebDriverAgent'):
        call(manager)


# ---------------------------------------------------------- device power is n/a


def test_device_power_actions_are_no_ops():
    manager = offline_manager()

    assert manager.start_device() is None
    assert manager.stop_device() is None


# ------------------------------------------------------- device type resolution


def test_an_ios_device_id_resolves_to_the_ios_device_type():
    controller = DeviceController.__new__(DeviceController)

    assert controller.device_id_to_device_type(DEVICE_ID) == 'ios'


@pytest.mark.parametrize('device_id,expected', [
    ('avd:Pixel_7', 'adb'),
    ('bluestacks:Pie64', 'adb'),
    ('adb:serial-192.168.1.5:5555', 'adb'),
    ('pikvm:serial-10.0.0.2', 'kvm'),
    ('MyDesktop', 'python'),
])
def test_the_existing_device_types_still_resolve(device_id, expected):
    controller = DeviceController.__new__(DeviceController)

    assert controller.device_id_to_device_type(device_id) == expected


def test_an_unknown_prefix_names_itself():
    # This used to raise UnboundLocalError, which named neither the device nor the
    # prefix that was not understood.
    controller = DeviceController.__new__(DeviceController)

    with pytest.raises(Exception, match="unrecognized type prefix 'windows'"):
        controller.device_id_to_device_type('windows:some-host')
