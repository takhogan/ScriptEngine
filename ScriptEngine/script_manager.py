import sys
import random
import time
from dateutil import tz
import os
import json


import datetime

sys.path.append("..")
from script_loader import parse_zip
from script_executor import ScriptExecutor
from script_engine_constants import *

def str_timeout_to_datetime_timeout(timeout, src=None):
    if not isinstance(timeout, str):
        return timeout

    if src == 'deployment_server':
        timeout = datetime.datetime.strptime(timeout, "%Y-%m-%d %H-%M-%S")
    else:
        dt, _, us = timeout.partition(".")
        utc_tz = tz.gettz('UTC')
        is_utc = timeout[-1] == 'Z'
        timeout = datetime.datetime.strptime(timeout[:-1], "%Y-%m-%dT%H:%M:%S")
        if is_utc:
            timeout = timeout.replace(tzinfo=utc_tz).astimezone(tz.tzlocal())
    return timeout

def run_script_sequence(script_sequence, sequences, timeout):
    def get_command_tuple_val(command_val):
        if '(' in command_val:
            delay_range_repr = command_val[1:-1].split(',')
        else:
            delay_range_repr = command_val.split(',')

        return [int(delay_range_repr[0]), int(delay_range_repr[1])]

    def parse_delay_command(delay_obj):
        delay_range_repr = get_command_tuple_val(delay_obj)
        rand_val = random.random()
        print('parsing delay')
        delay_range = delay_range_repr[1] - delay_range_repr[0]
        delay_val = delay_range_repr[0] + rand_val * delay_range
        print('sleeping for ' + str(delay_val) + 's')
        time.sleep(delay_val)

    if 'dropoutChance' in script_sequence['commands']:
        dropoutRoll = random.random()
        if dropoutRoll < float(script_sequence['commands']['dropoutChance']):
            return

    if 'startDelay' in script_sequence['commands']:
        parse_delay_command(script_sequence['commands']['startDelay'])

    extended_timeout = timeout
    if 'endExtension' in script_sequence['commands']:
        print('parsing end extension')
        timeout = str_timeout_to_datetime_timeout(timeout)
        delay_range_repr = get_command_tuple_val(script_sequence['commands']['endExtension'])
        delay_val = random.randrange(delay_range_repr[0], delay_range_repr[1])
        print('delaying end for ', delay_val)
        extended_timeout = timeout + datetime.timedelta(seconds=delay_val)
        print('extended timeout : ', extended_timeout)


    for script in script_sequence['sequence']:
        if script in sequences:
            run_script_sequence(sequences[script], sequences, extended_timeout)
        else:
            print('running script ', script)
            load_and_run(script, extended_timeout, script_sequence['constants'])

def parse_constant_def(script_sequence_def):
    pass

def parse_script_sequence_def(script_sequence_def):
    is_sequence_def = False
    sequence_name = None
    sequences = {}
    main_sequence = {
        'sequence': [],
        'constants': {},
        'commands': {}
    }
    # print(script_sequence_def)
    # print(script_sequence_def.split('\n'))
    for line in script_sequence_def.split('\n'):
        if line == '':
            continue
        if line[-1] == ':':
            is_sequence_def = True
            sequence_name = line[:-1]
            sequences[sequence_name] = {
                'sequence': [],
                'commands': {},
                'constants': {}
            }
            continue
        if line[0].isalpha():
            is_sequence_def = False

        if is_sequence_def:
            if line[0].strip() == '[':
                line = line.strip()[1:-1]
                def_statement = line.split(':')
                if def_statement[0].upper() == def_statement[0]:
                    sequences[sequence_name]['constants'][def_statement[0]] = def_statement[1]
                else:
                    sequences[sequence_name]['commands'][def_statement[0]] = def_statement[1]
            else:
                sequences[sequence_name]['sequence'].append(line.strip())
        else:
            # print(line)
            if line[0].strip() == '[':
                line = line.strip()[1:-1]
                def_statement = line.split(':')
                # print(def_statement)
                if def_statement[0].upper() == def_statement[0]:
                    main_sequence['constants'][def_statement[0]] = def_statement[1]
                else:
                    main_sequence['commands'][def_statement[0]] = def_statement[1]
            else:
                main_sequence['sequence'].append(line)
    return main_sequence,sequences

def parse_and_run_script_sequence_def(script_sequence_def, timeout):
    print('def ', script_sequence_def)
    main_sequence,sequences = parse_script_sequence_def(script_sequence_def)
    print(main_sequence, sequences)
    timeout = str_timeout_to_datetime_timeout(timeout)
    if 'onInit' in sequences:
        run_script_sequence(sequences['onInit'], sequences, timeout)
    print('1')
    run_script_sequence(main_sequence, sequences, timeout)
    if 'onDestroy' in sequences:
        run_script_sequence(sequences['onDestroy'], sequences, timeout + datetime.timedelta(minutes=15))


def update_running_scripts_file(scriptname, action):
    if action == 'push':
        running_scripts = []
        if not os.path.exists(RUNNING_SCRIPTS_PATH):
            with open(RUNNING_SCRIPTS_PATH, 'w') as running_scripts_file:
                json.dump(running_scripts, running_scripts_file)
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
            running_scripts = json.load(running_script_file)
            if len(running_scripts) == 0 or running_scripts[0] != scriptname:
                running_scripts.append(scriptname)
        with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
            json.dump(running_scripts, running_script_file)
    elif action == 'pop':
        if not os.path.exists(RUNNING_SCRIPTS_PATH):
            return
        else:
            running_scripts = []
            with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                running_scripts = json.load(running_script_file)
                running_scripts.pop(0)
            print('running_scripts ', running_scripts)
            if len(running_scripts) == 0:
                os.remove(RUNNING_SCRIPTS_PATH)
            else:
                with open(RUNNING_SCRIPTS_PATH, 'w') as running_script_file:
                    json.dump(running_scripts, running_script_file)

def load_and_run(script_name, timeout, constants=None, start_time=None):
    # if you want to open zip then you pass .zip in command line args
    update_running_scripts_file(script_name, 'push')
    script_object = parse_zip(script_name)
    #https://stackoverflow.com/questions/28331512/how-to-convert-pythons-isoformat-string-back-into-datetime-objec
    # exit(0)
    main_script = ScriptExecutor(script_object, timeout, state=constants, start_time=start_time)
    main_script.run(log_level='INFO')
    print('completed script ', script_name, datetime.datetime.now())
    update_running_scripts_file(script_name, 'pop')



if __name__=='__main__':
    script_name = sys.argv[1]
    start_time = None
    end_time = None
    n_args = len(sys.argv)
    constants = {}
    if n_args > 2:
        start_time_str = sys.argv[2]
        start_time = str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')
    else:
        start_time = datetime.datetime.now()
        start_time_str = start_time.strftime('%Y-%m-%d %H-%M-%S')
    if n_args > 3:
        end_time = str_timeout_to_datetime_timeout(sys.argv[3], src='deployment_server').replace(tzinfo=tz.tzlocal())
    if n_args > 4:
        for arg_index in range(4, n_args):
            arg_split = sys.argv[arg_index].strip().split(':')
            constants[arg_split[0]] = arg_split[1]
    load_and_run(
        script_name,
        (start_time + datetime.timedelta(minutes=30)).replace(tzinfo=tz.tzlocal()) if end_time is None else end_time,
        start_time=start_time_str,
        constants=constants
    )