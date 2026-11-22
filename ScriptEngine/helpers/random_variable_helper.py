import numpy as np
import random
import time
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.script_engine_utils import state_eval, expression_text, eval_number
from typing import List
from ScriptEngine.common import sim_clock
script_logger = ScriptLogger()
class RandomVariableHelper:

    def __init__(self):
        pass

    @staticmethod
    def parse_post_action_delay(delayArg, state):
        """Sleep for an action's postActionDelay: a number, or an expression evaluated against state."""
        post_delay = eval_number(delayArg, state, default=0)
        script_logger.log('post action sleep for ', post_delay, 'seconds')
        if post_delay > 0:
            sim_clock.sleep(post_delay)

    @staticmethod
    def get_rv_val(delayTypeData, repeats: int = None) -> List[float]:
        script_logger.log('calculating delay value')
        # The distribution fields are string|number in the action schema.
        rv_param = lambda name: eval_number(delayTypeData[name], {})
        if delayTypeData["distributionType"] == 'normal':
            mean = rv_param("normalDistMean")
            stddev = rv_param("normalDistStdDev")
            dist_min = rv_param("normalDistMin")
            dist_max = rv_param("normalDistMax")
            mins = ((
                        dist_min if repeats is None else np.repeat(dist_min, repeats)
                    ) - mean) / stddev
            maxes = ((
                dist_max if repeats is None else np.repeat(dist_max, repeats)
            ) - mean) / stddev
            from scipy.stats import truncnorm 
            rv_vals = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
            rv_vals = [rv_vals] if repeats is None else rv_vals
            return rv_vals
        elif delayTypeData["distributionType"] == "uniform":
            min_val = rv_param("uniformDistMin")
            max_val = rv_param("uniformDistMax")
            dist_range = max_val - min_val
            if repeats is None:
                rv_vals = [random.random() * dist_range + min_val]
            else:
                rv_vals = [(random.random() * dist_range + min_val) for _ in range(0, repeats)]
            return rv_vals
        else:
            exception_message = 'random variable unimplemented: ' + delayTypeData["distributionType"]
            script_logger.log(exception_message, level='error')
            raise Exception(exception_message)