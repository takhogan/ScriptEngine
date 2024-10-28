import math
import numpy as np
import os
import json
from dateutil import tz
from script_logger import ScriptLogger
script_logger = ScriptLogger()

RUNNING_SCRIPTS_PATH = './tmp/running_scripts.json'


class DummyFile:
    def write(self, *args, **kwargs):
        # Ignore anything written
        pass

    def writelines(self, lines):
        # Ignore any lines written
        pass

    def flush(self):
        # No-op for flushing
        pass

    def close(self):
        # No-op for closing
        pass

imageFileExtensions = [
    'jpg', 'jpeg',
    'png',
    'gif',
    'bmp',
    'tiff', 'tif',
    'svg',
    'webp',
    'ico',
    'heif',
    'heic',
    'jfif',
    'pjpeg',
    'pjp'
  ]

def generate_context_switch_action(childGroups, state, context, update_dict):
    return {
        "actionName" : "contextSwitchAction",
        "actionGroup" : 0,
        "childGroups" : childGroups,
        "actionData" : {
            "targetSystem": "none",
            "state" : state,
            "context" : context,
            "update_dict" : update_dict
        }
    }

def masked_mse(target_im, compare_im, mask_size):
    return 1 - np.sum(np.square(np.subtract(target_im, compare_im))) / mask_size


def is_null(item):
    return item is None or item == 'None' or item == 'null' or item == 'undefined'


def dist(x1, y1, x2, y2):
    return math.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)


def get_digits(number):
    if number == 0:
        return [0]
    digits = []
    while number != 0:
        chopped_number = int(number / 10)
        digit = number - chopped_number * 10
        digits.insert(0, digit)
        number = chopped_number
    return digits


import subprocess
import re


def datetime_to_local_str(datetime, delim=':'):
    return datetime.astimezone(tz.tzlocal()).strftime('%Y-%m-%d %H{}%M{}%S'.format(delim, delim))

# Mapping dictionary with key-value pairs
variable_mapping = {
    "var1": "value1",
    "var3": "value3"
}

def apply_state_to_cmd_str(cmd_str, state):

    # Custom string formatter that replaces %KEY% placeholders with dictionary values
    class CustomFormatter:
        def __init__(self, mapping):
            self.mapping = mapping

        def format(self, text):
            pattern = r"%(\w+)%"
            return re.sub(pattern, lambda m: self.mapping.get(m.group(1), m.group()), text)

    # Replace %KEY% placeholders with dictionary values if they exist, otherwise leave them unchanged
    formatter = CustomFormatter(state)
    formatted_command = formatter.format(cmd_str)
    return formatted_command


def is_parallelizeable(action):
    return action['actionName'] == 'detectObject'


def get_glob_digit_regex_string(start_index, stop_index, pad_zeros=False):
    if start_index > stop_index:
        return []
    stop_index_digits = get_digits(stop_index)
    top_range_digit = stop_index_digits[0] - 1
    start_index_digits = get_digits(start_index)
    if len(start_index_digits) < len(stop_index_digits):
        bottom_range_digit = 1 if start_index != 0 else 0
    else:
        bottom_range_digit = start_index_digits[0] + 1
    # script_logger.log('start: ', start_index, 'stop: ', stop_index)
    if stop_index < 10:
        return [
            '[{}-{}]'.format(start_index, stop_index) if start_index < stop_index
            else '[{}]'.format(start_index)
        ]
    stop_index_digits_foot_str = ''.join(map(str, stop_index_digits[1:]))
    stop_index_digits_foot = int(stop_index_digits_foot_str)
    if start_index_digits[0] == stop_index_digits[0]:
        start_index_digits_foot_str = ''.join(map(str, start_index_digits[1:]))
        top_range_foot = int(start_index_digits_foot_str)
        top_range_n_zeros = len(start_index_digits_foot_str) - len(str(top_range_foot))
        top_range_only = True
    elif start_index_digits[0] < stop_index_digits[0]:
        top_range_n_zeros = 0
        top_range_foot = 0
        top_range_only = False
    else:
        top_range_n_zeros = len(stop_index_digits_foot_str) - len(str(stop_index_digits_foot))
        top_range_foot = int(stop_index_digits_foot / 10) * 10
        top_range_only = False
    top_range_footers = get_glob_digit_regex_string(
        top_range_foot,
        stop_index_digits_foot
    )
    top_range = ['[{}]'.format(stop_index_digits[0]) + '[0]' * top_range_n_zeros + top_range_footer for
                 top_range_footer in top_range_footers]
    # script_logger.log('top_range: ', top_range_footers)
    if top_range_only:
        return top_range
    # script_logger.log('s: ', start_index, 'st: ', stop_index, 'top: ', top_range)
    if start_index == 0:
        bottom_range = []
    elif start_index < 10:
        bottom_range = ['[{}-9]'.format(start_index) if start_index != 9 else '[9]']
        bottom_range_head = 10
    else:
        start_index_digits_foot_str = ''.join(map(str, start_index_digits[1:]))
        start_index_digits_foot = int(start_index_digits_foot_str)
        start_index_digits_foot_restr = str(start_index_digits_foot)
        start_index_n_zeros = len(start_index_digits_foot_str) - len(start_index_digits_foot_restr)
        if start_index_digits[0] < stop_index_digits[0]:
            bottom_range_head = int('9' * len(start_index_digits_foot_restr))
            bottom_pad = False
        else:
            bottom_range_head = int(start_index_digits_foot_restr[0] + '9' * (len(start_index_digits_foot_restr) - 1))
            bottom_pad = False
        bottom_range_footers = get_glob_digit_regex_string(
            start_index_digits_foot,
            bottom_range_head,
            bottom_pad
        )
        bottom_range = ['[{}]'.format(start_index_digits[0]) + (
                    '[0]' * (start_index_n_zeros + (1 if pad_zeros else 0))) + bottom_range_footer for
                        bottom_range_footer in bottom_range_footers]
    # middle_range_footers = get_glob_digit_regex_string(
    #     bottom_range_head + 1,
    #     top_range_foot - 1
    # )
    # script_logger.log(middle_range_footers)
    # exit(0)
    middle_range = [
        ('[{}-{}]'.format(bottom_range_digit, top_range_digit) if bottom_range_digit != top_range_digit
         else '[{}]'.format(bottom_range_digit)) + \
        ('[0-9]' * (len(stop_index_digits) - 1))
    ] if bottom_range_digit <= top_range_digit \
        else []
    # script_logger.log('m: ', middle_range)
    # script_logger.log('s: ', start_index, 'st: ', stop_index, 'bottom foot: ', bottom_range)
    return top_range + middle_range + bottom_range


def get_running_scripts():
    running_scripts = []
    if os.path.exists(RUNNING_SCRIPTS_PATH):
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_scripts_file:
            running_scripts = json.load(running_scripts_file)

    return running_scripts

def state_eval(statement, globals, locals, crashonerror=True):
    globals.update(locals)
    try:
        return eval(statement, globals, locals)
    except KeyError as k:
        script_logger.log(
            'ERROR: key error while parsing eval, keys present in state: ' + ', '.join(list(globals)))
        if not crashonerror:
            script_logger.log('script finished with failure, ignoring key error')
            return None
        raise