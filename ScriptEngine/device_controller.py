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

import argparse
import asyncio
import base64
import faulthandler
import importlib
import json
import sys
import datetime
import os
import threading
import time


from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from ScriptEngine.custom_thread_pool import CustomThreadPool
script_logger = ScriptLogger()
from typing import Dict, List, NamedTuple, Optional
from ScriptEngine.managers.device_manager import DeviceManager
from ScriptEngine.managers.device_secrets_manager import DeviceSecretsManager
from ScriptEngine.common.script_engine_utils import DummyFile
from ScriptEngine.common.screenshot_failures import ScreenshotFailureTracker, SCREENSHOT_FAILURE_LIMIT_SECONDS
from ScriptEngine.common.logging.capture_log import CAPTURE_LOG, TAKEN_BY_ACTION

from ScriptEngine.helpers.device_action_interpreter import DeviceActionInterpreter
from ScriptEngine.helpers.live_input import parse_live_drag_args
from ScriptEngine.helpers.host_input import HostInputDeniedError
from ScriptEngine.common.device_slots import (
    HOST_DEFAULT_SLOTS, HOST_SLOT, LEGACY_TARGET_SYSTEMS, NO_DEVICE, device_fits_slot, device_type_of_id,
    is_required_slot, is_slot_name, map_child_slot, normalize_target, required_slots, slot_kind, slot_sort_key,
)


from ScriptEngine.common.constants.script_engine_constants import DATA_ROOT, DEVICES_CONFIG_PATH, LOGS_FOLDER
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

# Global lock for response writing to prevent interleaving
response_lock = asyncio.Lock()

# Per-device locks to ensure only one thread per device at a time
# Two lanes per device, so the editor's live view keeps getting screenshots
# while a drag or a typed text runs on the same device: a capture lane
# (screen_capture, check_status) and an input lane (everything else). Commands
# in one lane run one at a time, as every command on a device used to; the two
# lanes run side by side. A capture is a read (adb screencap, mss, a PiKVM
# snapshot, a DVT screenshot) on a channel of its own, so it does not disturb
# an input. What the two can share is setting the device up, and each guards
# that itself: DeviceController.initialize_device creates a manager under a
# lock, so two lanes never build two managers for one device, and
# ADBDeviceManager runs (re)initialization under its own lock and waits for a
# running input first, so a screencap timeout cannot restart adb under a drag.
CAPTURE_LANE_ACTIONS = frozenset({'screen_capture', 'check_status'})
device_locks: Dict[tuple, asyncio.Lock] = {}
device_locks_lock = asyncio.Lock()  # Lock for accessing device_locks dict


def device_lane(device_action):
    return 'capture' if device_action in CAPTURE_LANE_ACTIONS else 'input'


# Requests run in worker threads (asyncio.to_thread), so a device action that
# wedges leaves the event loop healthy and the process alive: the only symptom
# is that the response frame never reaches stdout and deviceinterface.mjs fails
# the command with a queue timeout minutes later. Dump every thread's stack once
# a request has been running this long, so the stuck frame ends up in the logs
# instead of being something to reproduce by hand.
STALL_DUMP_SECONDS = float(os.environ.get('SCREENPLAN_DEVICE_STALL_SECONDS', '30'))
stall_dump_lock = threading.Lock()


def get_stall_dump_path():
    return os.path.join(LOGS_FOLDER, '{}-device-controller-stalls.txt'.format(formatted_today))


def dump_stalled_request(request_id, inputs, started_at):
    """
    Write every thread's stack for a request that has not returned yet.

    The dump goes to a file of its own, never to stderr: deviceinterface.mjs
    rejects the in-flight request as soon as the child writes anything to
    stderr, so diagnostics sent there would break the request being diagnosed.
    """
    elapsed = time.monotonic() - started_at
    dump_path = get_stall_dump_path()
    try:
        with stall_dump_lock:
            with open(dump_path, 'a', encoding='utf-8') as dump_file:
                dump_file.write('\n===== {} request {} ({}) still running after {:.1f}s =====\n'.format(
                    datetime.datetime.now(), request_id, ' '.join(map(str, inputs[1:])), elapsed
                ))
                # faulthandler writes straight to the file descriptor, so the
                # buffered header has to be flushed first to keep the order.
                dump_file.flush()
                faulthandler.dump_traceback(file=dump_file, all_threads=True)
    except Exception as dump_error:
        script_logger.log('DEVICE CONTROLLER: could not write stall dump', dump_error, level='error')
        return
    script_logger.log(
        'DEVICE CONTROLLER: request {} still running after {:.1f}s, thread stacks written to {}'.format(
            request_id, elapsed, dump_path
        ),
        level='error'
    )


