from scipy.stats import truncnorm
import random
import time
from script_logger import ScriptLogger
from script_engine_utils import state_eval
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
    def get_rv_val(action):
        if action["actionData"]["distType"] == 'normal':
            mean = action["actionData"]["mean"]
            stddev = action["actionData"]["stddev"]
            mins = (action["actionData"]["min"] - mean) / stddev
            maxes = (action["actionData"]["max"] - mean) / stddev
            delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)
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