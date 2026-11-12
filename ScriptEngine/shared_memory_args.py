"""Large numpy arrays in process-pool task arguments, sent through shared memory.

ProcessPoolExecutor pickles every argument of every task into one pipe. A
parallel detect sends the screenshot, its blurred copy and the template's
screen-sized canvases and masks, ~17 MB per task, and sends the same arrays
again for every detect of a batch. CustomProcessPool instead copies each large
array once into a shared-memory block of its own and sends a SharedArrayRef, a
few dozen bytes. The worker maps the block by name as a read-only array, with
no copy. Results still come back pickled.

Main process (SharedArgSender, one per pool):
- One block per array object. The next task that sends the same object reuses
  the block if the array still holds the same bytes. They are compared on every
  reuse, at memcmp speed, so an array changed in place gets a new block instead
  of a worker reading stale pixels.
- A block lives until every future that uses it is done, even when its array is
  dropped right after submit. Once no task uses it, it is unlinked if its array
  is gone, else kept for reuse, up to max_idle_bytes in all.
- On POSIX a block is unmapped once filled, so idle blocks hold no file
  descriptors; it is mapped again only for the comparison.
- Pool shutdown and interpreter exit unlink every block. A main process that is
  killed leaves its blocks to the resource tracker (POSIX) or to the OS
  (Windows, where a block goes away with its last handle).

Worker (call_with_shared_args): maps the blocks a task names and keeps a few
open for the next task. Attaching does not add a resource-tracker registration
of its own (see sends_shared_memory and _attach).
"""
import atexit
import collections
import itertools
import os
import sys
import threading
import weakref
from multiprocessing import shared_memory

import numpy as np

# Below this an array is pickled as before: a block costs a few system calls,
# more than pickling a small array.
MIN_SHARED_BYTES = 256 * 1024
# Blocks no task is using whose array is still alive (the run's templates,
# mostly), kept so the next detect that sends them reuses them. Past this the
# least recently used are unlinked; sending one of those arrays again copies it
# into a new block.
DEFAULT_MAX_IDLE_BYTES = 512 * 1024 * 1024
# Per worker. Opening a block costs ~0.05 ms, so the cache only saves a few
# system calls. It is small because a block the main process has unlinked
# keeps its memory while any worker still has it open, and because each open
# block holds two file descriptors on POSIX (SharedMemory's and mmap's copy).
WORKER_CACHE_MAX_BLOCKS = 16
WORKER_CACHE_MAX_BYTES = 64 * 1024 * 1024
# The main process maps a block only to fill it and to compare it on reuse. On
# POSIX a block lives on unmapped until it is unlinked, so the hundreds a run
# keeps (each template sends four screen-sized canvases and two masks) hold no
# file descriptors; macOS's default limit is 256 open files. On Windows a block
# goes away with its last handle, so the main process keeps it open there.
_MAIN_KEEPS_BLOCKS_MAPPED = os.name == 'nt'


def sends_shared_memory(mp_context):
    """Whether a pool with this context may send arrays through shared memory.

    Before Python 3.13 attaching to a block registers it with the resource
    tracker, and a tracker unlinks what is registered with it when it exits.
    Under spawn every worker shares its parent's tracker, which already holds
    the name from the create, so the attach adds nothing. A forked worker can
    start a tracker of its own, which would unlink the block when the worker
    exits. 3.13 attaches with track=False, safe under every start method.
    """
    return sys.version_info >= (3, 13) or mp_context.get_start_method() == 'spawn'


# Numbers every block this process creates. A name only stays unique while its
# block exists: once the main process unlinks a block, a later block can get the
# same random name (8 hex characters) on POSIX, while a worker still has the
# old one mapped in its cache. The worker reuses a cached block only when the
# serial matches too.
_block_serials = itertools.count(1)


