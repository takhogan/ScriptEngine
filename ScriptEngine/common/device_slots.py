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

"""Device slots (interface version 23, workspace docs/specs/device-slots.md).

An action's targetSystem names the slot it acts on (device0, desktop0,
phone1, ...), or `host` (always this machine's screen) or `none` (no device).
The run binds slots to devices with `--device`. This module holds the pure
parts, kept equal to @screenplan/script-vcs (src/slots.ts, migrate.ts):

- parse_device_bindings: the `--device` values, bare values included;
- map_v22_script: the load-time copy of migrateV22ToV23, for files a host
  still holds at v22 (a rollback, a deploy before the bulk migration);
- required_slots / static_required_slots: the run-start check.
"""

import re

SLOT_KINDS = ('device', 'desktop', 'phone', 'tablet')
SLOT_NAME_PATTERN = re.compile(r'^(device|desktop|phone|tablet)(\d+)$')
HOST_SLOT = 'host'
NO_DEVICE = 'none'
DEFAULT_SLOT = 'device0'
# Left unbound, these are the host's own desktop, so they are never required.
HOST_DEFAULT_SLOTS = frozenset({'device0', 'desktop0'})
LEGACY_TARGET_SYSTEMS = frozenset({'python', 'adb', 'kvm', 'ios'})
# Every slot a bare file: value binds (what a file: run did before slots).
ALL_SLOTS = '*'
DEVICES_INTERFACE_VERSION = 23

# The device types a slot kind fits; stage 1 only warns on a mismatch.
KIND_DEVICE_TYPES = {
    'device': None,
    'desktop': ('python', 'kvm'),
    'phone': ('adb', 'ios'),
    'tablet': ('adb', 'ios'),
}


class DeviceBindingError(Exception):
    """A --device value that cannot be read, or binds a slot twice."""


def is_slot_name(value):
    return isinstance(value, str) and SLOT_NAME_PATTERN.match(value) is not None


def is_valid_target(value):
    return value in (None, '', HOST_SLOT, NO_DEVICE) or is_slot_name(value)


def normalize_target(value):
    """Blank means device0; host, none and slot names stay as they are."""
    if value is None or value == '':
        return DEFAULT_SLOT
    return str(value)


def slot_kind(slot):
    m = SLOT_NAME_PATTERN.match(slot or '')
    return m.group(1) if m else None


def is_required_slot(slot):
    return is_slot_name(slot) and slot not in HOST_DEFAULT_SLOTS


def slot_sort_key(slot):
    m = SLOT_NAME_PATTERN.match(slot)
    if not m:
        return (len(SLOT_KINDS), 0, slot)
    return (SLOT_KINDS.index(m.group(1)), int(m.group(2)), '')


def device_type_of_id(device_id):
    """The engine device type of a device id (DeviceController.device_id_to_device_type), None if unknown."""
    if not device_id or device_id == HOST_SLOT or ':' not in device_id:
        return 'python'
    prefix = device_id.split(':', 1)[0]
    if prefix in ('avd', 'bluestacks', 'adb'):
        return 'adb'
    if prefix == 'ios':
        return 'ios'
    if prefix == 'pikvm':
        return 'kvm'
    return None


def device_fits_slot(slot, device_id):
    kind = slot_kind(slot)
    types = KIND_DEVICE_TYPES.get(kind) if kind else None
    if not types or device_id.startswith('file:'):
        return True
    return device_type_of_id(device_id) in types


def default_slot_for_device_id(device_id):
    """The slot a bare value binds: adb/iOS phone0, PiKVM and host desktop0, file: every slot, else device0."""
    if device_id == HOST_SLOT:
        return 'desktop0'
    if device_id.startswith('file:'):
        return ALL_SLOTS
    prefix = device_id.split(':', 1)[0] if ':' in device_id else ''
    if prefix in ('avd', 'bluestacks', 'adb', 'ios'):
        return 'phone0'
    if prefix == 'pikvm':
        return 'desktop0'
    return DEFAULT_SLOT


_ENTRY_START = re.compile(r',(?=\s*(?:(?:device|desktop|phone|tablet)\d+|host|none)\s*=)')


def _split_entries(value):
    """A comma ends an entry only when what follows starts with `<slot>=`."""
    return [part.strip() for part in _ENTRY_START.split(value)]


