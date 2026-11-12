"""CustomProcessPool sends large numpy arguments through shared memory
(ScriptEngine/shared_memory_args.py): each array is copied once into a block of
its own, tasks carry a reference to it, and workers map it read-only. These
tests run a real spawn pool, the start method the engine uses."""
import gc
import json
import multiprocessing
import os
import subprocess
import sys
import textwrap
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.custom_process_pool import CustomProcessPool
from ScriptEngine import shared_memory_args
from ScriptEngine.shared_memory_args import MIN_SHARED_BYTES, SharedArgSender, SharedArrayRef, _same_bytes

SPAWN = multiprocessing.get_context('spawn')


# -- run in the workers ---------------------------------------------------------

def describe(*args, **kwargs):
    """What the worker received, as plain values."""
    def one(v):
        if isinstance(v, np.ndarray):
            return {
                'shape': v.shape, 'dtype': str(v.dtype), 'writeable': bool(v.flags.writeable),
                'bytes': v.tobytes(),
            }
        if isinstance(v, dict):
            return {k: one(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return type(v)(one(x) for x in v)
        return v
    return one(list(args)), one(kwargs)


def echo(*args, **kwargs):
    return args, kwargs


def same_object(a, b):
    return a is b


def checksum_after(seconds, arr):
    time.sleep(seconds)
    return int(arr.astype(np.int64).sum())


def try_write(arr):
    try:
        arr[0] = 1
    except ValueError:
        return 'read-only'
    return 'written'


def sleep(seconds):
    time.sleep(seconds)


# -- helpers ----------------------------------------------------------------------

def _image(seed=0, shape=(720, 1280, 3)):
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def _segment_exists(name):
    try:
        if sys.version_info >= (3, 13):
            shm = shared_memory.SharedMemory(name=name, track=False)
        else:
            shm = shared_memory.SharedMemory(name=name)
    except FileNotFoundError:
        return False
    shm.close()
    return True


def _eventually(condition, timeout=10.0):
    # A future's done callbacks, which release its blocks, run just after
    # result() returns, on the pool's management thread.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@pytest.fixture(autouse=True)
def quiet_logger():
    # The pool logs each worker spawn; the logger is a singleton with no log
    # file outside a run.
    logger = ScriptLogger()
    logger.set_log_file_path(os.devnull)
    logger.set_log_to_stdout(False)


@pytest.fixture
def pool():
    p = CustomProcessPool(max_workers=2, mp_context=SPAWN)
    yield p
    p.shutdown()


# -- tests ------------------------------------------------------------------------

def test_spawn_pools_send_shared_memory(pool):
    assert pool._shared_args is not None


def test_round_trip_equals_the_arrays_sent(pool):
    screenshot = _image(1)
    blurred_view = np.pad(_image(2), ((15, 15), (15, 15), (0, 0)))[15:-15, 15:-15]  # not contiguous
    assert not blurred_view.flags.c_contiguous
    fortran = np.asfortranarray(_image(3, (600, 800)))
    floats = np.random.default_rng(4).standard_normal((300, 400)).astype(np.float32)
    floats[0, 0] = np.nan
    action = {'input_obj': {'screencap_im_bgr': screenshot, 'original_image_blurred': blurred_view},
              'actionData': {'positiveExamples': [{'img': fortran, 'mask': floats}]}}

    (received,), kwargs = pool.submit(describe, action, extra=screenshot).result()

    sent = [screenshot, blurred_view, fortran, floats]
    got = [received['input_obj']['screencap_im_bgr'], received['input_obj']['original_image_blurred'],
           received['actionData']['positiveExamples'][0]['img'], received['actionData']['positiveExamples'][0]['mask']]
    for arr, info in zip(sent, got):
        assert info['shape'] == arr.shape and info['dtype'] == str(arr.dtype)
        assert info['bytes'] == arr.tobytes()
        assert info['writeable'] is False
    assert kwargs['extra']['bytes'] == screenshot.tobytes()


def test_results_still_come_back_pickled_and_writable(pool):
    screenshot = _image(5)
    (back,), _ = pool.submit(echo, screenshot).result()
    assert back is not screenshot
    assert np.array_equal(back, screenshot)
    assert back.flags.writeable


def test_the_caller_args_are_not_modified(pool):
    screenshot = _image(6)
    action = {'input_obj': {'screencap_im_bgr': screenshot}, 'name': 'detect'}
    pool.submit(describe, action).result()
    assert action['input_obj']['screencap_im_bgr'] is screenshot


def test_workers_get_read_only_views(pool):
    assert pool.submit(try_write, _image(7)).result() == 'read-only'


def test_one_block_per_array_reused_across_tasks(pool):
    screenshot = _image(8)
    template = _image(9, (720, 1280))
    futures = [pool.submit(describe, {'img': screenshot, 'mask': template}, i) for i in range(6)]
    for f in futures:
        (received, _), _ = f.result()
        assert received['img']['bytes'] == screenshot.tobytes()
    assert len(pool._shared_args.block_names()) == 2


def test_the_same_array_twice_in_one_task_is_one_view(pool):
    screenshot = _image(10)
    assert pool.submit(same_object, screenshot, screenshot).result() is True


def test_a_block_outlives_its_array_until_the_task_is_done():
    p = CustomProcessPool(max_workers=1, mp_context=SPAWN)
    try:
        blocker = p.submit(sleep, 0.5)  # the task below waits in the queue behind this
        screenshot = _image(11)
        expected = int(screenshot.astype(np.int64).sum())
        future = p.submit(checksum_after, 0, screenshot)
        (name,) = p._shared_args.block_names()
        del screenshot
        gc.collect()
        # The next submit is where the sender handles collected arrays.
        other = p.submit(checksum_after, 0, _image(99))
        assert name in p._shared_args.block_names()
        blocker.result()
        assert future.result() == expected
        other.result()
        # Done, and its array is gone: unlinked.
        assert _eventually(lambda: p._shared_args.block_names() == [])
        if sys.platform != 'win32':  # on Windows the worker's open handle keeps it
            assert not _segment_exists(name)
    finally:
        p.shutdown()


def test_an_array_changed_in_place_gets_a_new_block(pool):
    screenshot = _image(12)
    first = pool.submit(checksum_after, 0, screenshot).result()
    (old_name,) = pool._shared_args.block_names()
    screenshot[0, 0, 0] ^= 0xFF
    second = pool.submit(checksum_after, 0, screenshot).result()
    assert second == int(screenshot.astype(np.int64).sum()) != first
    assert _eventually(lambda: len(pool._shared_args.block_names()) == 1)
    assert pool._shared_args.block_names() != [old_name]


def test_no_segments_left_after_shutdown():
    p = CustomProcessPool(max_workers=2, mp_context=SPAWN)
    kept = [_image(13), _image(14, (720, 1280))]  # still alive at shutdown
    for f in [p.submit(describe, kept, _image(15)) for _ in range(3)]:
        f.result()
    names = p._shared_args.block_names()
    assert names
    p.shutdown()
    assert p._shared_args.block_names() == []
    for name in names:
        assert not _segment_exists(name)


def test_shutdown_without_wait_unlinks_in_use_blocks_when_their_task_ends():
    p = CustomProcessPool(max_workers=1, mp_context=SPAWN)
    screenshot = _image(16)
    future = p.submit(checksum_after, 0.5, screenshot)
    (name,) = p._shared_args.block_names()
    p.shutdown(wait=False)
    assert p._shared_args.block_names() == [name]
    assert future.result() == int(screenshot.astype(np.int64).sum())
    assert _eventually(lambda: p._shared_args.block_names() == [])
    p.shutdown()  # joins the workers
    assert not _segment_exists(name)


def test_small_arrays_and_other_args_go_as_before(pool):
    small = np.arange(MIN_SHARED_BYTES // 8 - 1, dtype=np.float64)
    objects = np.empty(MIN_SHARED_BYTES, dtype=object)
    args = ({'n': 3, 's': 'text', 'small': small, 'nested': [1, (2, None), {'x': 1.5}]}, objects)
    sender = SharedArgSender()
    packed_args, packed_kwargs, blocks = sender.pack(args, {'k': 'v'})
    assert packed_args is args and packed_kwargs == {'k': 'v'} and blocks == ()
    assert sender.block_names() == []
    sender.close()

    (received, received_objects), kwargs = pool.submit(echo, *args, k='v').result()
    assert received['n'] == 3 and received['s'] == 'text'
    assert received['nested'] == [1, (2, None), {'x': 1.5}]
    assert np.array_equal(received['small'], small) and received['small'].flags.writeable
    assert received_objects.shape == objects.shape
    assert kwargs == {'k': 'v'}
    assert pool._shared_args.block_names() == []


def test_pack_replaces_only_large_plain_arrays():
    big = _image(17)
    masked = np.ma.masked_array(big)
    sender = SharedArgSender()
    args = ({'a': big, 'b': [big, 1], 'masked': masked},)
    packed, _, blocks = sender.pack(args, {})
    d = packed[0]
    assert isinstance(d['a'], SharedArrayRef) and d['b'][0] is d['a'] and d['b'][1] == 1
    assert d['masked'] is masked
    assert len(blocks) == 1
    sender.release(blocks)
    sender.close()
    assert sender.block_names() == []


def test_idle_blocks_of_live_arrays_are_capped():
    arrays = [_image(i) for i in range(3)]
    sender = SharedArgSender(max_idle_bytes=arrays[0].nbytes * 2)
    for arr in arrays:
        _, _, blocks = sender.pack((arr,), {})
        sender.release(blocks)
    # The least recently used one went over the cap and was unlinked.
    assert len(sender.block_names()) == 2
    _, _, blocks = sender.pack((arrays[2],), {})
    assert len(sender.block_names()) == 2  # reused
    sender.release(blocks)
    sender.close()
    assert sender.block_names() == []


def test_same_bytes_compares_bytes_not_values():
    floats = np.full((300, 300), np.nan, dtype=np.float64)
    block = floats.copy()
    assert _same_bytes(block, floats)
    view = np.pad(floats, 1)[1:-1, 1:-1]
    assert not view.flags.c_contiguous and _same_bytes(block, view)
    changed = floats.copy()
    changed[-1, -1] = 0.0
    assert not _same_bytes(block, changed)


def test_a_float_array_with_nan_is_not_copied_again():
    floats = np.full((300, 300), np.nan, dtype=np.float64)
    sender = SharedArgSender()
    _, _, first = sender.pack((floats,), {})
    sender.release(first)
    _, _, second = sender.pack((floats,), {})
    assert second == first
    sender.release(second)
    sender.close()


@pytest.mark.parametrize('ending', ['shutdown', 'exit'])
def test_worker_exits_and_engine_exit_leave_no_segments_or_warnings(tmp_path, ending):
    """Each task runs in a fresh worker (max_tasks_per_child=1), so workers that
    attached the block exit while the block is still in use. Before Python 3.13
    attaching registers the block with the resource tracker; a tracker of the
    worker's own would unlink it, or warn about a leak, when the worker exits.
    'exit' ends the process without shutting the pool down: the exit hook
    unlinks the blocks."""
    script = tmp_path / 'run_pool.py'
    script.write_text(textwrap.dedent('''
        import json, multiprocessing, sys
        import numpy as np
        sys.path.insert(0, {repo!r})
        from ScriptEngine.custom_process_pool import CustomProcessPool

        def checksum(arr):
            return int(arr.astype(np.int64).sum())

        if __name__ == '__main__':
            ctx = multiprocessing.get_context('spawn')
            arr = np.random.default_rng(0).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
            pool = CustomProcessPool(max_workers=2, mp_context=ctx, max_tasks_per_child=1)
            results = [f.result() for f in [pool.submit(checksum, arr) for _ in range(4)]]
            print(json.dumps({{'names': pool._shared_args.block_names(), 'ok': results == [checksum(arr)] * 4}}))
            sys.stdout.flush()
            if sys.argv[1] == 'shutdown':
                pool.shutdown()
    ''').format(repo=str(REPO)))
    proc = subprocess.run(
        [sys.executable, str(script), ending], capture_output=True, text=True, timeout=120, cwd=str(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out['ok'] and len(out['names']) == 1
    # The resource tracker exits shortly after the process; its warnings land
    # on the same stderr, which run() has collected by now.
    assert 'leaked' not in proc.stderr and 'resource_tracker' not in proc.stderr, proc.stderr
    assert 'Traceback' not in proc.stderr, proc.stderr
    for name in out['names']:
        assert not _segment_exists(name)


@pytest.mark.skipif(sys.version_info >= (3, 13), reason='3.13 attaches with track=False under any start method')
@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(), reason='no fork on this platform')
def test_fork_pools_pickle_as_before():
    p = CustomProcessPool(max_workers=1, mp_context=multiprocessing.get_context('fork'))
    try:
        assert p._shared_args is None
    finally:
        p.shutdown()


@pytest.mark.skipif(not os.path.isdir('/dev/fd'), reason='needs /dev/fd to count open files')
def test_blocks_hold_no_file_descriptors():
    arrays = [_image(i, (512, 512)) for i in range(40)]
    sender = SharedArgSender()
    before = len(os.listdir('/dev/fd'))
    _, _, blocks = sender.pack((arrays,), {})
    assert len(blocks) == 40
    assert len(os.listdir('/dev/fd')) - before < 5
    sender.release(blocks)
    sender.close()
    assert sender.block_names() == []


def test_a_worker_does_not_reuse_a_cached_block_whose_name_came_back():
    """On POSIX, once the main process unlinks a block, a later block can get the
    same random name while a worker still has the old one open in its cache.
    The worker must map the new block, not reuse the old mapping. Runs the
    worker side in this process, with the name reused on purpose."""
    shape = (512, 1024)
    first = shared_memory.SharedMemory(create=True, size=shape[0] * shape[1])
    name = first.name
    second = None
    try:
        np.ndarray(shape, np.uint8, buffer=first.buf)[...] = 1
        seen = shared_memory_args.call_with_shared_args(
            lambda a: a.copy(), (SharedArrayRef(name, 1, shape, np.dtype(np.uint8)),), {})
        assert (seen == 1).all()
        # The worker keeps it open; the main process unlinks it and a new block
        # gets the same name.
        first.close()
        first.unlink()
        first = None
        second = shared_memory.SharedMemory(name=name, create=True, size=shape[0] * shape[1])
        np.ndarray(shape, np.uint8, buffer=second.buf)[...] = 2
        seen = shared_memory_args.call_with_shared_args(
            lambda a: a.copy(), (SharedArrayRef(name, 2, shape, np.dtype(np.uint8)),), {})
        assert (seen == 2).all()
    finally:
        for cached in list(shared_memory_args._worker_blocks):
            shared_memory_args._evict(cached)
        for shm in (first, second):
            if shm is not None:
                shm.close()
                shm.unlink()


def test_every_block_gets_its_own_serial():
    arrays = [_image(i, (512, 512)) for i in range(3)]
    sender = SharedArgSender()
    packed, _, blocks = sender.pack((arrays,), {})
    assert len({ref.serial for ref in packed[0]}) == 3
    sender.release(blocks)
    sender.close()