def start_stall_watchdog(request_id, inputs):
    """Arm a one-shot stall dump. The caller cancels the timer once the request returns."""
    watchdog = threading.Timer(
        STALL_DUMP_SECONDS, dump_stalled_request, args=(request_id, inputs, time.monotonic())
    )
    watchdog.daemon = True
    watchdog.start()
    return watchdog


def warm_request_path_imports():
    """
    Import what a device action needs here, on the main thread, before the event
    loop starts.

    parse_inputs runs inside asyncio.to_thread, so every module it imports lazily
    is imported from a worker thread the first time a command arrives. That
    includes scipy.stats, which ClickPathGenerator.generate_speed_path pulls in
    for every mouse move, and the desktop manager's own native stack. In the
    packaged (PyInstaller) build that first import did not return: a click logged
    its generated path and then nothing more, no response frame was ever written,
    and the controller failed the command on its queue timeout while the process
    itself stayed healthy. The same code run from the venv imports in well under a
    second. Doing the work here keeps it off the request path either way.
    """
    for module_name in ('scipy.stats', 'ScriptEngine.managers.desktop_device_manager'):
        started_at = time.monotonic()
        # Logged before as well as after: if a warm-up is what hangs, the last
        # line in the log names the module rather than leaving a process that
        # started and then never began listening.
        script_logger.log('DEVICE CONTROLLER: warming', module_name, level='debug')
        try:
            importlib.import_module(module_name)
        except Exception as import_error:
            # A host with no desktop stack still drives adb and kvm devices, so a
            # failed warm-up is worth reporting but not worth refusing to start over.
            script_logger.log('DEVICE CONTROLLER: could not warm', module_name, import_error, level='error')
        else:
            script_logger.log('DEVICE CONTROLLER: warmed {} in {:.2f}s'.format(
                module_name, time.monotonic() - started_at
            ), level='debug')


# Device types that drive something outside this host and therefore need a
# device attached to the run. 'python' is the host desktop itself, so it needs
# nothing attached.
DEVICE_TYPES_REQUIRING_ATTACHMENT = ('adb', 'kvm', 'ios')

# The key the host's own desktop is cached under (device slots: managers are
# cached per device, so device0, desktop0 and host share one when unbound).
HOST_DEVICE_KEY = 'host'
# The run's simulated device (a bare --device sim:), whatever slot an action names.
SIM_DEVICE_KEY = 'sim'

# Actions about an iOS device that is not registered yet - discovery, and the
# prerequisite checks and fixes behind the Add Device form's buttons. Named here
# rather than imported from the helper so that dispatching a request does not
# import pymobiledevice3; ios_setup_helper.SETUP_ACTIONS holds the handlers.
IOS_SETUP_ACTIONS = (
    'ios_list_devices',
    'ios_check_prerequisites',
    'ios_pair_device',
    'ios_reveal_developer_mode',
    'ios_mount_developer_image',
)


class ResolvedDevice(NamedTuple):
    """Where a target goes for this run: the slot it resolved to, and the device bound there."""
    # The run-level slot after the calling scripts' deviceMaps ('host' for the host).
    slot: str
    # The key the device manager is cached under: the device id, 'host', or a file key.
    key: str
    # The engine device type that drives it: python, adb, kvm or ios.
    device_type: str
    # What the action log records: the device id, 'host', or file:<path>.
    device_id: str
    # The device's host_devices_config.json record (None for the host and files).
    params: Optional[dict]
    # A still image the device reads instead of a screen (file: bindings).
    input_source: Optional[dict]


def load_file_input(device_value):
    """The input-source params of a file:<path> value: one still image, as a file: run has always read it."""
    file_path = ''.join(device_value.split(':')[1:])
    file_type = os.path.splitext(file_path)[1]
    script_logger.log('DEVICE CONTROLLER: loading input source', file_path, 'file exists', os.path.exists(file_path), level='info')
    from ScriptEngine.common.script_engine_utils import imageFileExtensions
    if file_type[1:] not in imageFileExtensions:
        raise Exception('file type not supported "' + file_type + '"')
    import cv2
    input_img = cv2.imread(file_path)
    height, width, _ = input_img.shape
    return {
        'script-engine-device-type': 'file',
        'screenshot': lambda: input_img,
        'width': width,
        'height': height,
    }


def how_to_bind(slot):
    """How a caller binds an unbound slot, for each way a run is started (the MCP tools, the studio, the command line)."""
    return ('Bind each when starting the script: devices: {{"{0}": "<device id>"}} in an MCP run_script or test_actions call, '
            'a device in the studio\'s device rows, or --device {0}=<device> on the command line.').format(slot)


