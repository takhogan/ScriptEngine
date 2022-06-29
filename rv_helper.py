from scipy.stats import truncnorm

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
            print(delays)
            return delays
        else:
            print('random variable unimplemented: ' + action["actionData"]["distType"])
            exit(0)