class SharedArrayRef:
    """What a task carries in place of an array: the block's name, serial, shape and dtype."""
    __slots__ = ('name', 'serial', 'shape', 'dtype')

    def __init__(self, name, serial, shape, dtype):
        self.name = name
        self.serial = serial
        self.shape = shape
        self.dtype = dtype

    def __reduce__(self):
        return (SharedArrayRef, (self.name, self.serial, self.shape, self.dtype))

    def __repr__(self):
        return 'SharedArrayRef({!r}, {}, {}, {})'.format(self.name, self.serial, self.shape, self.dtype)


def _is_shared(obj):
    # Exactly ndarray: a subclass (masked array, matrix) carries more than its
    # buffer and is pickled as before. Object arrays hold pointers, not data.
    return (
        type(obj) is np.ndarray
        and obj.nbytes >= MIN_SHARED_BYTES
        and not obj.dtype.hasobject
    )


def _attach(name):
    if sys.version_info >= (3, 13):
        return shared_memory.SharedMemory(name=name, track=False)
    # Registers the name with the resource tracker, which already holds it
    # from the create: under spawn, workers share the main process's tracker
    # (see sends_shared_memory).
    return shared_memory.SharedMemory(name=name)


_UINT_OF_SIZE = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}


def _same_bytes(block_view, arr):
    """Whether arr still holds the bytes once copied into block_view (C order,
    same shape and dtype). Compared as unsigned integers, so a float NaN equals
    itself and an array holding one is not copied again on every reuse."""
    if arr.flags.c_contiguous:
        a = arr.reshape(-1).view(np.uint8)
        b = block_view.reshape(-1).view(np.uint8)
        if a.size % 8 == 0:
            a, b = a.view(np.uint64), b.view(np.uint64)
        return bool(np.array_equal(a, b))
    uint = _UINT_OF_SIZE.get(arr.dtype.itemsize)
    if uint is None:
        return False
    return bool(np.array_equal(block_view.view(uint), arr.view(uint)))


class _Block:
    __slots__ = ('shm', 'name', 'serial', 'nbytes', 'shape', 'dtype', 'array_ref', 'key', 'users', '__weakref__')

    def __init__(self, shm, arr):
        # Closed (unmapped) on POSIX once filled; kept for unlink().
        self.shm = shm
        self.name = shm.name
        self.serial = next(_block_serials)
        self.nbytes = arr.nbytes
        self.shape = arr.shape
        self.dtype = arr.dtype
        self.array_ref = None
        # id() of the array this block holds, while that array is alive and the
        # block is its current one. None once the block is orphaned: it is then
        # unlinked as soon as no task uses it.
        self.key = None
        # Futures not yet done that carry this block.
        self.users = 0

    def fill(self, arr):
        np.ndarray(self.shape, dtype=self.dtype, buffer=self.shm.buf)[...] = arr
        if not _MAIN_KEEPS_BLOCKS_MAPPED:
            self.shm.close()

    def holds(self, arr):
        """Whether the block still holds arr's bytes: false once arr was changed in place."""
        if self.shape != arr.shape or self.dtype != arr.dtype:
            return False
        shm = self.shm if _MAIN_KEEPS_BLOCKS_MAPPED else _attach(self.name)
        try:
            view = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
            try:
                return _same_bytes(view, arr)
            finally:
                del view
        finally:
            if shm is not self.shm:
                shm.close()

    def ref(self):
        return SharedArrayRef(self.name, self.serial, self.shape, self.dtype)