class DeviceController:
    def __init__(self, default_props, default_device_params, io_executor : CustomThreadPool, secrets_manager: DeviceSecretsManager, device_selection=None,
                 restart_device_on_crash=False, restart_deadline=None, cancel_check=None,
                 screenshot_failure_limit_s=SCREENSHOT_FAILURE_LIMIT_SECONDS, bindings=None, all_slots_value=None):
        script_logger.log('Intializing Device Manager')
        if 'script-engine-device-type' in default_device_params and default_device_params['script-engine-device-type'] == 'file':
            self.input_source = default_device_params
        else:
            self.input_source = None
        
        self.default_props = default_props
        self.default_device_params = default_device_params
        self.io_executor = io_executor
        self.secrets_manager = secrets_manager
        # What the run asked to attach ('--device'), kept only so a missing
        # device is reported in terms of the choice the caller made rather than
        # the empty params dict it produced. None when nothing was selected.
        self.device_selection = device_selection
        # Passed on to device managers that can restart their device when
        # reconnecting fails ('--restart-device-on-crash'); restart_deadline is
        # the script's end time, after which they stop retrying.
        self.restart_device_on_crash = restart_device_on_crash
        self.restart_deadline = restart_deadline
        # Returns True once the run has been cancelled, so those reconnect and
        # restart loops stop instead of running on until the deadline.
        self.cancel_check = cancel_check
        # How long a device's screenshots may keep failing before that ends the
        # run. None for the interactive controller, which has no run to end.
        self.screenshot_failure_limit_s = screenshot_failure_limit_s

        # Device slots: the run's bindings, slot -> device id, 'host' or
        # file:<path> (parse_device_bindings). A bare file: value is a still
        # image for every slot, the host included, as a file: run always was.
        self.bindings: Dict[str, str] = dict(bindings or {})
        # A bare sim: value is a simulated device for every slot, the host
        # included (UI_MAPPER.md §4): script_manager passes its params as the
        # default device params, and resolve() sends every target to it.
        self.simulated = (default_device_params or {}).get('script-engine-device-type') == 'sim'
        if all_slots_value is not None and self.input_source is None and not self.simulated:
            self.input_source = load_file_input(all_slots_value)
        self._file_inputs: Dict[str, dict] = {}
        # One map per running script, child slot -> run-level slot, composed
        # through each scriptReference's deviceMap (push_slot_map).
        self._slot_maps: List[Dict[str, str]] = [{}]

        # Device managers by device key (the device id, 'host', a file key),
        # so two phones are two managers and every slot bound to one device
        # shares its manager.
        self.devices: Dict[str, DeviceManager] = {}
        # Reentrant: setting one device up may resolve another through here.
        self._initialize_device_lock = threading.RLock()
        # Keyed like self.devices.
        self.screenshot_failures: Dict[str, ScreenshotFailureTracker] = {}

    # ------------------------------------------------------------------
    # slot resolution

    def push_slot_map(self, device_map):
        """Enter a child script: its slots map onto the caller's through the scriptReference's deviceMap."""
        parent = self._slot_maps[-1]
        composed = {}
        for child_slot, parent_slot in (device_map or {}).items():
            if not is_slot_name(child_slot):
                continue
            mapped = map_child_slot(child_slot, device_map)
            composed[child_slot] = parent.get(mapped, mapped)
        # A child slot it leaves out maps to the caller's slot of the same
        # name, which may itself be mapped further up.
        for caller_slot, run_slot in parent.items():
            composed.setdefault(caller_slot, run_slot)
        self._slot_maps.append(composed)

    def pop_slot_map(self):
        if len(self._slot_maps) > 1:
            self._slot_maps.pop()

    def run_slot(self, target):
        """The run-level slot a target names in the running script: blank is device0, then the deviceMaps."""
        slot = normalize_target(target)
        if slot in (HOST_SLOT, NO_DEVICE) or slot in LEGACY_TARGET_SYSTEMS:
            return slot
        return self._slot_maps[-1].get(slot, slot)

    def _host(self, slot):
        return ResolvedDevice(slot, HOST_DEVICE_KEY, 'python', HOST_SLOT, None, self.input_source)

    def _sim(self, target):
        """The run's simulated device, for any target: one sim answers every slot, the host and the v22 types."""
        if target in LEGACY_TARGET_SYSTEMS:
            slot, device_type = target, target
        else:
            slot = self.run_slot(target)
            # The type an action on this slot would have: a phone or tablet
            # reads like an adb device, anything else like the desktop.
            device_type = 'adb' if slot_kind(slot) in ('phone', 'tablet') else 'python'
        params = self.default_device_params
        return ResolvedDevice(slot, SIM_DEVICE_KEY, device_type, params.get('deviceId', 'sim'), params, None)

    def _file_device(self, slot, value):
        if value not in self._file_inputs:
            self._file_inputs[value] = load_file_input(value)
        # A still image has no driver: a phone or tablet slot reads it the way
        # an adb device would, anything else the way the desktop does.
        device_type = 'adb' if slot_kind(slot) in ('phone', 'tablet') else 'python'
        params = self._file_inputs[value]
        return ResolvedDevice(slot, '{}#{}'.format(value, device_type), device_type, value, params, params)

    def resolve(self, target) -> ResolvedDevice:
        """The device an action's target acts on (device slots, docs/specs/device-slots.md).

        A slot goes through the running scripts' deviceMaps, then the run's
        bindings; device0 and desktop0 left unbound are the host, every other
        unbound slot is an error naming it. `host` is always the host. A v22
        driver type ('python', 'adb', ...) still resolves, for the engine's
        own calls (system scripts) and for files the loader could not map.
        """
        if target == NO_DEVICE:
            raise Exception("DEVICE CONTROLLER: an action with target 'none' needs no device")
        if self.simulated:
            return self._sim(target)
        if target in LEGACY_TARGET_SYSTEMS:
            return self._resolve_legacy(target)
        slot = self.run_slot(target)
        if slot == HOST_SLOT:
            return self._host(slot)
        value = self.bindings.get(slot)
        if value is None:
            if self.input_source is not None:
                # A bare file: binds every slot.
                device_type = 'adb' if slot_kind(slot) in ('phone', 'tablet') else 'python'
                key = HOST_DEVICE_KEY if device_type == 'python' else 'file:*#adb'
                return ResolvedDevice(slot, key, device_type, 'file', self.input_source, self.input_source)
            if slot in HOST_DEFAULT_SLOTS:
                return self._host(slot)
            raise Exception(
                'DEVICE CONTROLLER: action needs slot {}, and the run bound nothing to it: '
                'add {}=<device> when starting the script{}.'.format(
                    slot, slot,
                    '' if normalize_target(target) == slot else " (the script's own slot {} maps to {} through a scriptReference's deviceMap)".format(
                        normalize_target(target), slot)
                )
            )
        if value == HOST_SLOT:
            return self._host(slot)
        if value.startswith('file:'):
            return self._file_device(slot, value)
        device_type = self.device_id_to_device_type(value)
        if device_type == 'python':
            return self._host(slot)
        params = self.get_device_params(value)
        if params is None:
            raise Exception(
                'DEVICE CONTROLLER: slot {} is bound to {}, which {} no longer holds. Reconnect it '
                'on the controller, or bind a different device ({}=<device>).'.format(
                    slot, value, DEVICES_CONFIG_PATH, slot)
            )
        params = dict(params)
        params.setdefault('deviceId', value)
        return ResolvedDevice(slot, value, device_type, value, params, self.input_source)

    def _resolve_legacy(self, device_type):
        """A v22 driver type: the host for 'python', else the bound device of that type (phone0/desktop0 first)."""
        if device_type == 'python':
            return self._host(HOST_SLOT)
        preferred = 'desktop0' if device_type == 'kvm' else 'phone0'
        candidates = [preferred] + sorted((s for s in self.bindings if s != preferred), key=slot_sort_key)
        for slot in candidates:
            value = self.bindings.get(slot)
            if value and not value.startswith('file:') and value != HOST_SLOT \
                    and device_type_of_id(value) == device_type:
                return self.resolve(slot)
        if self.input_source is not None:
            return ResolvedDevice(preferred, 'file:*#' + device_type, device_type, 'file', self.input_source, self.input_source)
        if self.default_device_params and not self.bindings:
            # A caller from before slots built this controller around one
            # device's record, the run's device of whatever type was asked for.
            params = self.default_device_params
            return ResolvedDevice(preferred, device_type, device_type, params.get('deviceId', device_type), params, None)
        self._require_attached_device(device_type)

    def check_child_slots(self, script_obj, script_name=''):
        """Raise when a child script about to run needs a slot that maps to an unbound required run slot."""
        if self.input_source is not None or self.simulated:
            return
        missing = []
        for slot, description in required_slots(script_obj.get('props'), script_obj.get('actionRows')).items():
            run = self.run_slot(slot)
            if is_required_slot(run) and run not in self.bindings:
                missing.append('{}{}{}'.format(
                    run, '' if run == slot else ' (its {})'.format(slot), ': ' + description if description else ''))
        if missing:
            raise Exception(
                'DEVICE CONTROLLER: script {} needs device slots the run bound nothing to: {}. '
                '{}'.format(script_name, ', '.join(missing), how_to_bind(missing[0].split(' ')[0].rstrip(':')))
            )

    def describe_target(self, target):
        """(slot, device id) for the action log; never raises. (None, None) for an action that needs no device."""
        if target == NO_DEVICE:
            return None, None
        try:
            resolved = self.resolve(target)
            return resolved.slot, resolved.device_id
        except Exception:
            try:
                return self.run_slot(target), None
            except Exception:
                return None, None

    def device_key(self, target):
        """The key a target's device is cached under: parallel groups share one screenshot per key."""
        return self.resolve(target).key

    def check_bindings(self, required, adb_slots=()):
        """The run-start check: (errors, warnings). required: {slot: [descriptions]} (static_required_slots)."""
        errors, warnings = [], []
        whole_run = self.input_source is not None or self.simulated
        missing = [slot for slot in required if slot not in self.bindings and not whole_run]
        if missing:
            lines = []
            for slot in missing:
                notes = required[slot]
                lines.append('  {}{}'.format(slot, ': ' + '; '.join(notes) if notes else ''))
            errors.append(
                'DEVICE CONTROLLER: the script needs these device slots, and the run bound nothing to them:\n'
                + '\n'.join(lines)
                + '\n' + how_to_bind(missing[0])
            )
        for slot, value in sorted(self.bindings.items(), key=lambda kv: slot_sort_key(kv[0])):
            if value.startswith('file:') or value == HOST_SLOT:
                if value == HOST_SLOT and slot_kind(slot) in ('phone', 'tablet'):
                    warnings.append('DEVICE CONTROLLER: slot {} is a {} slot, bound to the host desktop'.format(slot, slot_kind(slot)))
                continue
            if device_type_of_id(value) is None:
                errors.append("DEVICE CONTROLLER: slot {} is bound to '{}', whose type prefix is unknown "
                              '(known: avd, bluestacks, adb, pikvm, ios, host, file).'.format(slot, value))
                continue
            if not device_fits_slot(slot, value):
                warnings.append('DEVICE CONTROLLER: slot {} is a {} slot, bound to {} (a {} device); running it anyway'.format(
                    slot, slot_kind(slot), value, device_type_of_id(value)))
        for slot in sorted(adb_slots, key=slot_sort_key):
            value = self.bindings.get(slot)
            if value and not value.startswith('file:') and device_type_of_id(value) != 'adb':
                errors.append('DEVICE CONTROLLER: an ADB configuration action acts on slot {}, which is bound to {}, '
                              'not an adb device.'.format(slot, value))
        return errors, warnings

    # ------------------------------------------------------------------
    # device managers

    def _require_attached_device(self, device_type):
        """Raises when a v22-style call needs a device of a type the run did not bind."""
        slot = 'desktop0' if device_type == 'kvm' else 'phone0'
        if self.device_selection:
            raise Exception(
                'DEVICE CONTROLLER: this script has actions that require a {} device, and the run '
                "was started with device '{}', but no configuration for that device exists in {}, "
                'or it is not a {} device. Reconnect it on the controller, or bind a different '
                'device ({}=<device>).'.format(device_type, self.device_selection, DEVICES_CONFIG_PATH, device_type, slot)
            )
        raise Exception(
            'DEVICE CONTROLLER: this script has actions that require a {} device, but the run bound '
            'none: add {}=<device> when starting the script.'.format(device_type, slot)
        )

    def _resolve_device_params(self, device_id, device_type):
        """Config for an explicitly named device, or a message saying which one is gone.

        get_device_params logs and returns None for an id the config does not
        hold; the callers then subscripted that None. Same failure as an
        unattached run, reached from the interactive device controller instead.
        """
        params = self.get_device_params(device_id)
        if params is None:
            raise Exception(
                "DEVICE CONTROLLER: device '{}' was requested for a {} action, but no "
                'configuration for it exists in {}. Reconnect it on the controller, or '
                'pick a different device.'.format(device_id, device_type, DEVICES_CONFIG_PATH)
            )
        return params

    def _explicit_type(self, target, device_params):
        """The device type of a call that names its device (the interactive controller)."""
        if target in LEGACY_TARGET_SYSTEMS:
            return target
        if target == HOST_SLOT:
            return 'python'
        return self.device_id_to_device_type(device_params['deviceId'])

    def _resolve_call(self, target, device_params):
        if device_params is not None:
            device_type = self._explicit_type(target, device_params)
            key = device_params['deviceId']
            return ResolvedDevice(target, key, device_type, key, None, self.input_source)
        return self.resolve(target)

    def initialize_device(self, target, device_params=None):
        # The device controller process calls this from both of a device's
        # lanes at once; without the lock both could build a manager for it.
        with self._initialize_device_lock:
            return self._initialize_device_unlocked(target, device_params)

    def _initialize_device_unlocked(self, target, device_params=None):
        resolved = self._resolve_call(target, device_params)
        if resolved.key in self.devices:
            return self.devices[resolved.key]
        device_type = resolved.device_type
        params = resolved.params
        if device_params is not None and device_type != 'python':
            # The interactive controller names a configured device.
            params = self._resolve_device_params(device_params['deviceId'], device_type)

        if resolved.key == SIM_DEVICE_KEY or device_type == 'sim' or str(resolved.key).startswith('sim:'):
            # The run's sim (resolve), or a sim: device the interactive
            # controller names, from its host_devices_config.json entry.
            from ScriptEngine.managers.simulated_device_manager import SimulatedDeviceManager
            manager = SimulatedDeviceManager(self.default_props.copy(), params)
        elif device_type == 'python':
            from ScriptEngine.managers.desktop_device_manager import DesktopDeviceManager
            manager = DesktopDeviceManager(self.default_props.copy(), resolved.input_source)
        elif device_type == 'adb':
            from ScriptEngine.managers.adb_device_manager import ADBDeviceManager
            manager = ADBDeviceManager(
                self.default_props.copy(), params, resolved.input_source,
                restart_device_on_crash=self.restart_device_on_crash, restart_deadline=self.restart_deadline,
                cancel_check=self.cancel_check
            )
        elif device_type == 'ios':
            from ScriptEngine.managers.ios_device_manager import IOSDeviceManager
            manager = IOSDeviceManager(self.default_props.copy(), params, resolved.input_source)
        elif device_type == 'kvm':
            from ScriptEngine.managers.pikvm_device_manager import PiKVMDeviceManager
            password = self.secrets_manager.get_secret(params['passwordName'])
            manager = PiKVMDeviceManager(params['ip'], params['username'], password, resolved.input_source)
        else:
            raise Exception('DEVICE CONTROLLER: no device manager for type {}'.format(device_type))
        self.devices[resolved.key] = manager
        return manager

    def get_screenshot_failures(self, target, device_params=None) -> ScreenshotFailureTracker:
        resolved = self._resolve_call(target, device_params)
        if resolved.key not in self.screenshot_failures:
            if device_params is not None or resolved.key in LEGACY_TARGET_SYSTEMS:
                device_name = resolved.device_id
            else:
                device_name = '{} (slot {})'.format(resolved.device_id, resolved.slot)
            self.screenshot_failures[resolved.key] = ScreenshotFailureTracker(
                device_name, limit_s=self.screenshot_failure_limit_s
            )
        return self.screenshot_failures[resolved.key]

    def get_device_action(self, target, action_type, device_params=None, taken_by=TAKEN_BY_ACTION):
        """The device's method for `action_type` on `target` (a slot, host, or a
        legacy driver type). For a screenshot, `taken_by` says who it is for
        (capture_log.py): an action to work on, or a log thread to draw on
        after the action has acted. None records nothing, for screenshots
        outside a run."""
        device = self.initialize_device(target, device_params)
        action_method_map = {
            'mouse_move': 'smooth_move'
        }
        method_name = action_method_map.get(action_type, action_type)
        device_action = getattr(device, method_name)
        if action_type == 'screenshot':
            # A screenshot that cannot be taken raises ScreenshotFailedError, which
            # the action executor turns into a FAILURE, until the device has
            # failed for the whole limit (ScreenshotFailureLimitError ends the run).
            screenshot_failures = self.get_screenshot_failures(target, device_params)
            if taken_by is None:
                return lambda *args, **kwargs: screenshot_failures.capture(lambda: device_action(*args, **kwargs))
            return lambda *args, **kwargs: CAPTURE_LOG.record(
                screenshot_failures.capture(lambda: device_action(*args, **kwargs)), taken_by
            )
        return device_action
    
    def ensure_device_initialized(self, target, device_params=None):
        device = self.initialize_device(target, device_params)
        # The kvm, desktop and ios managers take a screenshot here to learn the
        # screen size, and adb's checks the device answers, so a click that
        # cannot initialize its device fails the way a detect that cannot see
        # does. A device that is already initialized does nothing here, and that
        # is no evidence the screen can be read now: only a call that had work
        # to do resets the failure timer.
        already_initialized = getattr(device, 'width', None) is not None and getattr(device, 'height', None) is not None
        self.get_screenshot_failures(target, device_params).capture(
            device.ensure_device_initialized, counts_as_success=not already_initialized
        )
            
    
    def get_device_attribute(self, target, attribute_name, device_params=None):
        device = self.initialize_device(target, device_params)
        return getattr(device, attribute_name)
    
    def device_id_to_device_type(self, device_id):
        if ':' not in device_id:
            device_type = 'python'
        else:
            device_subtype = device_id.split(':')[0]
            if device_subtype == 'avd' or device_subtype == 'bluestacks' or device_subtype == 'adb':
                device_type = 'adb'
            elif device_subtype == 'pikvm':
                device_type = 'kvm'
            elif device_subtype == 'ios':
                device_type = 'ios'
            elif device_subtype == 'sim':
                device_type = 'sim'
            else:
                # Without this, an unrecognized prefix left device_type unbound and
                # the request failed with UnboundLocalError, which names neither the
                # device nor the prefix that was not understood.
                raise Exception(
                    "DEVICE CONTROLLER: device '{}' has an unrecognized type prefix '{}'. Known "
                    'prefixes are avd, bluestacks, adb, pikvm, ios and sim.'.format(device_id, device_subtype)
                )
        return device_type

    @staticmethod
    def get_device_params(device_key):
        params = None
        with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
            devices_config = json.load(devices_config_file)
            if device_key in devices_config:
                params = devices_config[device_key]
            else:
                script_logger.log('DEVICE CONTROLLER: device config for ', device_key, ' not found! ', level='error')
        script_logger.log('DEVICE CONTROLLER: loading args', params, level='debug')
        return params
    
    def parse_inputs(self, inputs):
        device_key = inputs[1]
        device_action = inputs[2]

        # Answered before any device is resolved: these report on what is attached
        # to the host and on a device's prerequisites, which the Add Device form
        # asks about while registering a device that has no configuration yet. A
        # device key is still sent so the controller's per-device lock serializes
        # them, but it names no configured device and nothing here looks it up.
        if device_action in IOS_SETUP_ACTIONS:
            from ScriptEngine.helpers.ios_setup_helper import run_setup_action
            return {
                "data": run_setup_action(device_action, inputs[3] if len(inputs) > 3 else None)
            }

        device_type = self.device_id_to_device_type(device_key)
        script_logger.log('DEVICE CONTROLLER: device type', device_type, device_key, level='debug')
        device_params = {
            'deviceId' : device_key
        }

        if device_action == 'check_status':
            status = self.get_device_action(device_type, 'get_status', device_params)()
            output = {
                "data": status
            }
            # The host's own screen also says whether it takes input: macOS
            # drops every click and key when the controller's launcher lacks
            # Accessibility, while the screen stays online for captures.
            try:
                input_status = self.get_device_attribute(device_type, 'get_input_status', device_params)
            except AttributeError:
                input_status = None
            if input_status is not None:
                output.update(input_status())
            return output
        elif device_action == 'screen_capture':
            screenshot = self.get_device_action(device_type, 'screenshot', device_params, taken_by=None)()
            from cv2 import imencode
            _, buffer = imencode('.jpg', screenshot)
            byte_array = buffer.tobytes()
            base64_encoded_string = base64.b64encode(byte_array).decode('utf-8')
            return {
                "data": base64_encoded_string
            }
        elif device_action == "click":
            # process_adb_host.get_screen_orientation()
            self.get_device_action(device_type, 'click', device_params)(int(float(inputs[3])), int(float(inputs[4])), 'left')
            return {
                "data" : "success"
            }
        elif device_action == "click_and_drag":
            # process_adb_host.get_screen_orientation()
            coordinates = [int(float(value)) for value in inputs[3:7]]
            # `live <durationMs>` after the coordinates is the editor's drag:
            # a short path over the gesture's own time (helpers/live_input.py).
            live_duration_ms = parse_live_drag_args(inputs[7:])
            if live_duration_ms is None:
                self.get_device_action(device_type, 'click_and_drag', device_params)(*coordinates)
            else:
                self.get_device_action(device_type, 'live_drag', device_params)(*coordinates, live_duration_ms)
            return {
                "data" : "success"
            }
        elif device_action == "send_keys":
            DeviceActionInterpreter.parse_keyboard_action(
                self, json.loads(inputs[3]), {}, {}, device_params
            )
            return {
                "data": "success"
            }
        elif device_action == "list_applications":
            applications = self.get_device_action(device_type, 'list_applications', device_params)()
            return {
                "data": applications
            }
        elif device_action == "start_application":
            self.get_device_action(device_type, 'start_application', device_params)(inputs[3], [])
            return {
                "data": "success"
            }
        elif device_action == "stop_application":
            self.get_device_action(device_type, 'stop_application', device_params)(inputs[3])
            return {
                "data": "success"
            }



