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
            start_time = time.time()
            for [parallel_index, (handle_function, handle_args)] in parallel_actions:
                futures[executor.submit(handle_function, *handle_args)] = (parallel_index, handle_args[0]['actionGroup'])
            future_results = [None] * (1 + stop_index - start_index)
            completed_indices = set()
            success_index = None
            print('before .result()')
            for future in concurrent.futures.as_completed(futures):
                (completed_index,completed_actionGroup) = futures[future]
                result = future.result()
                future_results[completed_index - start_index] = result
                (future_status, _) = result
                print(completed_actionGroup, 'completed ', time.time() - start_time, 'result: ', future_status)
                completed_indices.add(completed_index)
                if future_status == ScriptExecutionState.SUCCESS and \
                        set(range(start_index, completed_index)).issubset(completed_indices):
                    success_index = completed_index
                    print('returning with success action: ', completed_actionGroup)
                    for other_future in futures:
                        other_future.cancel()
                    break
            if success_index is not None:
                return success_index,future_results[success_index - start_index][1]
            else:
                return stop_index,future_results[-1][1]