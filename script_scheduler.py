import datetime
import json
import multiprocessing
import os.path
import random
import requests
import sys
import time

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
RUNNING_SCRIPTS_PATH = './tmp/running_scripts.json'
REFRESH_GOOGLE_TOKEN_SCRIPT = 'Windows_RefreshGoogleToken'

class ScriptScheduler:


    def __init__(self, host_server_ip):
        self.host_server_ip = host_server_ip
    def str_timeout_to_datetime_timeout(self, timeout, src=None):
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

    def initialize_service(self):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('assets/token.json'):
            creds = Credentials.from_authorized_user_file('assets/token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            needs_refresh = True
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    needs_refresh = False
                except RefreshError:
                    pass
            if needs_refresh:
                refresh_process = multiprocessing.Process(
                    target=self.parse_and_run_script_sequence_def,
                    args=(
                        self.clean_description(REFRESH_GOOGLE_TOKEN_SCRIPT),
                        (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S") + 'Z'
                    )
                )
                refresh_process.start()
                flow = InstalledAppFlow.from_client_secrets_file(
                    'assets/credentials.json', SCOPES)
                # if issues here: https://github.com/googleapis/google-auth-library-python-oauthlib/issues/69
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open('assets/token.json', 'w') as token:
                token.write(creds.to_json())
        service = build('calendar', 'v3', credentials=creds)

        try:

            calendar_id = self.create_calendar_if_not_exists(service)

        except HttpError as error:
            print('An error occurred: %s' % error)
            exit(0)


        return service,calendar_id

    def check_and_execute_active_tasks(self, service, calendar_id, running_scripts):
        now_datetime = datetime.datetime.utcnow()
        now_plus_five_datetime = now_datetime + datetime.timedelta(minutes=5)

        now = now_datetime.isoformat() + 'Z'
        now_plus_five = now_plus_five_datetime.isoformat() + 'Z'
        try:
            events_result = service.events().list(calendarId=calendar_id,
                                                  timeMin=now,
                                                  timeMax=now_plus_five,
                                                  singleEvents=True,
                                                  timeZone='UTC',
                                                  orderBy='startTime').execute()
        except RefreshError as r_error:
            print(r_error)
            self.initialize_service()
            events_result = service.events().list(calendarId=calendar_id,
                                                  timeMin=now,
                                                  timeMax=now_plus_five,
                                                  singleEvents=True,
                                                  timeZone='UTC',
                                                  orderBy='startTime').execute()
        except ConnectionResetError as cr_error:
            print(cr_error)
            time.sleep(60)
            return
        events = events_result.get('items', [])

        if not events:
            pass
            # print('No events found.')
        else:
            event = events[0]

            if event['summary'] not in running_scripts:
                print(self.clean_description(event['description']))
                event_process = multiprocessing.Process(
                    target=self.parse_and_run_script_sequence_def,
                    args=(self.clean_description(event['description']), event['end']['dateTime'])
                )
                event_process.start()
                running_scripts[event['summary']] = {}
                pass
        # event['summary']

        event_list = set(map(lambda event: event['summary'], events))
        delete_events = []
        for event in running_scripts.keys():
            if event not in event_list:
                delete_events.append(event)
        for event in delete_events:
            del running_scripts[event]
        print(now, '-', now_plus_five, ' running scripts: ', list(running_scripts))

    def run_script_sequence(self, script_sequence, sequences, timeout):
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
            timeout = self.str_timeout_to_datetime_timeout(timeout)
            delay_range_repr = get_command_tuple_val(script_sequence['commands']['endExtension'])
            delay_val = random.randrange(delay_range_repr[0], delay_range_repr[1])
            print('delaying end for ', delay_val)
            extended_timeout = timeout + datetime.timedelta(seconds=delay_val)
            print('extended timeout : ', extended_timeout)


        for script in script_sequence['sequence']:
            if script in sequences:
                self.run_script_sequence(sequences[script], sequences, extended_timeout)
            else:
                print('running script ', script)

                self.load_and_run(script, extended_timeout, script_sequence['constants'])

    def load_and_run(self,script_name, timeout, constants=None):
        def await_script_load(script_name):
            MAX_CHECK_COUNT = 10
            for _ in range(0, MAX_CHECK_COUNT):
                print('Awaiting script load ', script_name)
                if os.path.exists(RUNNING_SCRIPTS_PATH):
                    running_scripts = []
                    with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                        running_scripts = json.load(running_script_file)

                    if script_name in running_scripts:
                        return True
                time.sleep(2)
            print('Script load timed out')
            return False

        def await_script_completion(script_name):
            while True:
                print('Awaiting Script Completion ', script_name)
                if os.path.exists(RUNNING_SCRIPTS_PATH):
                    running_scripts = []
                    with open(RUNNING_SCRIPTS_PATH, 'r') as running_script_file:
                        running_scripts = json.load(running_script_file)

                    if script_name not in running_scripts:
                        return True
                time.sleep(60)
            return False


        duration = timeout - datetime.datetime.now().replace(tzinfo=tz.tzlocal())
        duration_mins = duration.seconds / 60
        duration_hours = str(int(duration_mins // 60))
        duration_mins = str(int(duration_mins % 60)).zfill(2)
        request_url = "http://{}/run/{}?timeout={}h{}m".format(
            self.host_server_ip, script_name, duration_hours, duration_mins
        ) + self.constants_to_url_params(constants)

        print('Script Scheduler invoking script: ', request_url)
        requests.get(request_url)
        script_loaded = await_script_load(script_name)
        if script_loaded:
            await_script_completion(script_name)

    def parse_constant_def(self, script_sequence_def):
        pass

    def parse_script_sequence_def(self, script_sequence_def):
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

    def parse_and_run_script_sequence_def(self, script_sequence_def, timeout):
        print('def ', script_sequence_def)
        main_sequence,sequences = self.parse_script_sequence_def(script_sequence_def)
        print(main_sequence, sequences)
        timeout = self.str_timeout_to_datetime_timeout(timeout)
        if 'onInit' in sequences:
            self.run_script_sequence(sequences['onInit'], sequences, timeout)
        print('1')
        self.run_script_sequence(main_sequence, sequences, timeout)
        if 'onDestroy' in sequences:
            self.run_script_sequence(sequences['onDestroy'], sequences, timeout + datetime.timedelta(minutes=15))

    def run(self):
        print("Starting script scheduling service")
        service,calendar_id = self.initialize_service()
        running_scripts = {}
        print("Completed script scheduler setup, entering scheduler loop")
        while True:
            self.check_and_execute_active_tasks(service, calendar_id, running_scripts)
            time.sleep(60)




if __name__ == '__main__':

    script_scheduler = ScriptScheduler(sys.argv[1] + ":" + sys.argv[2])
    script_scheduler.run()