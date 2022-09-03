import sys
import random
import time
from dateutil import tz


import datetime

sys.path.append(".")
from script_loader import parse_zip
from script_executor import ScriptExecutor


def run_script_sequence(script_sequence, sequences, timeout):
    def parse_delay_command(delay_obj):
        print('parsing delay')
        rand_val = random.random()
        if '(' in delay_obj:
            delay_range_repr = delay_obj[1:-1].split(',')
        else:
            delay_range_repr = delay_obj.split(',')

        delay_range_repr = [int(delay_range_repr[0]), int(delay_range_repr[1])]
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


    for script in script_sequence['sequence']:
        if script in sequences:
            run_script_sequence(sequences[script], sequences, timeout)
        else:
            print('running script ', script)
            load_and_run(script, timeout)


def parse_script_sequence_def(script_sequence_def):
    is_sequence_def = False
    sequence_name = None
    sequences = {}
    main_sequence = {
        'sequence': [],
        'constants': {},
        'commands': {}
    }
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
        if line[0] != '\t':
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
                sequences[sequence_name]['sequence'].append(line)
        else:
            if line[0].strip() == '[':
                line = line.strip()[1:-1]
                def_statement = line.split(':')
                if def_statement[0].upper() == def_statement[0]:
                    main_sequence['constants'][def_statement[0]] = def_statement[1]
                else:
                    main_sequence['commands'][def_statement[0]] = def_statement[1]
            else:
                main_sequence['sequence'].append(line)
    return main_sequence,sequences

def parse_and_run_script_sequence_def(script_sequence_def, timeout):
    main_sequence,sequences = parse_script_sequence_def(script_sequence_def)
    print(main_sequence, sequences)
    if 'onInit' in sequences:
        run_script_sequence(sequences['onInit'], sequences, timeout)

    run_script_sequence(main_sequence, sequences, timeout)

    if 'onDestroy' in sequences:
        run_script_sequence(sequences['onDestroy'], sequences, timeout)


def load_and_run(script_name, timeout):
    # if you want to open zip then you pass .zip in command line args
    script_object = parse_zip('./scripts/' + script_name)
    # print(script_object)
    #https://stackoverflow.com/questions/28331512/how-to-convert-pythons-isoformat-string-back-into-datetime-object
    if isinstance(timeout, str):
        dt, _, us = timeout.partition(".")
        utc_tz = tz.gettz('UTC')
        is_utc = timeout[-1] == 'Z'
        timeout = datetime.datetime.strptime(timeout[:-1], "%Y-%m-%dT%H:%M:%S")
        if is_utc:
            timeout = timeout.replace(tzinfo=utc_tz).astimezone(tz.tzlocal())
    main_script = ScriptExecutor(script_object, timeout)
    main_script.run(log_level='INFO')



if __name__=='__main__':
    script_name = sys.argv[1]
    load_and_run(script_name, datetime.datetime.now() + datetime.timedelta(minutes=30))