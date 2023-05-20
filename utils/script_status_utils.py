import datetime
import os
import json
import time
import requests
from dateutil import tz

RUNNING_SCRIPTS_PATH = './tmp/running_scripts.json'
RUNNING_EVENTS_PATH = './tmp/running_events.json'
COMPLETED_EVENTS_PATH = './tmp/completed_events.json'


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
        # if is_utc:
        #     timeout = timeout.replace(tzinfo=utc_tz).astimezone(tz.tzlocal())
    return timeout

def persist_event_status(event_name, running_event):
    running_events = get_running_events(convert_timeout=False)
    if running_event is not None:
        running_event = running_event.copy()
        running_event['timeout'] = running_event['timeout'].strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + 'Z'
        running_event['start_time'] = running_event['start_time'].strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + 'Z'

    with open(RUNNING_EVENTS_PATH, 'w') as running_events_file:
        if len(running_events) > 0 and running_events[0]['sequence_name'] == event_name:
            if running_event is None:
                running_events = running_events[1:]
            else:
                running_events[0] = running_event
        else:
            running_events = [running_event]
        json.dump(running_events, running_events_file)

def get_running_scripts():
    running_scripts = []
    if os.path.exists(RUNNING_SCRIPTS_PATH):
        with open(RUNNING_SCRIPTS_PATH, 'r') as running_scripts_file:
            running_scripts = json.load(running_scripts_file)

    return running_scripts

def get_script_object(script_id):
    running_scripts = get_running_scripts()
    for running_script in running_scripts:
        if running_script['script_id'] == script_id:
            return running_script
    return None

def persist_running_script(running_script, script_id=None):
    running_scripts = get_running_scripts()
    if script_id is None:
        if running_script is not None:
            running_scripts.append(running_script)
    else:
        for script_index,running_script_iter in enumerate(running_scripts):
            if running_script_iter['script_id'] == script_id:
                if running_script is None:
                    del running_scripts[script_index]
                else:
                    running_scripts[script_index] = running_script
    with open(RUNNING_SCRIPTS_PATH, 'w') as runng_scripts_file:
        json.dump(running_scripts, runng_scripts_file)

def get_next_script_id():
    running_scripts = get_running_scripts()
    if len(running_scripts) > 0:
        return max(running_scripts, key=lambda script: script['script_id'])['script_id'] + 1
    else:
        return 1

def get_running_scripts_status():
    running_scripts = get_running_scripts()
    return str(running_scripts)

def get_running_events(convert_timeout=True):
    running_events = []
    if os.path.exists(RUNNING_EVENTS_PATH):
        with open(RUNNING_EVENTS_PATH, 'r') as running_events_file:
            running_events = json.load(running_events_file)
    if convert_timeout:
        for running_event in running_events:
            running_event['timeout'] = str_timeout_to_datetime_timeout(running_event['timeout'])
            running_event['start_time'] = str_timeout_to_datetime_timeout(running_event['start_time'])
    return running_events

def get_running_events_status():
    running_events = get_running_events()
    def running_event_obj_to_status(running_event_obj, depth=0):
        status_str = (' ' * ((depth - 1) if (depth - 1 >= 0) else 0) * 4) + running_event_obj['sequence_name'] + ' -> ' + running_event_obj['status'] + ':\n'
        for script_or_sequence in running_event_obj['sequence']:
            if script_or_sequence['type'] == 'script':
                status_str += (' ' * depth * 4) + script_or_sequence['script_name'] + ' -> ' + script_or_sequence['status'] + '\n'
            elif script_or_sequence['type'] == 'sequence':
                status_str += running_event_obj_to_status(script_or_sequence, depth + 1)
        return status_str

    running_events_statuses = list(map(
        running_event_obj_to_status,
        running_events
    ))
    return '\n'.join(running_events_statuses)

def get_completed_events():
    completed_events = []
    if os.path.exists(COMPLETED_EVENTS_PATH):
        with open(COMPLETED_EVENTS_PATH, 'r') as completed_events_file:
            completed_events = json.load(completed_events_file)
    for completed_event in completed_events:
        completed_event['timeout'] = str_timeout_to_datetime_timeout(completed_event['timeout'])
        completed_event['start_time'] = str_timeout_to_datetime_timeout(completed_event['start_time'])
    return completed_events

def get_completed_events_status():
    completed_events = get_completed_events()
    completed_events_statuses = list(map(
        lambda event: event['sequence_name'] + ": " + event["timeout"].strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + 'Z',
        completed_events
    ))
    return '\n'.join(completed_events_statuses)