async def get_device_lock(device_key: str, lane: str = 'input') -> asyncio.Lock:
    """Get or create the lock for one lane of a device (see CAPTURE_LANE_ACTIONS)."""
    async with device_locks_lock:
        key = (device_key, lane)
        if key not in device_locks:
            device_locks[key] = asyncio.Lock()
        return device_locks[key]

async def process_input(device_controller: DeviceController, inputs: list):
    """Process a single input with per-device locking and global response locking."""
    device_key = inputs[1]
    request_id = inputs[0]
    
    # Get the lock for this device's lane: captures wait only for captures,
    # inputs only for inputs.
    device_lock = await get_device_lock(device_key, device_lane(inputs[2]))
    
    # Wait for this lane of the device to be free
    async with device_lock:
        stall_watchdog = start_stall_watchdog(request_id, inputs)
        try:
            # Process the input in a thread pool (non-blocking for event loop)
            output = await asyncio.to_thread(device_controller.parse_inputs, inputs)
        except HostInputDeniedError as e:
            # No "data": the controller answers a request without it as failed,
            # where "device controller error" would read as done.
            script_logger.log('DEVICE CONTROLLER: input refused', inputs, e, level='error')
            output = {
                "data": None,
                "error": str(e),
                "code": e.code
            }
        except Exception as e:
            script_logger.log('DEVICE CONTROLLER: error in parse_inputs', inputs, e, level='error')
            output = {
                "data" : "device controller error"
            }
        finally:
            stall_watchdog.cancel()
        
        # Write response with global lock to prevent interleaving
        async with response_lock:
            input_response = json.dumps(output)
            script_logger.log('DEVICE CONTROLLER: Sending response for {}'.format(request_id), flush=True)
            # level='error' so the frame is never dropped by the verbosity filter.
            # This is not a log line the user reads, it is the response itself: the
            # host parses it out of stdout. At the default 'info' it was suppressed
            # whenever the controller ran at log level 'error' - which happens as
            # soon as the Script-Engine-Controller's own level is warning or error,
            # since getDeviceControllerLogLevel() maps both of those to 'error' -
            # and then every device command, for every device type, failed on its
            # five-minute queue timeout instead of answering.
            script_logger.log(
                '<--{}-->'.format(request_id) + input_response + '<--{}-->'.format(request_id),
                file=DummyFile(), flush=True, level='error'
            )
            # script_logger.log('DEVICE CONTROLLER: response', input_response, flush=True)
            script_logger.log('DEVICE CONTROLLER: Response sent for {}'.format(request_id), flush=True)

