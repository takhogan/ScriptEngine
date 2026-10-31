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

"""
What the Add Device form needs to know and do before an iOS device can be driven.

An iOS device has four or five prerequisites that an Android device does not
(pairing, Developer Mode, a mounted developer disk image, and on iOS 17+ a root
RSD tunnel), and the only published instructions for them are `pymobiledevice3`
command lines. This module turns each one into a check the controller can run and,
where possible, a fix it can apply, so that registering an iPhone is a matter of
pressing buttons rather than of reading a terminal.

Nothing here needs a registered device: these run from the Add Device form before
any configuration for the device exists, so they take a UDID (or none at all, for
discovery) rather than a device record. Nothing here raises either - every entry
point returns a report, because the caller is a form that has to show the user
something whatever happens.
"""

import json
import socket
from urllib.error import URLError
from urllib.request import urlopen

from pymobiledevice3 import usbmux
from pymobiledevice3.exceptions import (
    AlreadyMountedError,
    DeveloperModeIsNotEnabledError,
    MessageNotSupportedError,
    PairingError,
    PyMobileDevice3Exception,
)
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS

from ScriptEngine.common.logging.script_logger import ScriptLogger

script_logger = ScriptLogger()


# iOS 17 moved the developer services behind RemoteServiceDiscovery, which only
# answers over a tunnel. Kept in step with IOSDeviceManager.RSD_REQUIRED_MAJOR_VERSION.
RSD_REQUIRED_MAJOR_VERSION = 17
# Developer Mode is an iOS 16 feature; below that there is no switch to look for.
DEVELOPER_MODE_MINIMUM_MAJOR_VERSION = 16

# How long to leave the "Trust This Computer" prompt up before giving up on it.
# Long enough to pick the phone up and tap, short enough that the form is not
# wedged if nobody does.
TRUST_PROMPT_TIMEOUT_SECONDS = 45
# The tunnel check only asks a loopback HTTP server whether it is there, so a
# wait of more than a moment means it is not.
TUNNELD_TIMEOUT_SECONDS = 2

# Each prerequisite, in the order it has to be satisfied: a later one cannot even
# be tested until the earlier ones pass.
CHECK_USB = 'usb'
CHECK_TRUST = 'trust'
CHECK_DEVELOPER_MODE = 'developerMode'
CHECK_DEVELOPER_IMAGE = 'developerImage'
CHECK_TUNNEL = 'tunnel'

STATE_OK = 'ok'
STATE_FAILED = 'failed'
# Does not apply to this device - an iOS 15 phone has no Developer Mode switch
# and needs no tunnel. Shown as neither passing nor blocking.
STATE_SKIPPED = 'skipped'

# Fixes the controller can offer as a button. A check with no fix is one only the
# user can clear, by doing something on the phone.
FIX_PAIR = 'pair'
FIX_REVEAL_DEVELOPER_MODE = 'revealDeveloperMode'
FIX_MOUNT_DEVELOPER_IMAGE = 'mountDeveloperImage'
# The one fix with no handler in SETUP_ACTIONS: installing the tunnel daemon is
# work on the host, not on the phone, so the controller does it itself through
# SMAppService (src/iosTunnelDaemon.mjs). Named here because the check that
# reports the failure is here.
FIX_START_TUNNEL = 'startTunnel'


def _check(check_id, label, state, detail, fix=None):
    return {'id': check_id, 'label': label, 'state': state, 'detail': detail, 'fix': fix}


def _find_mux_device(udid=None):
    """The attached device with this UDID, or the only attached one if none was given."""
    devices = usbmux.list_devices()
    if udid:
        for device in devices:
            if device.matches_udid(udid):
                return device
        return None
    return devices[0] if devices else None