def parse_device_bindings(values):
    """The run's bindings from its --device values: (bindings, all_slots_value).

    `values` is a string, a list of strings (the repeated-flag form) or None.
    Each entry is `slot=device` (split at the first `=` only) or a bare value,
    which binds its type's default slot. A bare file: value binds every slot,
    returned as all_slots_value. Empty values and 'null' bind nothing. Binding
    a slot twice, or the slots host and none, is an error.
    """
    if values is None:
        return {}, None
    if isinstance(values, str):
        values = [values]
    bindings = {}
    all_slots_value = None
    for value in values:
        if value is None:
            continue
        for entry in _split_entries(str(value)):
            if entry in ('', 'null'):
                continue
            slot, device = None, entry
            if '=' in entry:
                head, tail = entry.split('=', 1)
                head = head.strip()
                if is_slot_name(head) or head in (HOST_SLOT, NO_DEVICE):
                    slot, device = head, tail.strip()
            if slot in (HOST_SLOT, NO_DEVICE):
                raise DeviceBindingError(
                    "--device {}: the slot '{}' cannot be bound ({})".format(
                        entry, slot, 'always this machine' if slot == HOST_SLOT else 'it means no device'))
            if device in ('', 'null'):
                continue
            if slot is None:
                slot = default_slot_for_device_id(device)
                if slot == ALL_SLOTS:
                    if all_slots_value is not None:
                        raise DeviceBindingError('--device {}: a still image for every slot is given twice'.format(entry))
                    all_slots_value = device
                    continue
            if slot in bindings:
                raise DeviceBindingError(
                    "--device: slot {} is bound twice ({} and {})".format(slot, bindings[slot], device))
            bindings[slot] = device
    return bindings, all_slots_value


def map_child_slot(child_slot, device_map):
    """A child script's slot in its parent: through deviceMap, else the same name. host and none stay."""
    slot = normalize_target(child_slot)
    if slot in (HOST_SLOT, NO_DEVICE):
        return slot
    mapped = device_map.get(slot) if isinstance(device_map, dict) else None
    if mapped in (None, ''):
        return slot
    return normalize_target(mapped)


def _actions(action_rows):
    for row in action_rows or []:
        for action in (row or {}).get('actions') or []:
            if isinstance(action, dict):
                yield action


def used_slots(action_rows):
    """The slots a script's actions use, sorted: targets (blank = device0) and deviceMap parent slots."""
    out = set()
    for action in _actions(action_rows):
        data = action.get('actionData')
        if not isinstance(data, dict):
            continue
        if 'targetSystem' in data:
            slot = normalize_target(data['targetSystem'])
            if is_slot_name(slot):
                out.add(slot)
        if action.get('actionName') == 'scriptReference' and isinstance(data.get('deviceMap'), dict):
            for parent in data['deviceMap'].values():
                slot = normalize_target(parent)
                if is_slot_name(slot):
                    out.add(slot)
    return sorted(out, key=slot_sort_key)


def sync_device_slots(action_rows, devices):
    """props.devices in step with the actions (syncDeviceSlots in @screenplan/script-vcs)."""
    existing = {}
    for entry in devices if isinstance(devices, list) else []:
        if isinstance(entry, dict) and is_slot_name(entry.get('slot')) and entry['slot'] not in existing:
            existing[entry['slot']] = entry
    used = used_slots(action_rows)
    if not used and not isinstance(devices, list):
        return None
    out = []
    for slot in used:
        entry = existing.get(slot)
        if entry is None:
            out.append({'slot': slot})
            continue
        entry = dict(entry)
        entry['slot'] = slot
        if entry.get('description') in (None, ''):
            entry.pop('description', None)
        out.append(entry)
    return out


def migrate_target_system(value, mixes_python_and_kvm):
    if value == 'python':
        return HOST_SLOT if mixes_python_and_kvm else 'desktop0'
    if value == 'kvm':
        return 'desktop0'
    if value in ('adb', 'ios'):
        return 'phone0'
    return value


def mixes_python_and_kvm(action_rows):
    targets = {(a.get('actionData') or {}).get('targetSystem') for a in _actions(action_rows)}
    return 'python' in targets and 'kvm' in targets


def has_legacy_targets(action_rows, props=None):
    for action in _actions(action_rows):
        if (action.get('actionData') or {}).get('targetSystem') in LEGACY_TARGET_SYSTEMS:
            return True
    reference = (props or {}).get('scriptReference')
    if isinstance(reference, dict) and (reference.get('actionData') or {}).get('targetSystem') in LEGACY_TARGET_SYSTEMS:
        return True
    return False


