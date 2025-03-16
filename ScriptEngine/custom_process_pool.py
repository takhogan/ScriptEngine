from concurrent.futures import ProcessPoolExecutor,ALL_COMPLETED, wait

class CustomProcessPool(ProcessPoolExecutor):
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
        process_futures = self.active_tasks

        process_done, process_not_done = wait(process_futures, timeout=timeout, return_when=ALL_COMPLETED)
        script_logger.log("Shutting down process pool...")
        self.shutdown(wait=False)

        # Handle any unfinished tasks
        if process_not_done:
            script_logger.log(
                f"Timeout reached. Cancelling unfinished processes. {len(process_not_done)} processes are still active.")
            for future in process_not_done:
                future.cancel()
        script_logger.log('Completed shutting down process pool')

