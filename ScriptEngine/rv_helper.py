from scipy.stats import truncnorm
import numpy as np
import random
import time
from script_logger import ScriptLogger
from script_engine_utils import state_eval
from typing import List
script_logger = ScriptLogger()
class RandomVariableHelper:

    def __init__(self):
        pass

    @staticmethod
    def parse_post_action_delay(delayArg, state):
        post_delay = 0
        if delayArg.isdigit():
            post_delay = int(delayArg)
        else:
            post_delay = int(state_eval(delayArg, {}, state))
        script_logger.log('post action sleep for ', post_delay, 'seconds')
        time.sleep(post_delay)

    @staticmethod
    def get_rv_val(action, repeats: int = None) -> List[float]:
        if action["actionData"]["distType"] == 'normal':
            mean = action["actionData"]["mean"]
            stddev = action["actionData"]["stddev"]
            mins = ((
                        action["actionData"]["min"] if repeats is None else np.repeat(action["actionData"]["min"])
                    ) - mean) / stddev
            maxes = ((
                action["actionData"]["max"] if repeats is None else np.repeat(action["actionData"]["max"])
            ) - mean) / stddev
            rv_vals = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
            rv_vals = [rv_vals] if repeats is None else rv_vals
            return rv_vals
        elif action["actionData"]["distType"] == "uniform":
            min_val = action["actionData"]["min"]
            max_val = action["actionData"]["max"]
            dist_range = max_val - min_val
            if repeats is None:
                rv_vals = [random.random() * dist_range + min_val]
            else:
                rv_vals = [(random.random() * dist_range + min_val) for _ in range(0, repeats)]
            return rv_vals
        else:
            script_logger.log('random variable unimplemented: ' + action["actionData"]["distType"])
            exit(0)