def check_if_event_in_completed_events(event_name, start_time, event_id):
    completed_events = get_completed_events()
    print('is event ', event_name, ' completed? : ', any(
        completed_event['sequence_name'] == event_name and \
        completed_event['start_time'] == start_time and \
        completed_event['event_id'] == event_id for completed_event in completed_events
    ))
    return any(
        completed_event['sequence_name'] == event_name and \
        completed_event['start_time'] == start_time and \
        completed_event['event_id'] == event_id for completed_event in completed_events
    )

def check_if_event_enqueued(event_name, start_time, event_id):
    running_events = get_running_events()
    print('is event ', event_name, ' enqueued? : ', any(
        running_event['sequence_name'] == event_name and\
        running_event['start_time'] == start_time and\
        running_event['event_id'] == event_id for running_event in running_events
    ))
    return any(
        running_event['sequence_name'] == event_name and\
        running_event['start_time'] == start_time and\
        running_event['event_id'] == event_id for running_event in running_events
    )

def update_completed_events(event_object):
    print('updating completed events ', event_object)
    completed_events = get_completed_events()
    now = datetime.datetime.utcnow()
    new_completed_events = []
    for completed_event in completed_events:
        if completed_event['timeout'] > now:
            completed_event['timeout'] = completed_event['timeout'].strftime(
                "%Y-%m-%dT%H:%M:%S"
            ) + 'Z'
            completed_event['start_time'] = completed_event['start_time'].strftime(
                "%Y-%m-%dT%H:%M:%S"
            ) + 'Z',
            print('assigning 2', completed_event)
            new_completed_events.append(completed_event)
    event_object['start_time'] = event_object['start_time'].strftime(
        "%Y-%m-%dT%H:%M:%S"
    ) + 'Z'
    event_object['timeout'] = event_object['timeout'].strftime(
        "%Y-%m-%dT%H:%M:%S"
    ) + 'Z'
    new_completed_events.append(event_object)
    with open(COMPLETED_EVENTS_PATH, 'w') as completed_events_file:
        json.dump(new_completed_events, completed_events_file)

def check_terminate_signal(event_name):
    running_events = []
    if os.path.exists(RUNNING_EVENTS_PATH):
        with open(RUNNING_EVENTS_PATH, 'r') as running_events_file:
            try:
                running_events = json.load(running_events_file)
            except JSONDecodeError:
                running_events = []
    return not (len(running_events) > 0 and running_events[0]['sequence_name'] == event_name)


def await_script_load(event_name, script_name, is_await_queue, request_url):
    MAX_CHECK_COUNT = 10
    check_count = 0
    while True:
        if check_terminate_signal(event_name):
            print(event_name, 'received event terminate signal')
            break

        if is_await_queue:
            print(requests.get(request_url))
        elif check_count > MAX_CHECK_COUNT:
            break
        else:
            check_count += 1
        print('Awaiting script load ', script_name)
        running_scripts = []
        if os.path.exists(RUNNING_SCRIPTS_PATH):
            with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                running_scripts = json.load(running_script_file)

        if script_name in running_scripts:
            return True
        if is_await_queue:
            time.sleep(60)
        else:
            time.sleep(2)
    print('Script load timed out')
    return False


def await_script_completion(event_name, script_name):
    while True:
        print(event_name, ' awaiting script completion: ', script_name)
        if check_terminate_signal(event_name):
            print(event_name, 'received event terminate signal')
            break
        running_scripts = []
        if os.path.exists(RUNNING_SCRIPTS_PATH):
            with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                running_scripts = json.load(running_script_file)

        if script_name not in running_scripts:
            return True

        time.sleep(60)
    return False

def await_event_queue_availability():
    while True:
        print('Awaiting Event Queue Availability')
        running_events = get_running_events()
        if len(running_events) == 0:
            return True
        time.sleep(60)


def await_event_start(event_name):
    while True:
        print('Awaiting Event Start ', event_name)
        if check_terminate_signal(event_name):
            print(event_name, 'received event terminate signal')
            break
        running_events = []
        if os.path.exists(RUNNING_EVENTS_PATH):
            with open(RUNNING_EVENTS_PATH, 'r') as running_events_file:
                running_events = json.load(running_events_file)

        if len(running_events) > 0 and running_events[0]['sequence_name'] == event_name and running_events[0]['status'] == 'running':
            return True
        time.sleep(60)


if __name__ == '__main__':
    print(str_timeout_to_datetime_timeout('2023-03-15T15:00:00Z'))