def _open_lockdown(udid, autopair=False, pair_timeout=None):
    """A lockdown client for this device, paired or not.

    autopair=False by default: pairing is blocking, and a check that silently put
    a prompt on someone's phone and then waited on it would look like a hang.
    The pair fix asks for it explicitly.
    """
    return create_using_usbmux(serial=udid, autopair=autopair, pair_timeout=pair_timeout)


def _device_summary(udid):
    """Name and iOS version, which need a paired connection, plus whether we have one."""
    summary = {'udid': udid, 'deviceName': None, 'productVersion': None, 'productType': None, 'paired': False}
    lockdown = None
    try:
        lockdown = _open_lockdown(udid)
        summary['paired'] = bool(lockdown.paired)
        if summary['paired']:
            summary['deviceName'] = lockdown.all_values.get('DeviceName')
            summary['productVersion'] = lockdown.product_version
            summary['productType'] = lockdown.product_type
    except Exception as error:
        script_logger.log('iOS SETUP: could not read values from', udid, error, level='debug')
    finally:
        if lockdown is not None:
            try:
                lockdown.close()
            except Exception:
                pass
    return summary


def _major_version(product_version):
    if not product_version:
        return None
    try:
        return int(str(product_version).split('.')[0])
    except ValueError:
        return None


def list_attached_devices(udid=None):
    """Every iOS device usbmuxd can see, labelled as well as pairing allows.

    Takes a UDID only so that every setup action has the same signature; discovery
    is the one action that has no device in mind yet.

    The UDID is always available; the name and version are not, because reading
    them needs a paired connection. An unpaired device is still listed - it is
    exactly the device the user is trying to set up.
    """
    try:
        mux_devices = usbmux.list_devices()
    except Exception as error:
        return {
            'ok': False,
            'message': 'Could not reach usbmuxd, the macOS service that talks to attached iPhones: '
                       '{}'.format(error),
            'devices': []
        }

    # usbmuxd lists a device once per connection type, so a phone that is plugged
    # in and also on the wi-fi appears twice. One entry per device, and USB wins:
    # it is the connection every prerequisite here is about.
    devices = []
    seen = {}
    for mux_device in sorted(mux_devices, key=lambda device: device.connection_type != 'USB'):
        if mux_device.serial in seen:
            seen[mux_device.serial]['connectionTypes'].append(mux_device.connection_type)
            continue
        summary = _device_summary(mux_device.serial)
        summary['connectionType'] = mux_device.connection_type
        summary['connectionTypes'] = [mux_device.connection_type]
        summary['label'] = summary['deviceName'] or mux_device.serial
        seen[mux_device.serial] = summary
        devices.append(summary)

    if not devices:
        return {
            'ok': True,
            'message': 'No iPhone or iPad is attached. Connect one with a USB cable and unlock it.',
            'devices': []
        }
    return {
        'ok': True,
        'message': 'Found {} device{}.'.format(len(devices), '' if len(devices) == 1 else 's'),
        'devices': devices
    }


