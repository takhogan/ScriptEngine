import datetime
import json
import multiprocessing
import os.path
import random
import ssl

import httplib2.error
import requests
import socket
import sys
import time

from utils.script_status_utils import *

from collections import OrderedDict
from bs4 import BeautifulSoup
from dateutil import tz

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_NAME = 'ScriptScheduler'
REFRESH_GOOGLE_TOKEN_SCRIPT = 'Windows_RefreshGoogleToken'

REFRESH_EVENT_NAME = "REFRESH_GOOGLE_TOKEN_SCRIPT"
EXCLUDED_EVENTS = {
    REFRESH_EVENT_NAME
}

TEST_EVENT = """
[startDelay:0,240]
[targetHost:Taks-MacBook-Pro.local]
Windows_BlueStacks_ToWaoLoadingScreen
Windows_DoHourlyTasksShuffle
BlueStacks_WAO_SwitchBothToStaminaGear
onDestroy:
     Windows_CloseBlueStacks
"""

class ScriptScheduler:


    def __init__(self, host_server_ip):
        self.host_server_ip = host_server_ip
        self.host_name = socket.gethostname()

    def clean_description(self, description):
        # print('preclean : ', description)
        if bool(BeautifulSoup(description, "html.parser").find()):
            parsed_html = BeautifulSoup(description, features="html.parser")
            for u_tag in parsed_html.select('u'):
                u_tag.extract()
            for br_tag in parsed_html.find_all("br"):
                br_tag.replace_with("\n")
            description = parsed_html.get_text()
            # description = unicodedata.normalize("NFKC",)
        return description

    @staticmethod
    def constants_to_url_params(constants):
        if constants is None:
            return ''
        url_str = ''
        for key,value in constants.items():
            url_str += "&args=" + key + "%3A" + value
        return url_str


    def create_calendar_if_not_exists(self, service):
        calendars = {}
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for calendar_list_entry in calendar_list['items']:
                calendars[calendar_list_entry['summary']] = calendar_list_entry['id']
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break

        if CALENDAR_NAME not in calendars:
            print('creating calendar: ', CALENDAR_NAME)
            calendar = {
                'summary': CALENDAR_NAME,
                'timeZone' : 'UTC'
            }
            new_calendar = service.calendars().insert(body=calendar).execute()
            calendars[CALENDAR_NAME] = new_calendar.get('id')
        else:
            print('loaded existing calendar: ', CALENDAR_NAME)
        return calendars[CALENDAR_NAME]

    def initialize_service(self, force_refresh=False):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('assets/token.json'):
            creds = Credentials.from_authorized_user_file('assets/token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid or force_refresh:
            print('loaded creds were not valid, starting refresh')
            if not force_refresh:
                needs_refresh = True
            else:
                needs_refresh = False

            if (creds and creds.expired and creds.refresh_token) or force_refresh:
                try:
                    creds.refresh(Request())
                    needs_refresh = False
                except RefreshError as r:
                    print('refresh error!', r)
                    needs_refresh = True
                    pass
            if needs_refresh:
                print('calling refresh script')
                self.parse_and_run_script_sequence_def(
                    REFRESH_EVENT_NAME,
                    self.clean_description(REFRESH_GOOGLE_TOKEN_SCRIPT),
                    '1',
                    datetime.datetime.utcnow().strftime(
                        "%Y-%m-%dT%H:%M:%S") + 'Z',
                    (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).strftime(
                        "%Y-%m-%dT%H:%M:%S") + 'Z'
                )
                self.parse_event_queue()
                await_event_start(REFRESH_EVENT_NAME)
                # running_events['REFRESH_GOOGLE_TOKEN_SCRIPT'] = {}

            if force_refresh or needs_refresh:
                print('running local refresh server')
                flow = InstalledAppFlow.from_client_secrets_file(
                    'assets/credentials.json', SCOPES
                )
                # if issues here: https://github.com/googleapis/google-auth-library-python-oauthlib/issues/69
                creds = flow.run_local_server(port=0)
                await_script_completion(REFRESH_EVENT_NAME, REFRESH_GOOGLE_TOKEN_SCRIPT)
            # Save the credentials for the next run
            with open('assets/token.json', 'w') as token:
                token.write(creds.to_json())
        print('running with creds')
        service = build('calendar', 'v3', credentials=creds)

        try:

            calendar_id = self.create_calendar_if_not_exists(service)

        except HttpError as error:
            print('An error occurred: %s' % error)
            exit(0)


        return service,calendar_id

    def check_and_execute_active_tasks(self, service, calendar_id):
        now_datetime = datetime.datetime.utcnow()
        now_minus_five_datetime = now_datetime - datetime.timedelta(minutes=5)

        now = now_datetime.isoformat() + 'Z'
        now_minus_five = now_minus_five_datetime.isoformat() + 'Z'
        try:
            events_result = service.events().list(calendarId=calendar_id,
                                                  timeMin=now_minus_five,
                                                  timeMax=now,
                                                  singleEvents=True,
                                                  timeZone='UTC',
                                                  orderBy='startTime').execute()
        except RefreshError as r_error:
            print('Encountered Token error while calling calendar API: ',r_error)
            print('Renewing Token')
            self.initialize_service(force_refresh=True)
            return
        except ConnectionResetError as cr_error:
            print('Encountered Connection Reset error while calling calendar API : ',cr_error)
            print('Waiting 60 seconds')
            time.sleep(60)
            return
        except socket.gaierror as gaierror:
            print('Encountered Socket error while calling calendar API : ',gaierror)
            print('Waiting 60 seconds')
            time.sleep(60)
            return
        except httplib2.error.ServerNotFoundError as sr_error:
            print('Encountered Server Not Found error while calling calendar API : ', sr_error)
            print('Waiting 60 seconds')
            time.sleep(60)
            return
        except ssl.SSLEOFError as ssl_error:
            print('Encountered SSL Error while calling calendar API : ', ssl_error)
            print('Waiting 60 seconds')
            time.sleep(60)
            return
        events = events_result.get('items', [])

        if not events:
            pass
        else:
            for event in events:
                print('start time ', event['start']['dateTime'], event['end']['dateTime'])
                if not check_if_event_enqueued(
                    event['summary'],
                    str_timeout_to_datetime_timeout(event['start']['dateTime']),
                    '1'
                ) and not check_if_event_in_completed_events(
                    event['summary'],
                    str_timeout_to_datetime_timeout(event['start']['dateTime']),
                    '1'
                ):
                    event_plan = self.clean_description(event['description']) if 'description' in event else ''
                    print('loading event ', event['summary'])
                    self.parse_and_run_script_sequence_def(
                        event['summary'],
                        event_plan,
                        '1',
                        event['start']['dateTime'],
                        event['end']['dateTime']
                    )
        # event['summary']
        self.parse_event_queue()
        # event_list = set(map(lambda event: event['summary'], events))
        # delete_events = []
        # for event in running_events.keys():
        #     if event not in event_list:
        #         delete_events.append(event)
        # for event in delete_events:
        #     del running_events[event]
        request_url = "http://{}/queue".format(
            self.host_server_ip
        )
        running_scripts_str = requests.get(request_url).text
        print(now_minus_five, '-', now)
        print('active running events: ', get_running_events_status())
        print('completed events: ', get_completed_events_status())
        print('running scripts: ', running_scripts_str)

        # with open(RUNNING_EVENTS_PATH, 'w') as running_events_file:
        #     json.dump(running_events, running_events_file)

    def run_script_sequence(self, running_event, event_name, script_sequence, timeout, base=True):
        print('starting sequence : ', script_sequence['sequence_name'])
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

        extended_timeout = timeout
        if 'endExtension' in script_sequence['commands']:
            print('parsing end extension')
            extended_timeout = str_timeout_to_datetime_timeout(extended_timeout)
            delay_range_repr = get_command_tuple_val(script_sequence['commands']['endExtension'])
            if delay_range_repr[0] == delay_range_repr[1]:
                delay_val = delay_range_repr[0]
            else:
                delay_val = random.randrange(delay_range_repr[0], delay_range_repr[1])
            print('delaying end for ', delay_val)
            extended_timeout = extended_timeout + datetime.timedelta(seconds=delay_val)
            print('extended timeout : ', extended_timeout)
        if base:
            script_sequence['timeout'] = extended_timeout
            script_sequence['status'] = 'running'
            persist_event_status(event_name, running_event)


        if 'startDelay' in script_sequence['commands']:
            parse_delay_command(script_sequence['commands']['startDelay'])


        for script_or_sequence in script_sequence['sequence']:
            if script_or_sequence['type'] == 'script':
                print('running script ', script_or_sequence, extended_timeout)
                self.load_and_run(running_event, event_name, script_or_sequence, extended_timeout, constants=script_sequence['constants'])
            else:
                script_sequence['status'] = 'running'
                persist_event_status(event_name, running_event)
                self.run_script_sequence(running_event, event_name, script_or_sequence, extended_timeout, base=False)
        script_sequence['status'] = 'completed'
        if base:
            update_completed_events(running_event)
            running_event = None
        persist_event_status(event_name, running_event)

    def load_and_run(self, running_event, event_name, script_obj, timeout, constants=None):
        if check_terminate_signal(event_name):
            print('received terminate signal')
            return

        utcnow = datetime.datetime.utcnow()
        if timeout > utcnow:
            duration = timeout - utcnow
            duration_mins = duration.seconds / 60
            duration_hours = str(int(duration_mins // 60))
            duration_mins = str(int(duration_mins % 60)).zfill(2)
        else:
            script_obj['status'] = 'timed out'
            persist_event_status(event_name, running_event)
            return

        print('duration ', duration)
        script_name = script_obj['script_name']
        request_url = "http://{}/run/{}?timeout={}h{}m".format(
            self.host_server_ip, script_name, duration_hours, duration_mins
        ) + self.constants_to_url_params(constants)

        print('Script Scheduler invoking script: ', request_url)
        request_result = requests.get(request_url).text
        is_await_queue = False
        if 'Please wait for script completion' in request_result:
            #enqueue it later
            is_await_queue = True
        print(request_result)

        script_obj['status'] = 'invoking'
        persist_event_status(event_name, running_event)

        script_loaded = await_script_load(event_name, script_name, is_await_queue, request_url)
        if script_loaded:
            script_obj['status'] = 'running'
            persist_event_status(event_name, running_event)
            await_script_completion(event_name, script_name)
            script_obj['status'] = 'completed'
            persist_event_status(event_name, running_event)
        else:
            script_obj['status'] = 'timed out'
            persist_event_status(event_name, running_event)

    def create_script_event_object(self, script_event_obj, sequence_name):
        if 'onInit' in script_event_obj['sequences'] and script_event_obj['sequence'][0] != 'onInit':
            script_event_obj['sequence'] = [self.create_script_event_object(script_event_obj['sequences']['onInit'], 'onInit')] + script_event_obj['sequence']
        for item_index,script_or_sequence in enumerate(script_event_obj['sequence']):
            if script_or_sequence in script_event_obj['sequences']:
                script_event_obj['sequence'][item_index] = self.create_script_event_object(script_event_obj['sequences'][script_or_sequence], script_or_sequence)
            else:
                script_event_obj['sequence'][item_index] = {
                    'type' : 'script',
                    'script_name' : script_or_sequence,
                    'status' : 'waiting'#,
                    # 'timeout' : timeout
                }
        if 'onDestroy' in script_event_obj['sequences'] and script_event_obj['sequence'][-1] != 'onDestroy':
            onDestroy = script_event_obj['sequences']['onDestroy']
            onDestroy['commands']['endExtension'] = '900,900'
            script_event_obj['sequence'].append(self.create_script_event_object(onDestroy, 'onDestroy'))
        script_event_obj['sequence_name'] = sequence_name
        script_event_obj['type'] = 'sequence'
        script_event_obj['status'] = 'waiting'
        # script_event_obj['timeout'] = timeout
        del script_event_obj['sequences']
        return script_event_obj

    def parse_script_sequence_def(self, script_sequence_def, line_number=0, depth=0):
        main_sequence = {
            'sequence': [],
            'constants': {},
            'commands': {},
            'sequences' : {}
        }
        # print(script_sequence_def.split('\n'))
        line_index = 0
        for line_index,line in enumerate(script_sequence_def):
            # print('parsing line : ', line, line_index, line_number, line_index < line_number,not all(c == '\t' for c in line[0:depth]) and\
            #         not all(c == ' ' for c in line[0:depth * 4]) and\
            #         not all(ord(c) == 160 or ord(c) == 32 for c in line[0:depth * 5]))
            if line_index < line_number:
                continue
            if line == '':
                continue
            if not all(c == '\t' for c in line[0:depth]) and\
                    not all(c == ' ' for c in line[0:depth * 4]) and\
                    not all(ord(c) == 160 or ord(c) == 32 for c in line[0:depth * 5]):
                print(list(map(ord, line)))
                return main_sequence, line_index + 1
            if line[-1] == ':':
                sequence_name = line[:-1]
                print('defining sequence ')
                sequence, line_number = self.parse_script_sequence_def(script_sequence_def, line_number=line_index+1, depth=depth+1)
                print('end def')
                main_sequence['sequences'][sequence_name] = sequence
                continue

            if line[0].strip() == '[':
                line = line.strip()[1:-1]
                def_statement = line.split(':')
                if def_statement[0].upper() == def_statement[0]:
                    main_sequence['constants'][def_statement[0]] = def_statement[1]
                else:
                    main_sequence['commands'][def_statement[0]] = def_statement[1]
            else:
                main_sequence['sequence'].append(line.strip())

        return main_sequence, line_index + 1

    def parse_and_run_script_sequence_def(self, event_name, script_sequence_def, event_id, start_time, timeout):
        script_sequence_def = script_sequence_def.split('\n')
        main_sequence,_ = self.parse_script_sequence_def(script_sequence_def)
        start_time = str_timeout_to_datetime_timeout(start_time)
        timeout = str_timeout_to_datetime_timeout(timeout)
        main_sequence = self.create_script_event_object(main_sequence, event_name)
        main_sequence['start_time'] = start_time
        main_sequence['timeout'] = timeout
        main_sequence['event_id'] = str(event_id)
        if 'targetHost' in main_sequence['commands']:
            if self.host_name in main_sequence['commands']['targetHost'].split(','):
                pass
            else:
                print('Exiting event. Server host name is: ', self.host_name, '. Target host for script was ',
                      main_sequence['commands']['targetHost'])
                return
        print(event_name, ' event parsed : ', main_sequence)
        persist_event_status(event_name, main_sequence)

    def parse_event_queue(self):
        print('parsing event queue')
        running_events = get_running_events()
        if len(running_events) > 0 and running_events[0]['status'] == 'waiting':
            print('starting event : ', running_events[0]['sequence_name'])
            run_event_process = multiprocessing.Process(
                target=self.run_script_sequence,
                args=(
                    running_events[0],
                    running_events[0]['sequence_name'],
                    running_events[0],
                    running_events[0]['timeout']
                )
            )
            # running_events['REFRESH_GOOGLE_TOKEN_SCRIPT'] = {}
            run_event_process.daemon = True
            run_event_process.start()

    def run(self):
        print("Starting script scheduling service")
        service,calendar_id = self.initialize_service()
        print("Completed script scheduler setup, entering scheduler loop")
        while True:
            self.check_and_execute_active_tasks(service, calendar_id)
            time.sleep(60)




if __name__ == '__main__':
    script_scheduler = ScriptScheduler(sys.argv[1] + ":" + sys.argv[2])
    script_scheduler.run()
    # script_scheduler = ScriptScheduler('0.0.0.0')
    # script_sequence_def = TEST_EVENT
    # script_scheduler.parse_and_run_script_sequence_def('TEST_EVENT', script_sequence_def, '1',
    #                 datetime.datetime.utcnow().strftime(
    #                     "%Y-%m-%dT%H:%M:%S") + 'Z',
    #                 (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).strftime(
    #                     "%Y-%m-%dT%H:%M:%S") + 'Z')