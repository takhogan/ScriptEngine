"""When each screenshot was taken, and by what: an action result's `capture`.

Result files from version 2 (action_result.py) say, for the image an action
logged as its pre_file, when the device returned it, whether an action took it
to work on or a log thread took it to draw on afterwards, and a hash of its
pixels. Without this the first action that used a screenshot was the only
clue to its time, and a click's log image, taken after the click, looked like
the screen the click was aimed at (UI_MAPPER.md §8, E1).

DeviceController records every screenshot here as it is taken. Logging an
image as a pre_file then looks the image up, first by identity (the same
array, as when a click reuses its detect's screenshot) and then by its pixels,
because a parallel detect's screenshot comes back from its worker process as a
copy. Two screenshots of an unchanged screen have the same pixels; a copy then
gets the later one's time, which is the one a parallel group was dispatched
with.

Hashing a 720 x 1280 screenshot takes a few milliseconds, so it runs on a
thread of its own rather than in the action that took it.

    {"path": "<data-root-relative>", "sha": "<sha1 of the pixels>",
     "width": 720, "height": 1280,
     "captured_at": "2026-11-01T17:00:04.512Z", "taken_by": "action",
     "taken_in": 6}

The type definition is Capture in screenplan-contracts
(packages/screenplan-contracts/schemas/script-action-result.schema.json).
"""
import collections
import datetime
import hashlib
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ScriptEngine.common.constants.script_engine_constants import relative_data_path

TAKEN_BY_ACTION = 'action'
TAKEN_BY_LOGGER = 'logger'

# Captures kept for lookup by pixels. A run looks back a few screenshots at
# most (a parallel group, a click drawn on its detect's screenshot).
RECENT_CAPTURES = 64

_hash_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='capture-hash')


def timestamp(when=None):
    """`when` (default now) as UTC ISO 8601 with milliseconds and a Z."""
    when = when or datetime.datetime.now(datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
        '{:03d}Z'.format(when.microsecond // 1000)


def pixel_sha(image):
    return hashlib.sha1(np.ascontiguousarray(image).data).hexdigest()


def _current_counter():
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    try:
        action_log = ScriptLogger.get_logger().get_action_log()
        return action_log.get_script_counter() if action_log is not None else None
    except Exception:
        return None


class CaptureLog:
    def __init__(self, recent=RECENT_CAPTURES):
        self._lock = threading.Lock()
        self._by_id = {}
        self._recent = collections.deque(maxlen=recent)

    def record(self, image, taken_by=TAKEN_BY_ACTION):
        """Note that the device just returned `image`. Returns `image`."""
        if not isinstance(image, np.ndarray):
            return image
        entry = {
            'captured_at': timestamp(),
            'taken_by': taken_by,
            'taken_in': _current_counter(),
            # Hashed from a copy-free view now, before anything draws on it.
            'sha': _hash_executor.submit(pixel_sha, image),
        }
        with self._lock:
            for key in [key for key, (ref, _) in self._by_id.items() if ref() is None]:
                del self._by_id[key]
            self._by_id[id(image)] = (weakref.ref(image), entry)
            self._recent.append(entry)
        return image

    def describe(self, image, path):
        """The capture record of `image`, logged at `path`, for a result file."""
        with self._lock:
            found = self._by_id.get(id(image))
            entry = found[1] if found is not None and found[0]() is image else None
            recent = list(self._recent)
        sha = entry['sha'].result() if entry is not None else pixel_sha(image)
        if entry is None:
            entry = next((e for e in reversed(recent) if e['sha'].result() == sha), None)
        height, width = image.shape[:2]
        return {
            'path': relative_data_path(path),
            'sha': sha,
            'width': int(width),
            'height': int(height),
            'captured_at': entry['captured_at'] if entry else None,
            'taken_by': entry['taken_by'] if entry else None,
            'taken_in': entry['taken_in'] if entry else None,
        }


CAPTURE_LOG = CaptureLog()


def note_input_sent(action_log):
    """Record in `action_log`'s result that its input is going to the device
    now (`input_at`, result version 2). Called just before the device call,
    so the time is when the input left, not when the device returned."""
    if action_log is not None:
        action_log.update_result({'input_at': timestamp()})
