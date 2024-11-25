from concurrent.futures import ProcessPoolExecutor, Future

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
