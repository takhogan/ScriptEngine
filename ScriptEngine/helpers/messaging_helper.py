from typing import Dict, TypedDict
import argparse
import base64
import cv2

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest

script_logger = ScriptLogger()

class MessagingHelper:
    class SendMessageRequest(TypedDict):
        action: str
        messagingChannelName: str
        messagingProvider: str
        messageType: str

    def __init__(self):
        self.api = ScreenPlanAPI()

    def send_message(self, message_obj: "MessagingHelper.SendMessageRequest", message_pre_data: Dict):
        
        if message_pre_data["type"] == "text":
            message_data = {
                "type": "text",
                "content": message_pre_data["content"]
            }
        elif message_pre_data["type"] == "image":
            if isinstance(message_pre_data["images"], list):
                image_list = message_pre_data["images"]
            else:
                image_list = [message_pre_data["images"]]
            images = []
            for index,image in enumerate(image_list):
                images.append({
                    "data" : base64.b64encode(cv2.imencode('.jpg', image["matched_area"])[1].tobytes()).decode('utf-8'),
                    "contentType": "image/jpeg",
                    "filename": f"image_{index}.jpg"
                })
            message_data = {
                "type": "image",
                "images": images
            }
        
        # type TextMessageData = {
        #     type: 'text';
        #     content: string;
        # };

        # type ImageMessageData = {
        #     type: 'image';
        #     images: string[];
        #     caption?: string; // Optional caption/text to accompany the image(s)
        # };

        # type MessageData = TextMessageData | HtmlMessageData | RichMessageData | ImageMessageData;

        message_obj["messageData"] = message_data
        request = ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='json',
            path='sendMessage',
            payload=message_obj
        )
        return self.api.send_request(request)