async def read_input(device_controller: DeviceController):
    script_logger.log("DEVICE CONTROLLER PROCESS: listening for input")
    input_line = ''
    while True:
        input_line += await asyncio.to_thread(sys.stdin.readline)
        # Process the input
        if not input_line:  # EOF, if the pipe is closed
            break
        inputs = input_line.strip().split('###')
        if len(inputs) <= 2:
            script_logger.log('DEVICE CONTROLLER PROCESS: received partial inputs ', inputs, level='debug')
            continue
        inputs = inputs[0:2] + inputs[2].split(' ')
        input_line = ''
        script_logger.log('DEVICE CONTROLLER PROCESS: received inputs ', inputs, level='debug')
        if len(inputs) > 2:
            # Process input asynchronously (will queue per device automatically)
            asyncio.create_task(process_input(device_controller, inputs))

async def device_controller_main(device_controller: DeviceController):
    await asyncio.gather(read_input(device_controller))

def parse_args():
    parser = argparse.ArgumentParser(description='ScreenPlan device controller')
    parser.add_argument('--log-level', '-l', default='info', choices=['debug', 'info', 'error'],
                        help='Logging level, mirroring the Script-Engine-Controller that spawned '
                             'this process: debug = every log including the per-request input and '
                             'device-type traces; info = info/error only; error = errors only')
    # Declared so it shows in --help and is not reported as unrecognized. The
    # value itself is read from sys.argv by script_engine_constants at import
    # time, before this parser runs.
    parser.add_argument('--data-root',
                        help="Root of the controller's data folder (tmp/, logs/, certs/, scripts/). "
                             'Defaults to $SCREENPLAN_DATA_ROOT, then the per-user app data folder.')
    # parse_known_args, not parse_args: runStartDeviceController.bat/.sh forward
    # their arguments after `-m ScriptEngine.device_controller`, so a Python flag
    # meant for the interpreter (`-u`) arrives here as a script argument instead.
    # Refusing to start over a stray argument would be worse than ignoring it.
    return parser.parse_known_args()