def _tunnel_check(udid, major_version):
    """Whether a tunnel this device can be reached through is up.

    Asks tunneld's loopback API directly rather than going through
    get_tunneld_device_by_udid, which builds an RemoteServiceDiscoveryService per
    tunnel - a connection to open and then close for a question that a list of
    UDIDs already answers.
    """
    if major_version is not None and major_version < RSD_REQUIRED_MAJOR_VERSION:
        return _check(
            CHECK_TUNNEL, 'Developer tunnel', STATE_SKIPPED,
            'Not needed on iOS {}. The tunnel is only required from iOS {} on.'.format(
                major_version, RSD_REQUIRED_MAJOR_VERSION
            )
        )

    url = 'http://{}:{}/'.format(*TUNNELD_DEFAULT_ADDRESS)
    try:
        with urlopen(url, timeout=TUNNELD_TIMEOUT_SECONDS) as response:
            tunnels = json.loads(response.read().decode('utf-8'))
    except (URLError, socket.timeout, OSError):
        return _check(
            CHECK_TUNNEL, 'Developer tunnel', STATE_FAILED,
            'The tunnel service is not running. iOS {} and later reach the developer services '
            'through a network tunnel, which needs a background service installed once. Press '
            'Set up tunnel; macOS asks you to authorise it, and then it starts by itself from '
            'here on.'.format(RSD_REQUIRED_MAJOR_VERSION),
            fix=FIX_START_TUNNEL
        )
    except ValueError:
        return _check(
            CHECK_TUNNEL, 'Developer tunnel', STATE_FAILED,
            'Something is answering on the tunnel service port but it is not the tunnel service.',
            fix=FIX_START_TUNNEL
        )

    if udid in tunnels:
        return _check(CHECK_TUNNEL, 'Developer tunnel', STATE_OK, 'The tunnel service has a tunnel for this device.')
    # No fix offered: the service is installed and running, so installing it again
    # would report success and change nothing. What is missing is the device's end
    # of the tunnel, which only reconnecting the device can supply.
    return _check(
        CHECK_TUNNEL, 'Developer tunnel', STATE_FAILED,
        'The tunnel service is running but has no tunnel for this device. Unplug it and plug it '
        'back in; if that does not help, check that it is unlocked and trusted.'
    )


def check_prerequisites(udid=None):
    """Every prerequisite for driving this device, each one passed, failed or not applicable."""
    mux_device = _find_mux_device(udid)
    if mux_device is None:
        return {
            'ok': True,
            'udid': udid,
            'ready': False,
            'checks': [_check(
                CHECK_USB, 'Device attached', STATE_FAILED,
                'No attached device matches this one. Connect it with a USB cable and unlock it.'
                if udid else 'No iPhone or iPad is attached. Connect one with a USB cable and unlock it.'
            )]
        }

    udid = mux_device.serial
    checks = [_check(
        CHECK_USB, 'Device attached', STATE_OK,
        'Connected over {}.'.format(mux_device.connection_type)
    )]

    summary = _device_summary(udid)
    if not summary['paired']:
        checks.append(_check(
            CHECK_TRUST, 'Trusted by this computer', STATE_FAILED,
            'This computer is not trusted by the device yet. Unlock the device and press Pair, '
            'then tap Trust on the prompt that appears on it.',
            fix=FIX_PAIR
        ))
        # Nothing below pairing can be read, so the rest of the list would be
        # guesswork. Stopping here also keeps the form honest about what is known.
        return {'ok': True, 'udid': udid, 'ready': False, 'device': summary, 'checks': checks}

    checks.append(_check(
        CHECK_TRUST, 'Trusted by this computer', STATE_OK,
        '{} running iOS {}.'.format(summary['deviceName'] or udid, summary['productVersion'])
    ))

    major_version = _major_version(summary['productVersion'])
    checks.extend(_developer_checks(udid, major_version))
    checks.append(_tunnel_check(udid, major_version))

    return {
        'ok': True,
        'udid': udid,
        'device': summary,
        'ready': all(check['state'] != STATE_FAILED for check in checks),
        'checks': checks
    }