class SharedArgSender:
    """The main process's side: puts arrays in blocks, tracks who uses them, unlinks them."""

    def __init__(self, max_idle_bytes=DEFAULT_MAX_IDLE_BYTES):
        self.max_idle_bytes = max_idle_bytes
        self._lock = threading.Lock()
        self._by_array = {}                      # id(array) -> its current block
        self._blocks = set()                     # every block not yet unlinked
        self._idle = collections.OrderedDict()   # unused blocks of live arrays, oldest first
        self._idle_bytes = 0
        # Blocks whose array was garbage-collected. Weakref callbacks run on
        # whichever thread drops the last reference, possibly inside this
        # class with the lock held, so they only append here; the next
        # pack, release or close handles them.
        self._dead = collections.deque()
        self._closed = False
        with _senders_lock:
            _senders.add(self)

    # -- main process API ---------------------------------------------------

    def pack(self, args, kwargs):
        """args and kwargs with every large array replaced by a SharedArrayRef.

        Returns (args, kwargs, blocks). Containers that hold no such array are
        returned as they are. Pass blocks to release() once the task's future
        is done; until then they stay linked.
        """
        used = {}
        with self._lock:
            if self._closed:
                return args, kwargs, ()
            self._collect_dead()
            memo = {}
            try:
                args = self._pack(args, memo, used)
                kwargs = self._pack(kwargs, memo, used)
            except BaseException:
                self._release_locked(used)
                raise
        return args, kwargs, tuple(used)

    def release(self, blocks):
        with self._lock:
            self._release_locked(blocks)

    def close(self):
        """Unlink every block no task is using; the rest go when their task is done."""
        with self._lock:
            self._closed = True
            self._collect_dead()
            for block in list(self._blocks):
                if block.users == 0:
                    self._orphan(block)
            if not self._blocks:
                with _senders_lock:
                    _senders.discard(self)

    def unlink_all(self):
        """Unlink every block, in use or not: the interpreter is exiting."""
        with self._lock:
            self._closed = True
            for block in list(self._blocks):
                self._unlink(block)
            self._by_array.clear()
            self._idle.clear()
            self._idle_bytes = 0

    def block_names(self):
        with self._lock:
            return sorted(block.name for block in self._blocks)

    # -- internals, called with the lock held --------------------------------

    def _pack(self, obj, memo, used):
        key = id(obj)
        if key in memo:
            return memo[key]
        t = type(obj)
        if t is np.ndarray:
            out = self._share(obj, used) if _is_shared(obj) else obj
        elif t is dict:
            memo[key] = obj
            items = [(k, self._pack(v, memo, used)) for k, v in obj.items()]
            if any(packed is not v for (_, packed), v in zip(items, obj.values())):
                out = dict(items)
            else:
                out = obj
        elif t is list or t is tuple:
            memo[key] = obj
            packed = [self._pack(v, memo, used) for v in obj]
            if any(p is not v for p, v in zip(packed, obj)):
                out = packed if t is list else tuple(packed)
            else:
                out = obj
        else:
            out = obj
        memo[key] = out
        return out

    def _share(self, arr, used):
        block = self._by_array.get(id(arr))
        if block is not None and not (block.array_ref() is arr and block.holds(arr)):
            # Changed in place since it was copied, or a new array that got a
            # dead one's id. The old block stays for the tasks that carry it.
            self._orphan(block)
            block = None
        if block is None:
            block = self._create(arr)
        if block not in used:
            used[block] = None
            if block.users == 0:
                self._idle_remove(block)
            block.users += 1
        return block.ref()

    def _create(self, arr):
        shm = shared_memory.SharedMemory(create=True, size=max(1, arr.nbytes))
        block = _Block(shm, arr)
        try:
            block.fill(arr)
        except BaseException:
            shm.close()
            shm.unlink()
            raise
        dead = self._dead
        block_ref = weakref.ref(block)

        def _array_collected(_, dead=dead, block_ref=block_ref):
            block = block_ref()
            if block is not None:
                dead.append(block)

        block.array_ref = weakref.ref(arr, _array_collected)
        block.key = id(arr)
        self._by_array[block.key] = block
        self._blocks.add(block)
        return block

    def _collect_dead(self):
        while self._dead:
            block = self._dead.popleft()
            if block in self._blocks:
                self._orphan(block)

    def _orphan(self, block):
        if block.key is not None and self._by_array.get(block.key) is block:
            del self._by_array[block.key]
        block.key = None
        if block.users == 0:
            self._idle_remove(block)
            self._unlink(block)

    def _release_locked(self, blocks):
        self._collect_dead()
        for block in blocks:
            block.users -= 1
            if block.users == 0:
                if self._closed or block.key is None:
                    self._unlink(block)
                else:
                    self._idle[block] = None
                    self._idle_bytes += block.nbytes
        while self._idle_bytes > self.max_idle_bytes and self._idle:
            self._orphan(next(iter(self._idle)))

    def _idle_remove(self, block):
        if self._idle.pop(block, False) is None:
            self._idle_bytes -= block.nbytes

    def _unlink(self, block):
        if block not in self._blocks:
            return
        self._blocks.discard(block)
        try:
            block.shm.close()  # already closed on POSIX
        except (BufferError, OSError):
            pass
        try:
            # A no-op on Windows, where the block goes with its last handle.
            block.shm.unlink()
        except OSError:
            # FileNotFoundError: already gone.
            pass
        if self._closed and not self._blocks:
            with _senders_lock:
                _senders.discard(self)


