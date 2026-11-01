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
Read-only driver for a physical iOS device (phase 1 of docs/ios-device-support-plan.md).

Everything the engine needs to *observe* a device works here: screenshots, status,
the installed application list, and launching or killing an application by bundle
id. Everything that needs to *touch* the screen does not: iOS has no equivalent of
`adb shell input tap`, and pymobiledevice3 exposes no coordinate-based input
service, so click/drag/scroll/keyboard raise IOSInputUnsupportedError until the
WebDriverAgent client of phase 2 lands.

Two transports, picked by OS version:

  iOS < 17   every developer service is reachable over plain usbmux lockdown, no
             root needed.
  iOS >= 17  Apple moved them behind RemoteServiceDiscovery, which needs an RSD
             tunnel. `pymobiledevice3 remote tunneld` has to be running as root;
             we look the device up in it by UDID.

Either way the device must be paired ("Trust This Computer"), have Developer Mode
enabled, and have the developer disk image mounted - the screenshot service is a
developer service, so an unmounted DDI means no screenshots at all.
"""

import threading
from io import BytesIO
from typing import List

import cv2
import numpy as np
from PIL import Image

from pymobiledevice3 import usbmux
from pymobiledevice3.exceptions import StartServiceError, TunneldConnectionError
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from pymobiledevice3.services.springboard import SpringBoardServicesService
from pymobiledevice3.tunneld.api import get_tunneld_device_by_udid
from pymobiledevice3.utils import get_asyncio_loop

from .device_manager import DeviceManager
from ScriptEngine.common.script_engine_utils import is_null
from ScriptEngine.common.logging.script_logger import ScriptLogger

script_logger = ScriptLogger()


# Pointed at from every input method, so the message a script fails with names
# the prerequisite rather than just the missing capability.
IOS_INPUT_UNSUPPORTED_MESSAGE = (
    'iOS CONTROLLER: {} requires WebDriverAgent, which is not wired up yet. iOS has no '
    'coordinate-based input service of its own, so taps, drags, scrolls and key events need a '
    'signed WebDriverAgent runner on the device. See docs/ios-device-support-plan.md (phase 2). '
    'Screenshot, status and application actions work without it.'
)


class IOSInputUnsupportedError(Exception):
    """An input action was asked of an iOS device that has no WebDriverAgent runner.

    Its own type, not a bare Exception, so a caller can tell "this device cannot do
    input at all" apart from "this device stopped responding" - the two want
    different handling, and only the second is worth retrying.
    """


class IOSDeviceManager(DeviceManager):
    # iOS 17 moved the developer services behind RSD, so from here up a tunnel is
    # required and plain usbmux lockdown is only good for the device's own values.
    RSD_REQUIRED_MAJOR_VERSION = 17

    def __init__(self, props, device_params, input_source=None):
        script_logger.log('Configuring iOS device with device_params', device_params, level='info')
        self.props = props
        self.device_params = device_params or {}
        self.width = None
        self.height = None
        # Screenshots come back in pixels while WebDriverAgent takes points, so a
        # Retina device needs every incoming coordinate divided by this before it
        # can be tapped. Phase 1 has no input and no WDA to ask for the point size,
        # so it stays None rather than being guessed at; phase 2 fills it in from
        # WDA's window size. DesktopDeviceManager.scale_factor is the same idea.
        self.scale_factor = None
        self.screen_orientation = None

        self.lockdown = None
        self.product_version = None
        # Whichever of lockdown/RSD the developer services are reachable through on
        # this OS version. Every service in this class is built from it.
        self.service_provider = None
        self._dvt = None
        self._screenshot_channel = None
        # One connection, shared by every caller: a DVT channel is a single socket
        # with a request/reply protocol on it, so two threads interleaving on it
        # would read each other's replies. Script runs are multithreaded
        # (parallelized_script_executor), hence the lock rather than a comment.
        self._service_lock = threading.RLock()

        if input_source is not None:
            self.dummy_mode = True
            self.input_source = input_source
            self.width = input_source['width']
            self.height = input_source['height']
        else:
            self.dummy_mode = False
            self.input_source = None

        if not self.device_params and input_source is None:
            raise Exception(
                'iOS CONTROLLER: this action requires an iOS device, but no device configuration '
                'was provided for it. Attach a device to the run, or check that the selected '
                'device still exists in the host device config.'
            )

        self.udid = None if self.dummy_mode else self._resolve_udid()

    # ------------------------------------------------------------------ identity

    def _resolve_udid(self):
        """The device's UDID, from an explicit field or from the `ios:<udid>` id.

        Deliberately not falling back to 'deviceName' the way the adb manager uses
        it for an emulator name: on an iOS record that field holds a human name, so
        accepting it here would quietly drive whatever device a nickname happened to
        match - or nothing at all.
        """
        udid = self.device_params.get('udid')
        if udid:
            return udid
        device_id = self.device_params.get('deviceId')
        if device_id and ':' in device_id:
            return device_id.split(':', 1)[1]
        raise Exception(
            'iOS CONTROLLER: could not work out which device to drive. Expected a '
            "'udid' field or a device id of the form 'ios:<udid>', got {}".format(
                self.device_params.get('deviceId')
            )
        )

    # ---------------------------------------------------------------- connection

    def _connect(self):
        """Open lockdown and resolve the provider the developer services live behind.

        Lockdown over usbmux first in every case: it needs no root, and it is the
        only thing that can tell us the OS version that decides whether a tunnel is
        required in the first place.
        """
        self.lockdown = create_using_usbmux(serial=self.udid)
        self.product_version = self.lockdown.product_version
        script_logger.log(
            'iOS CONTROLLER: connected to', self.udid, 'running iOS', self.product_version, level='info'
        )

        if self._major_version() < self.RSD_REQUIRED_MAJOR_VERSION:
            self.service_provider = self.lockdown
            return

        # From here on the lockdown client we just opened is only useful if the
        # tunnel resolves, so every failure below closes it rather than leaving one
        # open connection behind per attempt.
        try:
            rsd = get_tunneld_device_by_udid(self.udid)
        except TunneldConnectionError:
            self._close_lockdown()
            raise Exception(
                'iOS CONTROLLER: device {} runs iOS {}, which reaches its developer services only '
                'through an RSD tunnel, and no tunneld is running. Start it as root with '
                "'sudo pymobiledevice3 remote tunneld' and try again.".format(
                    self.udid, self.product_version
                )
            )
        except Exception:
            self._close_lockdown()
            raise
        if rsd is None:
            self._close_lockdown()
            raise Exception(
                'iOS CONTROLLER: tunneld is running but has no tunnel for device {} (iOS {}). '
                'Reconnect the device, or check that it is trusted and has Developer Mode '
                'enabled.'.format(self.udid, self.product_version)
            )
        self.service_provider = rsd

    def _close_lockdown(self):
        if self.lockdown is None:
            return
        try:
            self.lockdown.close()
        except Exception as close_error:
            script_logger.log('iOS CONTROLLER: error closing lockdown', close_error, level='debug')
        self.lockdown = None

    def _major_version(self):
        try:
            return int(str(self.product_version).split('.')[0])
        except (TypeError, ValueError):
            # An unreadable version is treated as new, because the tunnel path also
            # works for older devices while the reverse is not true.
            script_logger.log(
                'iOS CONTROLLER: could not parse product version', self.product_version,
                'assuming RSD is required', level='error'
            )
            return self.RSD_REQUIRED_MAJOR_VERSION

    def _ensure_connected(self):
        with self._service_lock:
            if self.service_provider is None:
                self._connect()
            return self.service_provider

    def _reset_connection(self):
        """Drop every cached service so the next call reconnects from scratch."""
        with self._service_lock:
            # Decided before anything is closed, because below iOS 17 the provider
            # *is* the lockdown client and must not be closed twice.
            rsd = self.service_provider if self.service_provider is not self.lockdown else None

            if self._dvt is not None:
                try:
                    self._dvt.close()
                except Exception as close_error:
                    script_logger.log('iOS CONTROLLER: error closing dvt', close_error, level='debug')
            self._close_lockdown()
            # On iOS 17+ the provider is an RSD, whose close() is a coroutine: left
            # unawaited it would both leak the tunnel connection on every reconnect
            # and warn about it.
            if rsd is not None:
                try:
                    get_asyncio_loop().run_until_complete(rsd.close())
                except Exception as close_error:
                    script_logger.log('iOS CONTROLLER: error closing RSD', close_error, level='debug')

            self._dvt = None
            self._screenshot_channel = None
            self.service_provider = None

    def _dvt_service(self):
        """The shared DVT connection, opened on first use.

        A failure here is almost always the developer disk image not being mounted,
        so it is worth translating: the raw StartServiceError says only that a
        service would not start.
        """
        with self._service_lock:
            if self._dvt is None:
                provider = self._ensure_connected()
                try:
                    self._dvt = DvtSecureSocketProxyService(lockdown=provider)
                    self._dvt.perform_handshake()
                except StartServiceError:
                    raise Exception(
                        'iOS CONTROLLER: could not reach the instruments service on device {}. The '
                        'developer disk image is most likely not mounted - run '
                        "'pymobiledevice3 mounter auto-mount' - and Developer Mode must be enabled "
                        'in Settings > Privacy & Security.'.format(self.udid)
                    )
            return self._dvt

    def close(self):
        self._reset_connection()

    # ------------------------------------------------------------ initialization

    def ensure_device_initialized(self, reinitialize=False):
        if self.dummy_mode:
            if self.width is None or self.height is None:
                self.width = self.input_source['width']
                self.height = self.input_source['height']
            script_logger.log('iOS CONTROLLER: script in dummy mode, initialized to input source')
            return None

        if reinitialize:
            self._reset_connection()

        source_im = None
        if reinitialize or self.width is None or self.height is None:
            self._ensure_connected()
            # Same bootstrap as the adb and kvm managers: the screenshot is the only
            # thing that knows the dimensions the rest of the engine works in.
            source_im = self._png_to_bgr(self._capture_png())
            self.height, self.width = source_im.shape[:2]
            self.get_screen_orientation()
            script_logger.log(
                'iOS CONTROLLER: initialized device', self.udid,
                'screen', self.width, 'x', self.height,
                'orientation', self.screen_orientation,
                level='info'
            )

        if is_null(self.props.get('width')):
            self.props['width'] = self.width
        if is_null(self.props.get('height')):
            self.props['height'] = self.height
        return source_im

    def get_status(self):
        """'online' when the device is attached and its services are reachable.

        Deliberately cheaper than taking a screenshot: the editor's live view polls
        this every second or two. It still resolves the service provider, so an
        iOS 17+ device whose tunnel has gone away reports offline rather than
        reporting online and then failing every screenshot.
        """
        if self.dummy_mode:
            return 'online'
        try:
            if not any(device.serial == self.udid for device in usbmux.list_devices()):
                script_logger.log('iOS CONTROLLER: device', self.udid, 'is not attached')
                return 'offline'
            self._ensure_connected()
            return 'online'
        except Exception as e:
            script_logger.log('iOS CONTROLLER: get_status', e, level='error')
            # A failed probe leaves a half-open connection behind that would be
            # reused by the next call, so clear it while we know it is bad.
            self._reset_connection()
            return 'offline'

    def get_screen_orientation(self):
        """Current interface orientation, or None if springboard will not say.

        Orientation is informational in phase 1 - nothing maps coordinates yet - so
        it never fails a run.
        """
        try:
            with self._service_lock:
                provider = self._ensure_connected()
                with SpringBoardServicesService(provider) as springboard:
                    self.screen_orientation = int(springboard.get_interface_orientation())
        except Exception as e:
            script_logger.log('iOS CONTROLLER: could not read screen orientation', e, level='debug')
            self.screen_orientation = None
        return self.screen_orientation

    # ------------------------------------------------------------------ capturing

    @staticmethod
    def _png_to_bgr(png_bytes):
        """PNG bytes -> the BGR numpy array every caller of screenshot() expects."""
        with Image.open(BytesIO(png_bytes)) as source_im:
            return cv2.cvtColor(np.array(source_im.convert('RGB')), cv2.COLOR_RGB2BGR)

    def _capture_png(self):
        """Raw screenshot, without the initialization ensure_device_initialized does.

        Split out for the same reason adb splits get_screencap from screenshot:
        ensure_device_initialized needs a screenshot to learn the dimensions, so the
        public method cannot be the one it calls.
        """
        with self._service_lock:
            dvt = self._dvt_service()
            if self._screenshot_channel is None:
                self._screenshot_channel = Screenshot(dvt)
            return self._screenshot_channel.get_screenshot()

    def screenshot(self):
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('iOS CONTROLLER: script in dummy mode, returning screenshot of input source')
            return self.input_source['screenshot']()
        try:
            return self._png_to_bgr(self._capture_png())
        except Exception as e:
            script_logger.log('iOS CONTROLLER: screenshot failed, reinitializing device', e, level='error')
            # One reconnect, then one retry: a reused DVT channel going stale after
            # the device locks or the tunnel restarts is the common case, and it
            # clears on reconnect. A second failure is real and fails the run.
            source_im = self.ensure_device_initialized(reinitialize=True)
            if source_im is None:
                raise Exception('iOS connection failed')
            return source_im

    # --------------------------------------------------------------- application

    def list_applications(self, filter_system=True) -> dict[str, str]:
        """Installed applications as {bundle id: display name}.

        Mirrors ADBDeviceManager.list_applications, including its filter_system
        default: user-installed applications only, because the full list on iOS is
        several hundred system bundles.
        """
        if self.dummy_mode:
            script_logger.log('iOS CONTROLLER: script in dummy mode, returning from list_applications')
            return {}
        try:
            with self._service_lock:
                provider = self._ensure_connected()
                with InstallationProxyService(provider) as installation_proxy:
                    apps = installation_proxy.get_apps(
                        application_type='User' if filter_system else 'Any'
                    )
            applications = {
                bundle_id: (app.get('CFBundleDisplayName') or app.get('CFBundleName') or bundle_id)
                for bundle_id, app in apps.items()
            }
            script_logger.log('iOS CONTROLLER: found {} applications'.format(len(applications)))
            return applications
        except Exception as e:
            script_logger.log('iOS CONTROLLER: error listing applications: {}'.format(e), level='error')
            return {}

    def start_application(self, application_path: str, args: List[str] | None):
        """Launch an application by bundle id.

        application_path is a bundle id here, not a path - it is the key
        list_applications returns, which is what the editor stores.
        """
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('iOS CONTROLLER: script in dummy mode, returning from start_application')
            return
        try:
            script_logger.log('iOS CONTROLLER: starting application {}'.format(application_path))
            with self._service_lock:
                process_control = ProcessControl(self._dvt_service())
                pid = process_control.launch(application_path, arguments=args or [], kill_existing=True)
            script_logger.log('iOS CONTROLLER: started application {} as pid {}'.format(application_path, pid))
        except Exception as e:
            script_logger.log(
                'iOS CONTROLLER: error starting application {}: {}'.format(application_path, e), level='error'
            )

    def stop_application(self, application_name: str):
        """Kill an application by bundle id."""
        self.ensure_device_initialized()
        if self.dummy_mode:
            script_logger.log('iOS CONTROLLER: script in dummy mode, returning from stop_application')
            return
        try:
            with self._service_lock:
                process_control = ProcessControl(self._dvt_service())
                pid = process_control.process_identifier_for_bundle_identifier(application_name)
                if not pid:
                    script_logger.log(
                        'iOS CONTROLLER: application {} is not running'.format(application_name)
                    )
                    return
                script_logger.log('iOS CONTROLLER: stopping application {} (pid {})'.format(application_name, pid))
                process_control.kill(pid)
        except Exception as e:
            script_logger.log(
                'iOS CONTROLLER: error stopping application {}: {}'.format(application_name, e), level='error'
            )

    # -------------------------------------------------------------- device power

    def start_device(self):
        """No-op: a physical iPhone cannot be powered on from the host.

        Same shape as the adb manager's 'adb' emulator type, which says the same
        thing for a real Android device. A Simulator could be booted here, but that
        is a device type of its own (see phase 3 of the plan).
        """
        script_logger.log(
            'iOS CONTROLLER: start device not supported for a physical iOS device, please unlock it manually'
        )

    def stop_device(self):
        script_logger.log(
            'iOS CONTROLLER: stop device not supported for a physical iOS device, please lock it manually'
        )

    # ---------------------------------------------------------------- input: n/a

    def _input_unsupported(self, action_name):
        message = IOS_INPUT_UNSUPPORTED_MESSAGE.format(action_name)
        script_logger.log(message, level='error')
        raise IOSInputUnsupportedError(message)

    def click(self, x, y, button='left', important=True, mouse_up=True):
        self._input_unsupported('click')

    def click_and_drag(self, source_x, source_y, target_x, target_y, mouse_down=True, mouse_up=True):
        self._input_unsupported('click_and_drag')

    def smooth_move(self, source_x, source_y, target_x, target_y, drag=False, button='left'):
        self._input_unsupported('mouse_move')

    def mouse_down(self, x, y, button='left'):
        self._input_unsupported('mouse_down')

    def mouse_up(self, x, y, button='left'):
        self._input_unsupported('mouse_up')

    def scroll(self, x, y, scroll_distance):
        self._input_unsupported('scroll')

    def key_press(self, key):
        self._input_unsupported('key_press')

    def key_down(self, key):
        self._input_unsupported('key_down')

    def key_up(self, key):
        self._input_unsupported('key_up')

    def hotkey(self, keys):
        self._input_unsupported('hotkey')
