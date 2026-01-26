import os
import sys
import json
import threading
from typing import Callable, Optional, Union, TextIO
import queue
import traceback

from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()
if sys.platform == "win32":
    import win32pipe  # pyright: ignore[reportMissingModuleSource]
    import win32file  # pyright: ignore[reportMissingModuleSource]
else:
    import fcntl
    import stat

class NamedPipeAdapter:
    def __init__(self, input_pipe_name: str, output_pipe_name: str, message_handler: Callable[[str], str]):
        """
        Initialize the named pipe adapter.
        
        Args:
            input_pipe_name: Name of the pipe to receive messages from
            output_pipe_name: Name of the pipe to send responses to
            message_handler: Callback function to process received messages
        """
        self.input_pipe_name = input_pipe_name
        self.output_pipe_name = output_pipe_name
        self.message_handler = message_handler
        self.running = False
        self.message_queue = queue.Queue()
        
    def _create_pipe(self, pipe_name: str, is_input: bool) -> Union[int, TextIO]:
        """Create a named pipe in a cross-platform way."""
        if sys.platform == "win32":
            pipe_handle = win32pipe.CreateNamedPipe(
                f"\\\\.\\pipe\\{pipe_name}",
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                1, 65536, 65536, 0, None
            )
            return pipe_handle
        else:
            if not os.path.exists(pipe_name):
                os.mkfifo(pipe_name, mode=0o666)
            return open(pipe_name, 'r' if is_input else 'w')

    def _read_from_pipe(self, pipe_handle) -> Optional[str]:
        """Read data from the pipe in a cross-platform way."""
        try:
            if sys.platform == "win32":
                win32pipe.ConnectNamedPipe(pipe_handle, None)
                result, data = win32file.ReadFile(pipe_handle, 65536)
                return data.decode('utf-8')
            else:
                return pipe_handle.readline().strip()
        except Exception as e:
            traceback.print_exc()
            return None

    def _write_to_pipe(self, pipe_handle, message: str) -> None:
        """Write data to the pipe in a cross-platform way."""
        try:
            if sys.platform == "win32":
                win32file.WriteFile(pipe_handle, message.encode('utf-8'))
                win32pipe.DisconnectNamedPipe(pipe_handle)
            else:
                pipe_handle.write(message + '\n')
                pipe_handle.flush()
        except Exception as e:
            traceback.print_exc()

    def _process_messages(self) -> None:
        """Process messages from the queue and send responses."""
        output_pipe = self._create_pipe(self.output_pipe_name, False)
        
        while self.running:
            try:
                request_id, message = self.message_queue.get(timeout=1)
                response = self.message_handler(message)
                formatted_response = f"<{request_id}>{response}</{request_id}>"
                self._write_to_pipe(output_pipe, formatted_response)
            except queue.Empty:
                continue
            except Exception as e:
                traceback.print_exc()

        if sys.platform != "win32":
            output_pipe.close()

    def start(self) -> None:
        """Start the named pipe adapter."""
        self.running = True
        
        # Start the message processing thread
        process_thread = threading.Thread(target=self._process_messages)
        process_thread.daemon = True
        process_thread.start()
        
        # Main loop to read from input pipe
        input_pipe = self._create_pipe(self.input_pipe_name, True)
        
        while self.running:
            try:
                data = self._read_from_pipe(input_pipe)
                if data:
                    try:
                        parsed_data = json.loads(data)
                        request_id = parsed_data.get('requestId')
                        message = parsed_data.get('message')
                        if request_id and message:
                            self.message_queue.put((request_id, message))
                    except json.JSONDecodeError:
                        print(f"Invalid JSON received: {data}", file=sys.stderr)
                        traceback.print_exc()
            except Exception as e:
                print(f"Error in main loop: {e}", file=sys.stderr)
                traceback.print_exc()
                break

        if sys.platform != "win32":
            input_pipe.close()

    def stop(self) -> None:
        """Stop the named pipe adapter."""
        self.running = False
