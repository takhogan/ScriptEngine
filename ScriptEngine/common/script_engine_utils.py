import math
import os
import json
import random
import shutil
import subprocess
import sys
import platform
import datetime
import numpy as np
import glob
import collections
from types import SimpleNamespace
from dateutil import tz
from ScriptEngine.common.logging.script_logger import ScriptLogger
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

def safe_subprocess_run(args, timeout=5, capture_output=True, cwd="/", retry_on_timeout=True, **kwargs):
        """
        Helper method to run commands with consistent error handling and timeout management.
        
        Args:
            args: List of command arguments
            timeout: Timeout in seconds (default: 5)
            capture_output: Whether to capture stdout/stderr (default: True)
            cwd: Working directory (default: "/")
            **kwargs: Additional arguments to pass to subprocess.run
            
        Returns:
            subprocess.CompletedProcess object or None on error
        """        
        
        try:
            script_logger.log(f'safe_subprocess_run: running command: {" ".join(args)}')
            
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=capture_output,
                timeout=timeout,
                **kwargs
            )
            
            if result.returncode == 0:
                script_logger.log(f'safe_subprocess_run: command succeeded')
            else:
                script_logger.log(f'safe_subprocess_run: command failed with return code {result.returncode}')
                if capture_output and result.stderr:
                    script_logger.log(f'safe_subprocess_run: stderr: {result.stderr.decode()}')
            
            return result
            
        except subprocess.TimeoutExpired as e:
            script_logger.log(f'safe_subprocess_run: command timed out after {timeout}s: {" ".join(args)}')
            if retry_on_timeout:
                safe_subprocess_run(args, timeout=timeout, capture_output=capture_output, cwd=cwd, retry_on_timeout=False, **kwargs)
            else:
                raise e
        except Exception as e:
            script_logger.log(f'safe_subprocess_run: error running command {" ".join(args)}: {e}')
            raise e


class StateEvaluator:
    """Helper for evaluating state expressions with shared context."""

    _base_globals = {
        'glob': glob,
        'datetime': datetime,
        'os': os,
        'sys': sys,
        'platform': platform,
        'shutil': shutil,
        'numpy': np,
        're': re,
        'json': json,
        'random': random,
        'math': math,
        'collections': collections,
    }

    _script_context = SimpleNamespace(
        script_name=None,
        script_id=None,
        timeout=None,
        script_start_time=None,
        device_details=None,
    )

    @classmethod
    def configure_script_context(cls, *, script_name=None, script_id=None, timeout=None, script_start_time=None, device_details=None):
        """Store the current script metadata for downstream state evaluations."""
        cls._script_context = SimpleNamespace(
            script_name=script_name,
            script_id=script_id,
            timeout=timeout,
            script_start_time=script_start_time,
            device_details=device_details,
        )

    @classmethod
    def eval(cls, statement, global_overrides, local_scope, crashonerror=True):
        env_globals = cls._base_globals.copy()
        if global_overrides:
            env_globals.update(global_overrides)
        if local_scope:
            env_globals.update(local_scope)
        env_globals.setdefault('script', cls._script_context)

        try:
            return eval(statement, env_globals, local_scope)
        except KeyError:
            script_logger.log(
                'ERROR: key error while parsing eval, keys present in state: ' + ', '.join(list(env_globals))
            )
            if not crashonerror:
                script_logger.log('script finished with failure, ignoring key error')
                return None
            raise


def state_eval(statement, globals, locals, crashonerror=True):
    return StateEvaluator.eval(statement, globals, locals, crashonerror=crashonerror)