def map_v22_script(action_rows, props, interface_version=None):
    """The load-time copy of migrateV22ToV23, in place. Returns True if it changed anything.

    Runs on a script below interface version 23 (or with no version file),
    and only touches driver-type targets, so a v23 script is never changed.
    The table: python -> desktop0 (host in a script that mixes python and kvm),
    kvm -> desktop0, adb/ios -> phone0, none stays; props.devices then lists
    the used slots.
    """
    if interface_version is not None and interface_version >= DEVICES_INTERFACE_VERSION:
        return False
    if not has_legacy_targets(action_rows, props):
        return False
    mixed = mixes_python_and_kvm(action_rows)
    for action in _actions(action_rows):
        data = action.get('actionData')
        if isinstance(data, dict) and 'targetSystem' in data:
            data['targetSystem'] = migrate_target_system(data['targetSystem'], mixed)
    if isinstance(props, dict):
        reference = props.get('scriptReference')
        if isinstance(reference, dict) and isinstance(reference.get('actionData'), dict) \
                and 'targetSystem' in reference['actionData']:
            reference['actionData']['targetSystem'] = migrate_target_system(reference['actionData']['targetSystem'], mixed)
        if 'targetSystem' in props:
            props['targetSystem'] = migrate_target_system(props['targetSystem'], mixed)
        devices = sync_device_slots(action_rows, props.get('devices'))
        if devices is None:
            props.pop('devices', None)
        else:
            props['devices'] = devices
    return True


def required_slots(props, action_rows):
    """{slot: description} a run must bind for one script: listed or used, except device0/desktop0."""
    out = {}
    for entry in (props or {}).get('devices') or []:
        if isinstance(entry, dict) and is_required_slot(entry.get('slot')) and entry['slot'] not in out:
            out[entry['slot']] = entry.get('description') or ''
    for slot in used_slots(action_rows):
        if is_required_slot(slot) and slot not in out:
            out[slot] = ''
    return out


def _is_dynamic_name(name):
    return not isinstance(name, str) or '{' in name or '}' in name


def static_required_slots(script_obj, load_script):
    """The run-start check's slots: the top script and every child it names statically, mapped onto top-level slots.

    `load_script(name)` returns a child script object ({'actionRows', 'props'})
    or None when it cannot be found (that child is then checked when called).
    Returns (required, adb_slots): required is {top_slot: [descriptions...]}
    ordered by slot, and adb_slots the top-level slots an ADBConfigurationAction
    acts on (their device must be an adb device).
    """
    required = {}
    adb_slots = set()
    visiting = set()

    def walk(script, slot_map, label):
        key = (label, tuple(sorted(slot_map.items())))
        if key in visiting:
            return
        visiting.add(key)
        rows = script.get('actionRows') or []
        props = script.get('props') or {}
        for slot, description in required_slots(props, rows).items():
            top = slot_map.get(slot, slot)
            if top == HOST_SLOT:
                continue
            if is_required_slot(top):
                note = description if description else ''
                required.setdefault(top, [])
                if note and note not in required[top]:
                    required[top].append(note)
        for action in _actions(rows):
            data = action.get('actionData') or {}
            if action.get('actionName') == 'ADBConfigurationAction':
                slot = normalize_target(data.get('targetSystem'))
                if slot in LEGACY_TARGET_SYSTEMS:
                    slot = 'phone0'
                top = slot_map.get(slot, slot)
                if is_slot_name(top):
                    adb_slots.add(top)
            if action.get('actionName') != 'scriptReference':
                continue
            name = data.get('scriptName')
            if _is_dynamic_name(name):
                continue
            name = name.strip()
            if name.startswith('[') and name.endswith(']'):
                continue
            child = load_script(name)
            if child is None:
                continue
            device_map = data.get('deviceMap') if isinstance(data.get('deviceMap'), dict) else {}
            child_map = {}
            for child_slot in set(used_slots(child.get('actionRows'))) | set(
                    e.get('slot') for e in ((child.get('props') or {}).get('devices') or []) if isinstance(e, dict)):
                if not is_slot_name(child_slot):
                    continue
                parent = map_child_slot(child_slot, device_map)
                child_map[child_slot] = slot_map.get(parent, parent)
            walk(child, child_map, name)

    walk(script_obj, {}, '<top>')
    ordered = {slot: required[slot] for slot in sorted(required, key=slot_sort_key)}
    return ordered, adb_slots
