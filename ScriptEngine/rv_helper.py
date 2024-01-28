from scipy.stats import truncnorm
import random
from script_logger import ScriptLogger
script_logger = ScriptLogger()
class RandomVariableHelper:

    def __init__(self):
        pass

    @staticmethod
    def get_rv_val(action):
        if action["actionData"]["distType"] == 'normal':
            mean = action["actionData"]["mean"]
            stddev = action["actionData"]["stddev"]
            mins = (action["actionData"]["min"] - mean) / stddev
            maxes = (action["actionData"]["max"] - mean) / stddev
            delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
            script_logger.log(delays)
            return delays
        elif action["actionData"]["distType"] == "uniform":
            min_val = action["actionData"]["min"]
            max_val = action["actionData"]["max"]
            dist_range = max_val - min_val
            return random.random() * dist_range + min_val
            pass
        else:
            script_logger.log('random variable unimplemented: ' + action["actionData"]["distType"])
            exit(0)