from typing import Dict
import argparse

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest

script_logger = ScriptLogger()

class MessagingHelper:
    def __init__(self):
        self.api = ScreenPlanAPI()

    def send_message(self, message_obj: Dict):
        request = ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='json',
            path='sendMessage',
            payload=message_obj
        )
        return self.api.send_request(request)