if __name__ == '__main__':
    cli_args, unknown_args = parse_args()
    os.makedirs(LOGS_FOLDER, exist_ok=True)
    script_logger.set_log_level(cli_args.log_level)
    script_logger.set_log_file_path(os.path.join(LOGS_FOLDER, '{}-device-controller-main.txt'.format(formatted_today)))
    script_logger.set_log_header('{}-device-controller-main-'.format(formatted_today))
    script_logger.set_log_folder(LOGS_FOLDER + '/')
    script_logger.set_action_log(ScriptActionLog(
        {
            'actionName' : 'configurationAction',
            'actionGroup' : 0,
            'actionData' : {
                'targetSystem': 'host'
            }
        },
        script_logger.get_log_folder(),
        script_logger.get_log_header(),
        0
    ))
    script_logger.log('DEVICE CONTROLLER: starting at log level', cli_args.log_level)
    if unknown_args:
        script_logger.log('DEVICE CONTROLLER: ignoring unrecognized arguments', unknown_args, level='debug')
    warm_request_path_imports()
    with CustomThreadPool(max_workers=50) as io_executor:
        asyncio.run(device_controller_main(DeviceController({
            # No script folder of its own, so actions that resolve per-script
            # files (jsonFileAction's tmp/) land under the controller's data
            # root. This used to be "./", which meant the same thing only
            # because the data root was the working directory.
            "dir_path": DATA_ROOT,
            "width" : None,
            "height" : None,
            "scriptMode" : 'train'

        }, {}, io_executor, DeviceSecretsManager(), screenshot_failure_limit_s=None)))
        asyncio.run(io_executor.soft_shutdown(script_logger))
