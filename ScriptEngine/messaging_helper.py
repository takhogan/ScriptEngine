import sys

if __package__ is None or __package__ == '':
    from script_engine_constants import *
else:
    from .script_engine_constants import *


import json
import requests
from script_logger import ScriptLogger
script_logger = ScriptLogger()

class MessagingHelper:
    def __init__(self):
        pass

    def send_viber_message(self, message):
        with open(VIBER_CREDENTIALS_FILEPATH, 'r') as creds_file:
            creds = json.load(creds_file)
        script_logger.log(requests.post(url=VIBER_CONTROLLER_ENDPOINT_URL, json={
            'action': 'sendMessage',
            'payload': message
        }, headers={
            'SECRET': creds['SECRET']
        }).text)
        del creds


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'sendmessage':
        message = sys.argv[2]
        helper = MessagingHelper()
        helper.send_viber_message(message)
    else:
        script_logger.log("Usage: python messaging_helper.py sendmessage 'Your Message Here'")
