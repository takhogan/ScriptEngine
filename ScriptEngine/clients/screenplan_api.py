from typing import Dict, Optional, Literal, List, Tuple
from dataclasses import dataclass, field
import requests
from ScriptEngine.common.logging.script_logger import ScriptLogger
import json
from ScriptEngine.common.constants.script_engine_constants import *
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os


script_logger = ScriptLogger()

@dataclass
class ScreenPlanAPIRequest:
    request_id: Optional[str]
    method: Literal['GET', 'POST']
    request_type: str
    path: str
    payload: Dict
    files: Optional[List[Tuple[str, Tuple[str, bytes, str]]]] = field(default=None)

class ScreenPlanAPI:
    def __init__(self):
        self.server_token = None
        self.base_url = "https://localhost:3849/api"
        self.get_server_token()

    def get_server_token(self):
        try:
            # Define handler that watches for both creation and modification
            class TokenFileHandler(FileSystemEventHandler):
                def __init__(self, callback, file_path):
                    self.callback = callback
                    self.file_path = file_path
                
                def on_created(self, event):
                    if event.src_path == self.file_path:
                        self.callback()
                        
                def on_modified(self, event):
                    if event.src_path == self.file_path:
                        self.callback()

            # If file doesn't exist, wait for creation
            if not os.path.exists(SERVER_AUTH_HASH_PATH):
                observer = Observer()
                event_handler = TokenFileHandler(lambda: observer.stop(), SERVER_AUTH_HASH_PATH)
                observer.schedule(event_handler, path=os.path.dirname(SERVER_AUTH_HASH_PATH), recursive=False)
                observer.start()
                observer.join()

            # Read current token
            with open(SERVER_AUTH_HASH_PATH, 'r') as server_auth_file:
                auth_json = json.load(server_auth_file)
                new_token = auth_json['server_auth_hash']
                
                # If token is the same, wait for file changes
                if self.server_token == new_token:
                    observer = Observer()
                    event_handler = TokenFileHandler(lambda: observer.stop(), SERVER_AUTH_HASH_PATH)
                    observer.schedule(event_handler, path=os.path.dirname(SERVER_AUTH_HASH_PATH), recursive=False)
                    observer.start()
                    observer.join()
                    
                    # Re-read the token after file change
                    with open(SERVER_AUTH_HASH_PATH, 'r') as server_auth_file:
                        auth_json = json.load(server_auth_file)
                        new_token = auth_json['server_auth_hash']
                
                self.server_token = new_token
                return True
        except Exception as e:
            script_logger.log('Warning: error while getting server token')
            script_logger.log(e)
            return False

    def send_request(self, request: ScreenPlanAPIRequest, retry: bool = True) -> Optional[Dict]:
        url = f"{self.base_url}/{request.path.lstrip('/')}"
        script_logger.log(f'sending {request.method} request to {url}')
        
        headers = {'Authorization': f'Bearer {self.server_token}'}
        
        try:
            if request.method == 'POST':
                if request.files:
                    # Use multipart/form-data when files are present
                    # Send JSON payload as a form field
                    script_logger.log(f'sending files:', len(request.files), request.payload)
                    
                    form_data = {'payload': json.dumps(request.payload)}
                    response = requests.post(
                        url,
                        data=form_data,
                        files=request.files,
                        headers=headers,
                        verify=VERIFY_PATH
                    )
                else:
                    # Use JSON when no files
                    response = requests.post(
                        url,
                        json=request.payload,
                        headers=headers,
                        verify=VERIFY_PATH
                    )
            else:  # GET
                response = requests.get(
                    url,
                    headers=headers,
                    verify=VERIFY_PATH
                )

            if response.status_code == 403 and retry:
                self.get_server_token()
                return self.send_request(request, retry=False)  # Retry once with new token
            
            if response.status_code in (200, 201):
                try:
                    return response.json()
                except:
                    return {'data': response.text}
            else:
                script_logger.log(f'Request failed with status code {response.status_code}: {response.text}')
                return None
            
        except Exception as e:
            script_logger.log(f'Request failed: {e}')
            return None
