import sys

# Personally, I don't understand this. I thought it should be the opposite...
if __package__ is None or __package__ == '':
    # Script is executed from the parent directory
    from script_engine_constants import *
else:
    # Script is executed from within the subdirectory
    from .script_engine_constants import *


import json
import requests

class MessagingHelper:
    def __init__(self):
        pass

    def send_viber_message(self, message):
        with open(VIBER_CREDENTIALS_FILEPATH, 'r') as creds_file:
            creds = json.load(creds_file)
        print(requests.post(url=VIBER_CONTROLLER_ENDPOINT_URL, json={
            'action': 'sendMessage',
            'payload': message
        }, headers={
            'SECRET': creds['SECRET']
            # 'Authorization' : 'Bearer ' + creds['AUTHORIZATION']
        }).text)
        del creds