# Senders that may still hold blocks, for the exit hook. A sender leaves once it
# is closed and its last block is unlinked.
_senders = set()
_senders_lock = threading.Lock()


@atexit.register
def _unlink_at_exit():
    with _senders_lock:
        senders = list(_senders)
    for sender in senders:
        sender.unlink_all()


# -- worker side --------------------------------------------------------------

_worker_blocks = collections.OrderedDict()   # name -> (serial, SharedMemory, view), least recent first
_worker_bytes = 0
# Evicted blocks that could not be closed yet because an array still pointed
# into them; tried again before each task.
_worker_unclosed = []


def _evict(name):
    global _worker_bytes
    _, shm, view = _worker_blocks.pop(name)
    _worker_bytes -= view.nbytes
    del view
    _try_close(shm)


def _open(ref, used):
    global _worker_bytes
    entry = _worker_blocks.get(ref.name)
    if entry is not None and entry[0] != ref.serial:
        # A block unlinked since, whose name a new block now has.
        _evict(ref.name)
        entry = None
    if entry is None:
        shm = _attach(ref.name)
        view = np.ndarray(ref.shape, dtype=ref.dtype, buffer=shm.buf)
        view.flags.writeable = False
        entry = _worker_blocks[ref.name] = (ref.serial, shm, view)
        _worker_bytes += view.nbytes
    else:
        _worker_blocks.move_to_end(ref.name)
    used.add(ref.name)
    return entry[2]


def _try_close(shm):
    try:
        shm.close()
    except BufferError:
        _worker_unclosed.append(shm)


def _trim_worker_cache(keep):
    for shm in _worker_unclosed[:]:
        _worker_unclosed.remove(shm)
        _try_close(shm)
    for name in list(_worker_blocks):
        if len(_worker_blocks) <= WORKER_CACHE_MAX_BLOCKS and _worker_bytes <= WORKER_CACHE_MAX_BYTES:
            break
        if name in keep:
            continue
        _evict(name)


def _unpack(obj, memo, used):
    key = id(obj)
    if key in memo:
        return memo[key]
    t = type(obj)
    if t is SharedArrayRef:
        out = _open(obj, used)
    elif t is dict:
        memo[key] = obj
        items = [(k, _unpack(v, memo, used)) for k, v in obj.items()]
        if any(unpacked is not v for (_, unpacked), v in zip(items, obj.values())):
            out = dict(items)
        else:
            out = obj
    elif t is list or t is tuple:
        memo[key] = obj
        unpacked = [_unpack(v, memo, used) for v in obj]
        if any(u is not v for u, v in zip(unpacked, obj)):
            out = unpacked if t is list else tuple(unpacked)
        else:
            out = obj
    else:
        out = obj
    memo[key] = out
    return out


def call_with_shared_args(fn, args, kwargs):
    """Runs in the worker: maps the task's blocks, then calls fn.

    The previous task's blocks are closed here, not when it returned: its
    result is pickled after fn returns, and may still point into them then.
    """
    used = set()
    memo = {}
    args = _unpack(args, memo, used)
    kwargs = _unpack(kwargs, memo, used)
    _trim_worker_cache(used)
    return fn(*args, **kwargs)
