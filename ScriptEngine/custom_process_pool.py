import threading
import time
from concurrent.futures import ProcessPoolExecutor, ALL_COMPLETED, wait

from ScriptEngine.shared_memory_args import SharedArgSender, call_with_shared_args, sends_shared_memory


class CustomProcessPool(ProcessPoolExecutor):
    def __init__(self, max_workers=None, mp_context=None, **kwargs):
        super().__init__(max_workers, mp_context=mp_context, **kwargs)
        # Large numpy arguments go to the workers through shared memory, once
        # per array, instead of through the call queue's pipe once per task;
        # see shared_memory_args. None where the start method rules it out.
        self._shared_args = SharedArgSender() if sends_shared_memory(self._mp_context) else None
        self.active_tasks = []
        self.max_workers_configured = max_workers
        # Worker processes are created lazily on submit, under the 'spawn' start
        # method, so each one re-executes the interpreter and re-imports the
        # engine — the whole frozen bundle in a packaged build. That cost lands
        # on whichever action happens to be first, where it is indistinguishable
        # from a slow action unless it is recorded separately.
        self._pool_created_at = time.monotonic()
        self._first_submit_at = None
        self._observed_workers = 0
        self._lifecycle_lock = threading.Lock()

    def submit(self, fn, *args, **kwargs):
        submitted_at = time.monotonic()
        with self._lifecycle_lock:
            if self._first_submit_at is None:
                self._first_submit_at = submitted_at
        blocks = ()
        if self._shared_args is not None:
            args, kwargs, blocks = self._shared_args.pack(args, kwargs)
        # Submit the task and track it
        if blocks:
            try:
                future = super().submit(call_with_shared_args, fn, args, kwargs)
            except BaseException:
                self._shared_args.release(blocks)
                raise
            # Done covers a result, an exception, a cancel and a broken pool.
            future.add_done_callback(lambda _f, blocks=blocks: self._shared_args.release(blocks))
        else:
            future = super().submit(fn, *args, **kwargs)
        self.active_tasks.append(future)
        self._note_worker_growth(submitted_at)
        # Add a callback to remove the task from active list once done
        future.add_done_callback(self._remove_task)
        return future

    def _note_worker_growth(self, submitted_at):
        """Log each newly spawned worker and what it cost the caller waiting on it.

        ProcessPoolExecutor does not announce worker creation, but it does keep
        them in `_processes`, so growth in that mapping is a spawn. Info level:
        this is a handful of lines per run and it is the clearest signal of what
        packaging costs at startup.
        """
        try:
            from ScriptEngine.common.logging.script_logger import ScriptLogger

            current = len(getattr(self, '_processes', {}) or {})
            with self._lifecycle_lock:
                if current <= self._observed_workers:
                    return
                spawned = current - self._observed_workers
                self._observed_workers = current
                first_submit_at = self._first_submit_at

            ScriptLogger.get_logger().log(
                'PROCESS POOL: {} worker(s) spawned, {} of {} live '
                '(+{:.2f}s since pool created, +{:.2f}s since first submit)'.format(
                    spawned, current, self.max_workers_configured,
                    submitted_at - self._pool_created_at,
                    submitted_at - first_submit_at if first_submit_at else 0.0
                ),
                level='info'
            )
        except Exception:
            # Instrumentation must never break dispatch.
            pass

    def _remove_task(self, future):
        # Remove the completed task from the active list
        self.active_tasks.remove(future)

    def shutdown(self, wait=True, *, cancel_futures=False):
        super().shutdown(wait=wait, cancel_futures=cancel_futures)
        # With wait=False, blocks that unfinished tasks still use are unlinked
        # as each of those tasks finishes.
        if self._shared_args is not None:
            self._shared_args.close()

    def get_active_tasks(self):
        # Return the list of currently active tasks
        return [f for f in self.active_tasks if not f.done()]

    def lifecycle_summary(self):
        with self._lifecycle_lock:
            return 'process_pool workers_spawned={} configured={} first_submit_delay={:.2f}s'.format(
                self._observed_workers,
                self.max_workers_configured,
                (self._first_submit_at - self._pool_created_at) if self._first_submit_at else 0.0
            )

    async def soft_shutdown(self, script_logger, timeout=30):
        process_futures = self.active_tasks

        process_done, process_not_done = wait(process_futures, timeout=timeout, return_when=ALL_COMPLETED)
        script_logger.log("Shutting down process pool...")
        self.shutdown(wait=False)

        # Handle any unfinished tasks
        if process_not_done:
            script_logger.log(
                f"Timeout reached. Cancelling unfinished processes. {len(process_not_done)} processes are still active.", level='error')
            for future in process_not_done:
                future.cancel()
        script_logger.log('Completed shutting down process pool')
