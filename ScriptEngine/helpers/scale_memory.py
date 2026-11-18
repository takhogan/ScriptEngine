"""Which template scales work on a device: learned per (device, source size,
capture size) pair, kept in {data root}/deviceScales/{device}.json.

docs/multiscale-template-matching.md is the design. In short: a pair starts
out *searching*; each confident match is an observation of the scale it was
found at; once a few scales hold most of the observations they are the
pair's *learned* set, and detects try only those. A learned pair that keeps
finding its matches elsewhere (explorations, RELEARN_AFTER in a row) goes
back to searching.

The state of a pair is a plain dict changed only by the pure functions
below (observe, learned_hit, outside_found), so a process can replay its
pending changes onto the file another process has just written.
"""
import atexit
import datetime
import json
import os
import re
import threading
import time

from ScriptEngine.common.constants.script_engine_constants import data_path

DEVICE_SCALES_FOLDER_NAME = 'deviceScales'
FILE_VERSION = 1

LEARN_MIN_SCORE = 0.9      # a match teaches only at or above this (and the detect's threshold)
MERGE_TOLERANCE = 0.02     # observations this close in x and in y are one scale
MAX_LEARNED = 3            # at most this many scales in a learned set
COVERAGE = 0.8             # the learned set holds at least this share of the observations
PROMOTE_AFTER = 3          # observations before a set can be learned
MIN_SCALE_OBSERVATIONS = 2 # each learned scale was seen at least this often
AGE_ABOVE = 60.0           # past this many observations, all are halved
EXPLORE_EVERY = 8          # a learned pair searches on the 8th, 16th and 32nd miss in a row,
EXPLORE_EVERY_MAX = 64     # then on every 64th
SEARCH_FIRST = 4           # a searching pair searches on its first 4 misses in a row, then as it explores
RELEARN_AFTER = 2          # explorations in a row that find a scale outside the set
HIT_FLUSH_SECONDS = 30.0   # hits on a learned scale are written at most this often
LOCK_WAIT_SECONDS = 0.5
LOCK_STALE_SECONDS = 10.0


def pair_key(source_size, capture_size):
    """'1920x1080->1280x720' for (width, height) sizes."""
    return '{}x{}->{}x{}'.format(int(source_size[0]), int(source_size[1]), int(capture_size[0]), int(capture_size[1]))


def new_pair():
    # outside_of: the learned set when the current run of outside finds began.
    return {'observations': [], 'learned': [], 'outside': 0, 'outside_of': [], 'updated': None}


def same_scale(a, b, tolerance=MERGE_TOLERANCE):
    return abs(a[0] / b[0] - 1) <= tolerance and abs(a[1] / b[1] - 1) <= tolerance


def in_set(scale, scales):
    return any(same_scale(scale, s) for s in scales)


def recompute(pair):
    """The learned set from the observations: the fewest, most observed
    scales (at most MAX_LEARNED, each seen MIN_SCALE_OBSERVATIONS times) that
    hold COVERAGE of them, once there are PROMOTE_AFTER; else none."""
    observations = sorted(pair['observations'], key=lambda o: -o['n'])
    total = sum(o['n'] for o in observations)
    learned = []
    if total >= PROMOTE_AFTER:
        held = 0.0
        for o in observations[:MAX_LEARNED]:
            if o['n'] < MIN_SCALE_OBSERVATIONS:
                break
            learned.append([o['sx'], o['sy']])
            held += o['n']
            if held >= COVERAGE * total:
                break
        if held < COVERAGE * total:
            learned = []
    pair['learned'] = learned
    return pair


def observe(pair, sx, sy, weight=1.0):
    """One confident match at (sx, sy)."""
    for o in pair['observations']:
        if same_scale((sx, sy), (o['sx'], o['sy'])):
            n = o['n'] + weight
            o['sx'] = round((o['sx'] * o['n'] + sx * weight) / n, 4)
            o['sy'] = round((o['sy'] * o['n'] + sy * weight) / n, 4)
            o['n'] = n
            break
    else:
        pair['observations'].append({'sx': round(float(sx), 4), 'sy': round(float(sy), 4), 'n': float(weight)})
    if sum(o['n'] for o in pair['observations']) > AGE_ABOVE:
        for o in pair['observations']:
            o['n'] = o['n'] / 2
        pair['observations'] = [o for o in pair['observations'] if o['n'] >= 0.5]
    pair['updated'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return recompute(pair)


def learned_hit(pair, sx, sy):
    """A match at a learned scale: observed, and the outside count reset."""
    pair['outside'] = 0
    pair['outside_of'] = []
    return observe(pair, sx, sy)


def outside_found(pair, sx, sy):
    """An exploration found a confident match at a scale outside the learned
    set. The scale is observed (it can join the set). RELEARN_AFTER of these
    with no learned hit between them send the pair back to searching, keeping
    only what was observed outside the set the first of them found."""
    if not pair.get('outside'):
        pair['outside_of'] = [list(s) for s in pair['learned']]
    observe(pair, sx, sy)
    pair['outside'] = pair.get('outside', 0) + 1
    if pair['outside'] >= RELEARN_AFTER:
        old = [tuple(s) for s in pair['outside_of']]
        pair['observations'] = [o for o in pair['observations'] if not in_set((o['sx'], o['sy']), old)]
        pair['outside'] = 0
        pair['outside_of'] = []
        recompute(pair)
    return pair


def should_explore(streak):
    if streak < EXPLORE_EVERY_MAX:
        return streak >= EXPLORE_EVERY and streak & (streak - 1) == 0
    return streak % EXPLORE_EVERY_MAX == 0


OPERATIONS = {'observe': observe, 'learned_hit': learned_hit, 'outside_found': outside_found}


def device_file_name(device_id):
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(device_id)) + '.json'