def _developer_checks(udid, major_version):
    """Developer Mode and the developer disk image, both read over one connection."""
    from pymobiledevice3.services.mobile_image_mounter import (
        DeveloperDiskImageMounter,
        PersonalizedImageMounter,
    )

    developer_mode = _check(
        CHECK_DEVELOPER_MODE, 'Developer Mode', STATE_FAILED,
        'Could not read whether Developer Mode is on.', fix=FIX_REVEAL_DEVELOPER_MODE
    )
    developer_image = _check(
        CHECK_DEVELOPER_IMAGE, 'Developer disk image', STATE_FAILED,
        'Could not read whether the developer disk image is mounted.', fix=FIX_MOUNT_DEVELOPER_IMAGE
    )

    lockdown = None
    try:
        lockdown = _open_lockdown(udid)

        if major_version is not None and major_version < DEVELOPER_MODE_MINIMUM_MAJOR_VERSION:
            developer_mode = _check(
                CHECK_DEVELOPER_MODE, 'Developer Mode', STATE_SKIPPED,
                'iOS {} has no Developer Mode switch; it was added in iOS {}.'.format(
                    major_version, DEVELOPER_MODE_MINIMUM_MAJOR_VERSION
                )
            )
        elif lockdown.developer_mode_status:
            developer_mode = _check(CHECK_DEVELOPER_MODE, 'Developer Mode', STATE_OK, 'Turned on.')
        else:
            developer_mode = _check(
                CHECK_DEVELOPER_MODE, 'Developer Mode', STATE_FAILED,
                'Turned off. Press Show on device, then on the device open Settings > Privacy & '
                'Security > Developer Mode and turn it on. The device restarts.',
                fix=FIX_REVEAL_DEVELOPER_MODE
            )

        # Two different images, and which one a device wants depends on its version:
        # a pre-17 device mounts the DeveloperDiskImage, a 17+ device a personalized
        # one. Asking for the wrong type reports "not mounted" for an image that is.
        mounter_class = (
            DeveloperDiskImageMounter
            if major_version is not None and major_version < RSD_REQUIRED_MAJOR_VERSION
            else PersonalizedImageMounter
        )
        mounter = mounter_class(lockdown=lockdown)
        if mounter.is_image_mounted(mounter.IMAGE_TYPE):
            developer_image = _check(
                CHECK_DEVELOPER_IMAGE, 'Developer disk image', STATE_OK, 'Mounted.'
            )
        else:
            developer_image = _check(
                CHECK_DEVELOPER_IMAGE, 'Developer disk image', STATE_FAILED,
                'Not mounted. Screenshots come from a developer service, so without this image '
                'the device cannot be viewed at all. Press Mount to download and mount it.',
                fix=FIX_MOUNT_DEVELOPER_IMAGE
            )
    except Exception as error:
        script_logger.log('iOS SETUP: developer checks failed for', udid, error, level='error')
        developer_image['detail'] = 'Could not ask the device: {}'.format(error)
    finally:
        if lockdown is not None:
            try:
                lockdown.close()
            except Exception:
                pass

    return [developer_mode, developer_image]


def pair_device(udid=None):
    """Put the Trust prompt on the device and wait for it to be answered."""
    mux_device = _find_mux_device(udid)
    if mux_device is None:
        return {'ok': False, 'message': 'No attached device matches this one.'}

    lockdown = None
    try:
        lockdown = _open_lockdown(mux_device.serial, autopair=True, pair_timeout=TRUST_PROMPT_TIMEOUT_SECONDS)
        if not lockdown.paired:
            return {
                'ok': False,
                'message': 'The device did not accept this computer. Unlock it and tap Trust on the prompt.'
            }
        return {
            'ok': True,
            'message': 'Paired with {}.'.format(lockdown.all_values.get('DeviceName') or mux_device.serial)
        }
    except PairingError as error:
        return {
            'ok': False,
            'message': 'Pairing was not completed: {}. Unlock the device and tap Trust on the prompt '
                       'that appears on it.'.format(error)
        }
    except Exception as error:
        script_logger.log('iOS SETUP: pairing failed for', mux_device.serial, error, level='error')
        return {'ok': False, 'message': 'Pairing failed: {}'.format(error)}
    finally:
        if lockdown is not None:
            try:
                lockdown.close()
            except Exception:
                pass


