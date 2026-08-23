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


def read_server_auth_hash(file_path):
    """Reads the controller's API token out of its auth hash file.

    `auth_hash` is accepted alongside `server_auth_hash` because controller
    builds before the key was unified wrote the former on the sign-in path; an
    install that has not rotated its token since then still has that file.
    """
    with open(file_path, 'r') as server_auth_file:
        auth_json = json.load(server_auth_file)
    token = auth_json.get('server_auth_hash') or auth_json.get('auth_hash')
    if not token:
        raise KeyError('no server_auth_hash in {}'.format(file_path))
    return token


# How long to wait for the controller to publish a token before giving up.
# The wait covers the rotation race — the controller rotates, our next request
# 403s, and the new token lands a moment later — not a controller that is down
# or out of sync with the file. Without a bound, the second case parks this
# thread until the next rotation, which may never come.
SERVER_TOKEN_WAIT_TIMEOUT_SECONDS = 30


class TokenFileHandler(FileSystemEventHandler):
    """Fires `callback` on any event touching `file_path`.

    The controller writes the file atomically (temp file + rename), so
    depending on the platform the change surfaces as a create, a modify or a
    move-into-place — watching only for modify would miss it.
    """

    def __init__(self, callback, file_path):
        self.callback = callback
        self.file_path = os.path.abspath(file_path)

    def on_any_event(self, event):
        paths = [getattr(event, 'src_path', None), getattr(event, 'dest_path', None)]
        for event_path in paths:
            if event_path and os.path.abspath(event_path) == self.file_path:
                self.callback()
                return


def wait_for_auth_hash_change(timeout_seconds=SERVER_TOKEN_WAIT_TIMEOUT_SECONDS):
    """Blocks until the token file is written, or `timeout_seconds` lapses.

    Returns True if the file changed. The observer is always torn down:
    join() with a timeout leaves the thread running, so a timed-out wait would
    otherwise leak one watchdog thread per attempt.
    """
    observer = Observer()
    handler = TokenFileHandler(lambda: observer.stop(), SERVER_AUTH_HASH_PATH)
    observer.schedule(
        handler,
        path=os.path.dirname(SERVER_AUTH_HASH_PATH) or '.',
        recursive=False
    )
    observer.start()
    observer.join(timeout_seconds)
    # The handler's only job is to stop the observer, so a dead thread means
    # the file changed and a live one means we ran out of time.
    if observer.is_alive():
        observer.stop()
        observer.join()
        return False
    return True


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
            # If file doesn't exist, wait for creation
            if not os.path.exists(SERVER_AUTH_HASH_PATH):
                if not wait_for_auth_hash_change():
                    script_logger.log(
                        'Timed out waiting for {} to be created'.format(SERVER_AUTH_HASH_PATH),
                        level='error'
                    )
                    return False

            # Read current token
            new_token = read_server_auth_hash(SERVER_AUTH_HASH_PATH)

            # If token is the same, wait for file changes
            if self.server_token == new_token:
                if wait_for_auth_hash_change():
                    # Re-read the token after file change
                    new_token = read_server_auth_hash(SERVER_AUTH_HASH_PATH)
                else:
                    # The controller is rejecting the same token the file
                    # holds. Hand the stale one back rather than blocking: the
                    # caller's request fails, which is recoverable, where a
                    # wait with no end is not.
                    script_logger.log(
                        'Timed out waiting for a new server token; keeping the current one',
                        level='error'
                    )

            self.server_token = new_token
            return True
        except Exception as e:
            script_logger.log('Warning: error while getting server token', level='error')
            script_logger.log(e, level='error')
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
                    script_logger.log(f'sending files:', len(request.files), request.payload, level='debug')
                    
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
                script_logger.log(f'Request failed with status code {response.status_code}: {response.text}', level='error')
                return None
            
        except Exception as e:
            script_logger.log(f'Request failed: {e}', level='error')
            return None
