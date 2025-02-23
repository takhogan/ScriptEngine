import subprocess
import sys
import os
import signal
from typing import Optional

class SudoClient:
    def __init__(self):
        self.process = None
        self.pid = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()

    def run_as_root(self, command: str) -> Optional[int]:
        """
        Runs a command with elevated privileges (root/admin) and returns the process ID.
        
        Args:
            command: The command to run with elevated privileges
            
        Returns:
            The process ID of the launched command, or None if the launch failed
        """
        try:
            if sys.platform == "win32":
                # On Windows, use 'powershell Start-Process with -Verb RunAs for GUI prompt
                self.process = subprocess.Popen(
                    ['powershell.exe', 'Start-Process', '-Verb', 'RunAs', '-PassThru', '-Wait:$false', command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            elif sys.platform == "darwin":
                # On macOS, use osascript to show GUI prompt
                self.process = subprocess.Popen(
                    ['osascript', '-e', f'do shell script "{command}" with administrator privileges'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
            else:
                # On Linux, use pkexec for GUI prompt
                self.process = subprocess.Popen(
                    ['pkexec'] + command.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
            
            self.pid = self.process.pid
            print(f"Process started with PID: {self.pid}")
            return self.pid
            
        except Exception as e:
            print(f"Error running command with elevated privileges: {e}")
            return None

    def terminate(self):
        """
        Terminates the running process if it exists.
        """
        if self.process and self.pid:
            try:
                if sys.platform == "win32":
                    # On Windows, use taskkill to forcefully terminate the process tree
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.pid)], 
                                check=False, capture_output=True)
                else:
                    # On Unix-like systems, send SIGTERM
                    os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            except Exception as e:
                print(f"Error terminating process: {e}")
            finally:
                self.process = None
                self.pid = None
