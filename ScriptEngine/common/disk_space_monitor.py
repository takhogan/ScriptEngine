"""Fails the run once the disk it writes to is nearly full.

A run writes its action logs, overlay images and stdout to the data root while it
goes. With the disk close to full those writes start failing or stalling one by
one, and the run limps on producing a log that is missing pieces. Stopping in
error while there is still room to write the error is the better outcome.

The free-space reading happens on a daemon thread so a slow or unresponsive disk
never holds up the run itself; the run only reads the result, between actions,
through raise_if_low_disk().
"""

import shutil
import threading


# At or below this much free space the run stops in error.
MIN_FREE_BYTES = 2 * 1024 ** 3

CHECK_INTERVAL_SECONDS = 30.0


class LowDiskSpaceError(Exception):
    pass


_low_disk_error = None


def _check(path):
    free_bytes = shutil.disk_usage(path).free
    if free_bytes <= MIN_FREE_BYTES:
        return LowDiskSpaceError(
            'Only {:.2f} GB free on the disk holding {} (minimum is more than {:.0f} GB)'.format(
                free_bytes / 1024 ** 3, path, MIN_FREE_BYTES / 1024 ** 3
            )
        )
    return None


def raise_if_low_disk():
    """Raise LowDiskSpaceError if the monitor has found the disk nearly full."""
    if _low_disk_error is not None:
        raise _low_disk_error


def start(path, stop_event=None):
    """Check free space on `path`'s disk now and every CHECK_INTERVAL_SECONDS
    after, on a daemon thread, until `stop_event` is set or the disk is found low.
    """
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    stop_event = stop_event or threading.Event()

    def loop():
        global _low_disk_error
        while True:
            try:
                error = _check(path)
            except Exception as e:
                # Not being able to read free space is not a reason to fail the run.
                ScriptLogger.get_logger().log('DISK SPACE: could not check free space on', path, e, level='debug')
                error = None
            if error is not None:
                ScriptLogger.get_logger().log('DISK SPACE:', str(error), level='error')
                _low_disk_error = error
                return
            if stop_event.wait(CHECK_INTERVAL_SECONDS):
                return

    thread = threading.Thread(target=loop, name='disk-space-monitor', daemon=True)
    thread.start()
    return stop_event
