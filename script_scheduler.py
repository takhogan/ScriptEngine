import datetime
import os.path
import time
import multiprocessing
import unicodedata

from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from script_manager import parse_and_run_script_sequence_def

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_NAME = 'ScriptScheduler'


def clean_description(description):
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


def create_calendar_if_not_exists(service):
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

def initialize_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
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
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            # if issues here: https://github.com/googleapis/google-auth-library-python-oauthlib/issues/69
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('calendar', 'v3', credentials=creds)

    try:

        calendar_id = create_calendar_if_not_exists(service)

    except HttpError as error:
        print('An error occurred: %s' % error)
        exit(0)


    return service,calendar_id

def check_and_execute_active_tasks(service, calendar_id, running_scripts):
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
        initialize_service()
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
            print(clean_description(event['description']))
            event_process = multiprocessing.Process(
                target=parse_and_run_script_sequence_def,
                args=(clean_description(event['description']), event['end']['dateTime'])
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

def run():
    service,calendar_id = initialize_service()
    running_scripts = {}

    while True:
        check_and_execute_active_tasks(service, calendar_id, running_scripts)
        time.sleep(60)




if __name__ == '__main__':
    run()