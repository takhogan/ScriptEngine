"""Periodic sampling of the engine's internal work queues.

Every artifact an action produces is written by somebody else: action-log JSON by
the single-worker executor in script_action_log, stdout and the run log by
ScriptLogger's writer thread, overlay images by the shared io_executor. Because
nothing waits on any of them, a queue that stops draining is invisible from the
critical path — until the disk or the cores it is competing for become the thing
holding everything up.

Until now the only evidence of a backlog was reconstructed after the fact, from
the gap between an action-log's `elapsed` and its `async_elapsed`. That gap is
recorded at flush time, so it says how far behind the writer was *when it finally
got there*, and only for actions that completed. This samples the queues while
the run is happening instead.

Levels are chosen so the healthy case costs nothing at the log level runs
actually use: routine samples are 'debug', and 'info' carries only the transition
into and out of a backlog, which is the part worth waking up for.
"""

import threading
import time


# The pool's worker processes do the image encoding and most of the writing, but
# they are shut down before the run summary is assembled, so by then there is
# nothing left to ask. The monitor is already awake while they are alive, so it
# keeps the most recent reading for the summary to use.
_last_child_snapshot = []
_child_snapshot_lock = threading.Lock()


def last_child_snapshot():
    with _child_snapshot_lock:
        return list(_last_child_snapshot)


def _sample_children():
    try:
        import psutil
        rows = []
        for child in psutil.Process().children(recursive=True):
            try:
                cpu = child.cpu_times()
                row = {
                    'pid': child.pid,
                    'name': child.name(),
                    'cpu_user': cpu.user,
                    'cpu_system': cpu.system,
                    'rss_mb': child.memory_info().rss / (1024 ** 2),
                }
                try:
                    io_counters = child.io_counters()
                    row['write_mb'] = io_counters.write_bytes / (1024 ** 2)
                    row['write_ops'] = io_counters.write_count
                except Exception:
                    pass
                rows.append(row)
            except Exception:
                continue
        if rows:
            with _child_snapshot_lock:
                global _last_child_snapshot
                _last_child_snapshot = rows
    except Exception:
        pass


# A queue this deep means the producer has outrun the writer by more items than a
# burst would explain. Depths below this are normal: actions are logged faster
# than the disk accepts them and the queue absorbs the difference.
BACKLOG_ITEM_THRESHOLD = 200

# Repeat the 'info' line no more often than this while a backlog persists, so a
# long stall costs a handful of lines rather than one every sample.
BACKLOG_REPEAT_SECONDS = 60.0

SAMPLE_INTERVAL_SECONDS = 10.0


def _queue_depth(queue_obj):
    """Best-effort depth of a queue-like object, or None if it will not say.

    ThreadPoolExecutor's pending work lives in a private `_work_queue`; reading it
    is a diagnostic convenience, not a contract, so every failure here is silent.
    """
    if queue_obj is None:
        return None
    try:
        return queue_obj.qsize()
    except Exception:
        return None


def _executor_pending(executor):
    return _queue_depth(getattr(executor, '_work_queue', None))


def sample(io_executor=None, process_executor=None):
    """One snapshot of every queue the engine writes through."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    from ScriptEngine.common.logging import script_action_log

    stdout_pending = _queue_depth(getattr(ScriptLogger, '_write_queue', None))
    action_log_pending = _executor_pending(getattr(script_action_log, '_log_executor', None))

    io_pending = _executor_pending(io_executor)
    io_active = None
    if io_executor is not None:
        try:
            io_active = len(io_executor.get_active_tasks())
        except Exception:
            io_active = None

    process_pending = _executor_pending(process_executor)
    process_workers = None
    if process_executor is not None:
        try:
            process_workers = len(getattr(process_executor, '_processes', {}) or {})
        except Exception:
            process_workers = None

    return {
        'stdout_queue': stdout_pending,
        'action_log_pending': action_log_pending,
        'io_pending': io_pending,
        'io_active': io_active,
        'process_pending': process_pending,
        'process_workers': process_workers,
    }


def format_sample(snapshot):
    return ' '.join(
        '{}={}'.format(key, 'n/a' if value is None else value)
        for key, value in snapshot.items()
    )


def is_backed_up(snapshot):
    return any(
        value is not None and value >= BACKLOG_ITEM_THRESHOLD
        for key, value in snapshot.items()
        if key in ('stdout_queue', 'action_log_pending', 'io_pending')
    )


def start(io_executor=None, process_executor=None, stop_event=None):
    """Run the sampler on a daemon thread until `stop_event` is set.

    Daemon on purpose: this is observability, and it must never be the reason a
    run fails to exit.
    """
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    stop_event = stop_event or threading.Event()

    def loop():
        backed_up_since = None
        last_reported = 0.0
        while not stop_event.wait(SAMPLE_INTERVAL_SECONDS):
            try:
                script_logger = ScriptLogger.get_logger()
                snapshot = sample(io_executor, process_executor)
                script_logger.log('QUEUE DEPTHS:', format_sample(snapshot), level='debug')
                _sample_children()

                now = time.monotonic()
                if is_backed_up(snapshot):
                    if backed_up_since is None:
                        backed_up_since = now
                        last_reported = 0.0
                    if now - last_reported >= BACKLOG_REPEAT_SECONDS:
                        last_reported = now
                        script_logger.log(
                            'QUEUE BACKLOG: writers behind for {:.0f}s —'.format(now - backed_up_since),
                            format_sample(snapshot),
                            level='info'
                        )
                elif backed_up_since is not None:
                    script_logger.log(
                        'QUEUE BACKLOG: cleared after {:.0f}s —'.format(now - backed_up_since),
                        format_sample(snapshot),
                        level='info'
                    )
                    backed_up_since = None
            except Exception:
                # A diagnostic thread must not take the run down with it.
                pass

    thread = threading.Thread(target=loop, name='backpressure-monitor', daemon=True)
    thread.start()
    return stop_event
