import sys
from typing import Dict

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
        self.server_token = None
        self.get_server_token()

    def get_server_token(self):
        try:
            with open(SERVER_AUTH_HASH_PATH, 'r') as server_auth_file:
                auth_json = json.load(server_auth_file)
                self.server_token = auth_json['server_auth_hash']
            return True
        except Exception as e:
            print('Warning: error while getting server token')
            print(e)
            return False

    def _send_message_request(self, message_obj : Dict):
        request_url = "https://localhost:3849/api/sendMessage"
        script_logger.log('sending request to ', request_url, 'with contents', message_obj)
        request_result = requests.post(
            request_url,
            json=message_obj,
            headers={
                'Authorization': 'Bearer {}'.format(self.server_token)
            },
            verify=VERIFY_PATH
        )
        return request_result

    def send_message(self, message_obj : Dict):
        request_result = self._send_message_request(message_obj)
        script_logger.log('printing response')
        script_logger.log('response', request_result.text)
        if int(request_result.status_code) == 403:
            self.get_server_token()
            request_result = self._send_message_request(message_obj)

        if int(request_result.status_code) == 403:
            return False
        else:
            return True





if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'sendmessage':
        message = sys.argv[2]
        helper = MessagingHelper()
        helper.send_viber_message(message)
    else:
        script_logger.log("Usage: python messaging_helper.py sendmessage 'Your Message Here'")