class ScaleMemory:
    """The learned scales of one device, in this process.

    The file is the shared copy: it is re-read when it changed, and this
    process's changes are kept as pending operations until they are written
    (replayed onto the file as read under the lock). With no path (a still
    image, a scorer) it learns in memory only.
    """
    _by_device = {}
    _lock = threading.Lock()

    @classmethod
    def for_device(cls, device_id):
        persistent = device_id is not None and str(device_id) != 'file' and not str(device_id).startswith('file:')
        key = device_id if persistent else None
        with cls._lock:
            memory = cls._by_device.get(key)
            if memory is None:
                path = data_path(DEVICE_SCALES_FOLDER_NAME, device_file_name(device_id)) if persistent else None
                memory = cls(path)
                cls._by_device[key] = memory
            return memory

    @classmethod
    def reset(cls):
        """Forget every device's in-process copy (tests, benchmarks)."""
        with cls._lock:
            for memory in cls._by_device.values():
                memory.flush()
            cls._by_device = {}

    def __init__(self, path=None):
        self.path = path
        self.pairs = {}
        self.pending = []
        self.file_mtime = None
        self.last_write = time.monotonic()
        self.miss_streak = {}
        self._mutex = threading.RLock()
        self._read_file()
        if path is not None:
            atexit.register(self.flush)

    # -- reading ---------------------------------------------------------

    def _load(self):
        if self.path is None or not os.path.exists(self.path):
            return {}, None
        try:
            mtime = os.path.getmtime(self.path)
            with open(self.path, 'r', encoding='utf-8') as f:
                document = json.load(f)
            if document.get('version') != FILE_VERSION:
                return {}, mtime
            return {key: recompute(dict(new_pair(), **pair)) for key, pair in document.get('pairs', {}).items()}, mtime
        except (OSError, ValueError, AttributeError, TypeError, KeyError):
            return {}, None

    def _replay(self, pairs):
        for operation, key, sx, sy in self.pending:
            OPERATIONS[operation](pairs.setdefault(key, new_pair()), sx, sy)
        return pairs

    def _read_file(self):
        pairs, mtime = self._load()
        self.pairs = self._replay(pairs)
        self.file_mtime = mtime

    def _refresh(self):
        if self.path is None:
            return
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime != self.file_mtime:
            self._read_file()

    def pair(self, key):
        """A copy of the pair's state, after any newer write by another process."""
        with self._mutex:
            self._refresh()
            pair = self.pairs.get(key) or new_pair()
            return json.loads(json.dumps(pair))

    def learned(self, key):
        return [tuple(s) for s in self.pair(key)['learned']]

    def observed(self, key):
        """A searching pair's observed scales, most observed first."""
        return [(o['sx'], o['sy']) for o in sorted(self.pair(key)['observations'], key=lambda o: -o['n'])]

    # -- changing --------------------------------------------------------

    def record(self, operation, key, sx, sy, urgent=True):
        with self._mutex:
            self._refresh()
            self.pending.append((operation, key, float(sx), float(sy)))
            OPERATIONS[operation](self.pairs.setdefault(key, new_pair()), float(sx), float(sy))
            if urgent or time.monotonic() - self.last_write >= HIT_FLUSH_SECONDS:
                self.flush()

    def note_miss(self, key):
        """A learned pair missed: True when this miss should explore. Most
        misses are screens that are not there, so explorations back off:
        the 8th, 16th and 32nd miss in a row, then every 64th."""
        with self._mutex:
            streak = self.miss_streak.get(key, 0) + 1
            self.miss_streak[key] = streak
            return should_explore(streak)

    def note_search_miss(self, key):
        """A searching pair missed at every scale it tried without searching:
        True when this miss should search. The first 4 misses in a row
        search, then the 8th, 16th and 32nd, then every 64th: a pair whose
        detects mostly look for screens that are not there must not pay a
        search on every miss before it has learned anything."""
        with self._mutex:
            streak = self.miss_streak.get(key, 0) + 1
            self.miss_streak[key] = streak
            return streak <= SEARCH_FIRST or should_explore(streak)

    def note_hit(self, key):
        with self._mutex:
            self.miss_streak[key] = 0

    # -- writing ---------------------------------------------------------

    def _acquire(self, lock_path):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return True
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(lock_path) > LOCK_STALE_SECONDS:
                        os.remove(lock_path)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)
            except OSError:
                return False

    def flush(self):
        """Write the pending changes; kept pending when the file is locked or unwritable."""
        with self._mutex:
            if self.path is None:
                self.pending = []
                return
            if not self.pending:
                return
            lock_path = self.path + '.lock'
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
            except OSError:
                return
            if not self._acquire(lock_path):
                return
            try:
                pairs, _ = self._load()
                pairs = self._replay(pairs)
                temporary = '{}.{}.tmp'.format(self.path, os.getpid())
                with open(temporary, 'w', encoding='utf-8') as f:
                    json.dump({'version': FILE_VERSION, 'pairs': pairs}, f, indent=1, sort_keys=True)
                os.replace(temporary, self.path)
                self.pairs = pairs
                self.pending = []
                self.file_mtime = os.path.getmtime(self.path)
                self.last_write = time.monotonic()
            except OSError:
                pass
            finally:
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
