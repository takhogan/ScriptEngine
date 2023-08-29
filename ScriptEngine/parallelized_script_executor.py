import concurrent.futures
import sys
import time


sys.path.append("..")
from script_execution_state import ScriptExecutionState



class ParallelizedScriptExecutor:
    def __init__(self):
        pass

    @staticmethod
    def parallelized_execute(parallel_actions, start_index, stop_index):
        with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
            futures = {}
            for [parallel_index, (handle_function, handle_args)] in parallel_actions:
                futures[executor.submit(handle_function, *handle_args)] = parallel_index
            future_results = [None] * (1 + stop_index - start_index)
            completed_indices = set()
            success_index = None
            for future in concurrent.futures.as_completed(futures):
                completed_index = futures[future]
                print(completed_index, 'completed', time.time())
                result = future.result()
                future_results[completed_index - start_index] = result
                (_, future_status, _, _, _, _) = result
                completed_indices.add(completed_index)
                if future_status == ScriptExecutionState.SUCCESS and \
                        set(range(start_index, completed_index)).issubset(completed_indices):
                    success_index = completed_index
                    print('success_index', completed_index)
                    for other_future in futures:
                        other_future.cancel()
                    break
            if success_index is not None:
                return future_results[success_index - start_index][5]
            else:
                return future_results[-1][5]