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
    def get_rv_val(delayTypeData, repeats: int = None) -> List[float]:
        script_logger.log('calculating delay value')
        if delayTypeData["distributionType"] == 'normal':
            mean = delayTypeData["normalDistMean"]
            stddev = delayTypeData["normalDistStdDev"]
            mins = ((
                        delayTypeData["normalDistMin"] if repeats is None else np.repeat(delayTypeData["normalDistMin"], repeats)
                    ) - mean) / stddev
            maxes = ((
                delayTypeData["normalDistMax"] if repeats is None else np.repeat(delayTypeData["normalDistMax"], repeats)
            ) - mean) / stddev
            from scipy.stats import truncnorm
            rv_vals = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
            rv_vals = [rv_vals] if repeats is None else rv_vals
            return rv_vals
        elif delayTypeData["distributionType"] == "uniform":
            min_val = delayTypeData["uniformDistMin"]
            max_val = delayTypeData["uniformDistMax"]
            dist_range = max_val - min_val
            if repeats is None:
                rv_vals = [random.random() * dist_range + min_val]
            else:
                rv_vals = [(random.random() * dist_range + min_val) for _ in range(0, repeats)]
            return rv_vals
        else:
            exception_message = 'random variable unimplemented: ' + delayTypeData["distributionType"]
            script_logger.log(exception_message)
            raise Exception(exception_message)