def reveal_developer_mode(udid=None):
    """Make the Developer Mode switch appear in the device's own Settings.

    Deliberately only reveals it. AmfiService can also turn it on, but that
    restarts the phone, and a button on a registration form is no place for an
    unannounced reboot. Flipping the switch is one tap for the user and leaves
    them in control of when the device goes down.
    """
    from pymobiledevice3.services.amfi import AmfiService

    mux_device = _find_mux_device(udid)
    if mux_device is None:
        return {'ok': False, 'message': 'No attached device matches this one.'}

    lockdown = None
    try:
        lockdown = _open_lockdown(mux_device.serial)
        if not lockdown.paired:
            return {'ok': False, 'message': 'Pair with the device first.'}
        AmfiService(lockdown).reveal_developer_mode_option_in_ui()
        return {
            'ok': True,
            'message': 'On the device, open Settings > Privacy & Security > Developer Mode and turn '
                       'it on. The device restarts, and asks you to confirm after it comes back. '
                       'Then press Check again.'
        }
    except Exception as error:
        script_logger.log('iOS SETUP: revealing developer mode failed for', mux_device.serial, error, level='error')
        return {'ok': False, 'message': 'Could not ask the device to show the switch: {}'.format(error)}
    finally:
        if lockdown is not None:
            try:
                lockdown.close()
            except Exception:
                pass


def mount_developer_image(udid=None):
    """Download the right developer disk image for this device and mount it."""
    from pymobiledevice3.services.mobile_image_mounter import auto_mount
    from pymobiledevice3.utils import get_asyncio_loop

    mux_device = _find_mux_device(udid)
    if mux_device is None:
        return {'ok': False, 'message': 'No attached device matches this one.'}

    lockdown = None
    try:
        lockdown = _open_lockdown(mux_device.serial)
        if not lockdown.paired:
            return {'ok': False, 'message': 'Pair with the device first.'}
        # auto_mount picks the image for the device's own version and downloads it
        # if this computer does not have it yet, so this can take a minute.
        get_asyncio_loop().run_until_complete(auto_mount(lockdown))
        return {'ok': True, 'message': 'Developer disk image mounted.'}
    except AlreadyMountedError:
        return {'ok': True, 'message': 'The developer disk image was already mounted.'}
    except DeveloperModeIsNotEnabledError:
        return {
            'ok': False,
            'message': 'Developer Mode has to be on before the image can be mounted. Turn it on '
                       'on the device first.'
        }
    except MessageNotSupportedError as error:
        return {'ok': False, 'message': 'This version of iOS did not understand the request: {}'.format(error)}
    except PyMobileDevice3Exception as error:
        script_logger.log('iOS SETUP: mounting failed for', mux_device.serial, error, level='error')
        return {'ok': False, 'message': 'Mounting the developer disk image failed: {}'.format(error)}
    except Exception as error:
        script_logger.log('iOS SETUP: mounting failed for', mux_device.serial, error, level='error')
        return {'ok': False, 'message': 'Mounting the developer disk image failed: {}'.format(error)}
    finally:
        if lockdown is not None:
            try:
                lockdown.close()
            except Exception:
                pass


# What the device controller will dispatch to, keyed by the action name the
# controller sends. Every one takes an optional UDID and returns a report.
SETUP_ACTIONS = {
    'ios_list_devices': list_attached_devices,
    'ios_check_prerequisites': check_prerequisites,
    'ios_pair_device': pair_device,
    'ios_reveal_developer_mode': reveal_developer_mode,
    'ios_mount_developer_image': mount_developer_image,
}


def run_setup_action(action, udid=None):
    """Dispatch one setup action, reporting rather than raising whatever goes wrong.

    The device controller turns an exception out of parse_inputs into the single
    string 'device controller error', which tells the user nothing. Everything
    here is driven by a button in a form, so the failure has to come back as
    something that can be read.
    """
    handler = SETUP_ACTIONS.get(action)
    if handler is None:
        return {'ok': False, 'message': 'Unknown iOS setup action {}'.format(action)}
    try:
        return handler(udid)
    except Exception as error:
        script_logger.log('iOS SETUP: action', action, 'failed', error, level='error')
        return {'ok': False, 'message': '{} failed: {}'.format(action, error)}
