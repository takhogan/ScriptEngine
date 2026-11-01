"""Unit tests for the Add Device form's iOS prerequisite checks.

Nothing here talks to a device: usbmux and the lockdown client are patched out,
which is the only way to cover an unpaired phone, an iOS 15 phone and a missing
tunnel from one machine.
"""

import json

import pytest

from ScriptEngine.helpers import ios_setup_helper as helper

UDID = '00008030-001A2B3C4D5E6F70'


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """Give the shared ScriptLogger a file to write to; see test_ios_device_manager."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('ios-setup-logs') / 'test.txt'))
    return logger


class FakeMuxDevice:
    def __init__(self, serial=UDID, connection_type='USB'):
        self.serial = serial
        self.connection_type = connection_type

    def matches_udid(self, udid):
        return self.serial.replace('-', '') == udid.replace('-', '')


class FakeLockdown:
    def __init__(self, paired=True, product_version='17.4', developer_mode_status=True, name='Test iPhone'):
        self.paired = paired
        self.product_version = product_version
        self.developer_mode_status = developer_mode_status
        self.product_type = 'iPhone15,2'
        self.all_values = {'DeviceName': name} if paired else {}
        self.closed = False

    def close(self):
        self.closed = True


class FakeMounter:
    """Stands in for DeveloperDiskImageMounter / PersonalizedImageMounter."""

    mounted = True
    IMAGE_TYPE = 'Personalized'

    def __init__(self, lockdown=None):
        self.lockdown = lockdown

    def is_image_mounted(self, image_type):
        assert image_type == self.IMAGE_TYPE
        return self.mounted


@pytest.fixture
def device(monkeypatch):
    """One attached, paired iOS 17 device with everything satisfied but the tunnel."""
    lockdown = FakeLockdown()
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [FakeMuxDevice()])
    monkeypatch.setattr(helper, '_open_lockdown', lambda *args, **kwargs: lockdown)
    monkeypatch.setattr(
        'pymobiledevice3.services.mobile_image_mounter.PersonalizedImageMounter', FakeMounter
    )
    monkeypatch.setattr(
        'pymobiledevice3.services.mobile_image_mounter.DeveloperDiskImageMounter', FakeMounter
    )
    FakeMounter.mounted = True
    return lockdown


@pytest.fixture
def tunnel_up(monkeypatch):
    """A tunneld answering on loopback with a tunnel for this device."""
    def fake_urlopen(url, timeout=None):
        class Response:
            def read(self):
                return json.dumps({UDID: [{'tunnel-address': 'fdxx::1', 'tunnel-port': 1234}]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        return Response()

    monkeypatch.setattr(helper, 'urlopen', fake_urlopen)


@pytest.fixture
def tunnel_down(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise OSError('connection refused')

    monkeypatch.setattr(helper, 'urlopen', fake_urlopen)


def checks_by_id(result):
    return {check['id']: check for check in result['checks']}


# ------------------------------------------------------------------- dispatching


def test_the_controllers_action_list_matches_the_handlers():
    # device_controller names the actions itself so that dispatching a request
    # does not import pymobiledevice3; the two lists have to agree or an action
    # the controller accepts has nowhere to go.
    from ScriptEngine.device_controller import IOS_SETUP_ACTIONS

    assert set(IOS_SETUP_ACTIONS) == set(helper.SETUP_ACTIONS)


def test_an_unknown_action_is_reported_not_raised():
    result = helper.run_setup_action('ios_make_coffee')

    assert result['ok'] is False
    assert 'ios_make_coffee' in result['message']


def test_a_handler_that_raises_is_reported_not_raised(monkeypatch):
    def explode(udid=None):
        raise RuntimeError('usbmuxd went away')

    monkeypatch.setitem(helper.SETUP_ACTIONS, 'ios_list_devices', explode)
    result = helper.run_setup_action('ios_list_devices')

    assert result['ok'] is False
    assert 'usbmuxd went away' in result['message']


def test_every_action_accepts_a_udid():
    # run_setup_action passes one to whichever handler it dispatches to, so a
    # handler that did not take one would fail only when its button was pressed.
    for handler in helper.SETUP_ACTIONS.values():
        handler(None)


# --------------------------------------------------------------------- discovery


def test_a_device_on_usb_and_wifi_is_listed_once(device, monkeypatch):
    monkeypatch.setattr(
        helper.usbmux, 'list_devices',
        lambda: [FakeMuxDevice(connection_type='Network'), FakeMuxDevice(connection_type='USB')]
    )
    result = helper.list_attached_devices()

    assert len(result['devices']) == 1
    # USB wins whichever order usbmuxd reports them in: it is the connection the
    # prerequisites are about.
    assert result['devices'][0]['connectionType'] == 'USB'
    assert sorted(result['devices'][0]['connectionTypes']) == ['Network', 'USB']


def test_an_unpaired_device_is_still_listed(monkeypatch):
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [FakeMuxDevice()])
    monkeypatch.setattr(helper, '_open_lockdown', lambda *args, **kwargs: FakeLockdown(paired=False))
    result = helper.list_attached_devices()

    # It is exactly the device being set up, so hiding it would be perverse. With
    # no pairing there is no name to show, so the UDID is the label.
    assert result['devices'][0]['paired'] is False
    assert result['devices'][0]['label'] == UDID


def test_no_devices_says_so_without_failing(monkeypatch):
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [])
    result = helper.list_attached_devices()

    assert result['ok'] is True
    assert result['devices'] == []
    assert 'USB' in result['message']


def test_usbmuxd_being_unreachable_is_reported(monkeypatch):
    def explode():
        raise ConnectionRefusedError('no usbmuxd')

    monkeypatch.setattr(helper.usbmux, 'list_devices', explode)
    result = helper.list_attached_devices()

    assert result['ok'] is False
    assert 'usbmuxd' in result['message']


# ------------------------------------------------------------------------ checks


def test_nothing_attached_fails_the_first_check_only(monkeypatch):
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [])
    result = helper.check_prerequisites(UDID)

    assert result['ready'] is False
    assert [check['id'] for check in result['checks']] == [helper.CHECK_USB]


def test_an_unpaired_device_stops_at_trust(device, monkeypatch):
    monkeypatch.setattr(helper, '_open_lockdown', lambda *args, **kwargs: FakeLockdown(paired=False))
    result = helper.check_prerequisites(UDID)

    checks = checks_by_id(result)
    assert checks[helper.CHECK_TRUST]['state'] == helper.STATE_FAILED
    assert checks[helper.CHECK_TRUST]['fix'] == helper.FIX_PAIR
    # Developer Mode and the image cannot be read without pairing, so reporting
    # on them would be guesswork.
    assert helper.CHECK_DEVELOPER_MODE not in checks
    assert result['ready'] is False


def test_a_ready_device_passes_everything(device, tunnel_up):
    result = helper.check_prerequisites(UDID)

    assert result['ready'] is True
    assert [check['state'] for check in result['checks']] == [helper.STATE_OK] * 5


def test_an_unmounted_image_offers_the_mount_fix(device, tunnel_up):
    FakeMounter.mounted = False
    result = helper.check_prerequisites(UDID)

    check = checks_by_id(result)[helper.CHECK_DEVELOPER_IMAGE]
    assert check['state'] == helper.STATE_FAILED
    assert check['fix'] == helper.FIX_MOUNT_DEVELOPER_IMAGE
    assert result['ready'] is False


def test_developer_mode_off_offers_the_reveal_fix(device, tunnel_up):
    device.developer_mode_status = False
    result = helper.check_prerequisites(UDID)

    check = checks_by_id(result)[helper.CHECK_DEVELOPER_MODE]
    assert check['state'] == helper.STATE_FAILED
    assert check['fix'] == helper.FIX_REVEAL_DEVELOPER_MODE


def test_no_tunnel_service_offers_the_tunnel_fix(device, tunnel_down):
    result = helper.check_prerequisites(UDID)

    check = checks_by_id(result)[helper.CHECK_TUNNEL]
    assert check['state'] == helper.STATE_FAILED
    assert check['fix'] == helper.FIX_START_TUNNEL


def test_a_running_tunnel_service_with_no_tunnel_offers_no_fix(device, monkeypatch):
    def fake_urlopen(url, timeout=None):
        class Response:
            def read(self):
                return json.dumps({}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        return Response()

    monkeypatch.setattr(helper, 'urlopen', fake_urlopen)
    check = checks_by_id(helper.check_prerequisites(UDID))[helper.CHECK_TUNNEL]

    # Installing the service again would report success and change nothing; the
    # missing half is the device's, and only reconnecting it helps.
    assert check['state'] == helper.STATE_FAILED
    assert check['fix'] is None


def test_a_tunnel_for_another_device_does_not_count(device, monkeypatch):
    def fake_urlopen(url, timeout=None):
        class Response:
            def read(self):
                return json.dumps({'some-other-udid': [{'tunnel-port': 1}]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        return Response()

    monkeypatch.setattr(helper, 'urlopen', fake_urlopen)
    result = helper.check_prerequisites(UDID)

    assert checks_by_id(result)[helper.CHECK_TUNNEL]['state'] == helper.STATE_FAILED


def test_ios_15_needs_neither_developer_mode_nor_a_tunnel(device, tunnel_down):
    device.product_version = '15.7'
    result = helper.check_prerequisites(UDID)

    checks = checks_by_id(result)
    assert checks[helper.CHECK_DEVELOPER_MODE]['state'] == helper.STATE_SKIPPED
    assert checks[helper.CHECK_TUNNEL]['state'] == helper.STATE_SKIPPED
    # Skipped is not failed: an iOS 15 phone with its image mounted is ready.
    assert result['ready'] is True


def test_ios_16_needs_developer_mode_but_no_tunnel(device, tunnel_down):
    device.product_version = '16.6'
    result = helper.check_prerequisites(UDID)

    checks = checks_by_id(result)
    assert checks[helper.CHECK_DEVELOPER_MODE]['state'] == helper.STATE_OK
    assert checks[helper.CHECK_TUNNEL]['state'] == helper.STATE_SKIPPED


def test_a_check_with_no_udid_uses_the_only_attached_device(device, tunnel_up):
    result = helper.check_prerequisites()

    assert result['udid'] == UDID
    assert result['ready'] is True


def test_a_udid_that_matches_nothing_attached_fails_the_usb_check(device):
    result = helper.check_prerequisites('00000000-000000000000000A')

    assert [check['id'] for check in result['checks']] == [helper.CHECK_USB]
    assert result['checks'][0]['state'] == helper.STATE_FAILED


# -------------------------------------------------------------------------- fixes


def test_pairing_an_unpaired_device_reports_the_refusal(monkeypatch):
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [FakeMuxDevice()])
    monkeypatch.setattr(helper, '_open_lockdown', lambda *args, **kwargs: FakeLockdown(paired=False))
    result = helper.pair_device(UDID)

    assert result['ok'] is False
    assert 'Trust' in result['message']


def test_pairing_reports_success_by_name(device):
    result = helper.pair_device(UDID)

    assert result['ok'] is True
    assert 'Test iPhone' in result['message']


def test_a_fix_for_a_device_that_is_not_there_says_so(monkeypatch):
    monkeypatch.setattr(helper.usbmux, 'list_devices', lambda: [])

    for fix in (helper.pair_device, helper.reveal_developer_mode, helper.mount_developer_image):
        assert fix(UDID)['ok'] is False


def test_an_already_mounted_image_is_not_an_error(device, monkeypatch):
    from pymobiledevice3.exceptions import AlreadyMountedError

    def already_mounted(lockdown):
        raise AlreadyMountedError()

    monkeypatch.setattr('pymobiledevice3.services.mobile_image_mounter.auto_mount', already_mounted)
    result = helper.mount_developer_image(UDID)

    assert result['ok'] is True


def test_mounting_without_developer_mode_names_the_reason(device, monkeypatch):
    from pymobiledevice3.exceptions import DeveloperModeIsNotEnabledError

    def not_enabled(lockdown):
        raise DeveloperModeIsNotEnabledError()

    monkeypatch.setattr('pymobiledevice3.services.mobile_image_mounter.auto_mount', not_enabled)
    result = helper.mount_developer_image(UDID)

    assert result['ok'] is False
    assert 'Developer Mode' in result['message']


def test_revealing_developer_mode_needs_pairing_first(device, monkeypatch):
    monkeypatch.setattr(helper, '_open_lockdown', lambda *args, **kwargs: FakeLockdown(paired=False))
    result = helper.reveal_developer_mode(UDID)

    assert result['ok'] is False
    assert 'Pair' in result['message']
