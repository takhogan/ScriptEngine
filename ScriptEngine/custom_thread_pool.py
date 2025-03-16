from concurrent.futures import ThreadPoolExecutor,ALL_COMPLETED, wait

class CustomThreadPool(ThreadPoolExecutor):
    def __init__(self, max_workers=None):
        super().__init__(max_workers)
        self.active_tasks = []

    def submit(self, fn, *args, **kwargs):
        # Submit the task and track it
        future = super().submit(fn, *args, **kwargs)
        self.active_tasks.append(future)
        # Add a callback to remove the task from active list once done
        future.add_done_callback(self._remove_task)
        return future

    def _remove_task(self, future):
        # Remove the completed task from the active list
        self.active_tasks.remove(future)

    def get_active_tasks(self):
        # Return the list of currently active tasks
        return [f for f in self.active_tasks if not f.done()]

    async def soft_shutdown(self, script_logger, timeout=30):
        thread_futures = self.active_tasks

        threads_done, threads_not_done = wait(thread_futures, timeout=timeout, return_when=ALL_COMPLETED)
        script_logger.log("Shutting down thred pool...")
        self.shutdown(wait=False)

        # Handle any unfinished tasks
        if threads_not_done:
            script_logger.log(
                f"Timeout reached. Cancelling unfinished threads. {len(threads_not_done)} threads are still active.")
            for future in threads_not_done:
                future.cancel()
        script_logger.log('Completed shutting down thread pool')