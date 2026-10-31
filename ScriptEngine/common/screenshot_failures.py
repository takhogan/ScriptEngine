"""Makes a screenshot that cannot be taken a failed check, for a while.

A device that shows nothing used to end the run: a PC behind a PiKVM with no
HDMI signal, an adb device that dropped off, an iPhone whose tunnel went away.
screenshot() raised and nothing between it and the script manager caught it.
Scripts are meant to restart from any state, which starts with looking at the
screen, so a detect on a device that cannot be seen now fails like a detect
that found nothing. firstMatch moves on to the next child (a keyboard action
that wakes the PC, say) and the batch retries as usual.

That only holds for a while. Once one device's screenshots have failed for
SCREENSHOT_FAILURE_LIMIT_SECONDS with no successful screenshot in between, the
run stops in error instead of retrying a device that is not coming back.
"""

import os
import threading
import time


# How long one device's screenshots may fail without a single success before
# the run stops in error. SCREENPLAN_SCREENSHOT_FAILURE_LIMIT_SECONDS overrides it.
SCREENSHOT_FAILURE_LIMIT_SECONDS = float(os.environ.get('SCREENPLAN_SCREENSHOT_FAILURE_LIMIT_SECONDS', '300'))


class ScreenshotFailedError(Exception):
    """A screenshot could not be taken. The action that needed it fails."""

    def __init__(self, device_name, cause, failing_for_s):
        self.device_name = device_name
        self.cause = cause
        self.failing_for_s = failing_for_s
        super().__init__('could not take a screenshot of {}: {}: {} (failing for {:.0f}s)'.format(
            device_name, type(cause).__name__, cause, failing_for_s
        ))


class ScreenshotFailureLimitError(Exception):
    """One device's screenshots have failed for the whole limit. Ends the run."""


class ScreenshotFailureTracker:
    """Times one device's current run of failed screenshots.

    Shared by the run's main thread and the threads that draw click log
    images, which take screenshots of their own, so updates hold a lock.
    """

    def __init__(self, device_name, limit_s=SCREENSHOT_FAILURE_LIMIT_SECONDS, clock=time.monotonic):
        self.device_name = device_name
        # None: failures never end the run (the interactive device controller).
        self.limit_s = limit_s
        self.clock = clock
        # When the first screenshot of the current failing stretch was started;
        # None while the last screenshot succeeded.
        self.failing_since = None
        self.failure_count = 0
        self._lock = threading.Lock()

    def capture(self, take, counts_as_success=True):
        """Return take(), or raise ScreenshotFailedError / ScreenshotFailureLimitError.

        counts_as_success=False is for a call that may not have taken a
        screenshot at all, such as initializing a device that already is: it
        succeeding says nothing about whether the screen can be read now.
        """
        started_at = self.clock()
        try:
            result = take()
        except (ScreenshotFailedError, ScreenshotFailureLimitError):
            raise
        except Exception as cause:
            raise self._failed(started_at, cause) from cause
        if counts_as_success:
            with self._lock:
                self.failing_since = None
                self.failure_count = 0
        return result

    def _failed(self, started_at, cause):
        with self._lock:
            if self.failing_since is None:
                self.failing_since = started_at
            self.failure_count += 1
            failing_for_s = self.clock() - self.failing_since
            failure_count = self.failure_count
        if self.limit_s is not None and failing_for_s >= self.limit_s:
            return ScreenshotFailureLimitError(
                'Screenshots of {} have failed for {:.0f} minutes ({} failed in a row, none succeeded), '
                'which is the limit of {:.0f} minutes. Last error: {}: {}'.format(
                    self.device_name, failing_for_s / 60, failure_count, self.limit_s / 60,
                    type(cause).__name__, cause
                )
            )
        return ScreenshotFailedError(self.device_name, cause, failing_for_s)
