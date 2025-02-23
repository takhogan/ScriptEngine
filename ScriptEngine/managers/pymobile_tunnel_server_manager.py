import asyncio
import datetime
import os
import subprocess
from pymobiledevice3.remote.tunneld import Tunneld
from ScriptEngine.common.logging.script_logger import ScriptLogger

script_logger = ScriptLogger()
formatted_today = str(datetime.datetime.now()).replace(':', '-').replace('.', '-')

class PyMobileTunnelServer:
    def __init__(self):
        self.tunneld_server = None
        self.process = None
        self.setup_logging()
        
    def setup_logging(self):
        os.makedirs('./logs', exist_ok=True)
        script_logger.set_log_file_path('./logs/{}-pymobile-tunnel-server-main.txt'.format(formatted_today))
        script_logger.set_log_header('{}-pymobile-tunnel-server-main-'.format(formatted_today))
        script_logger.set_log_folder('./logs/')

    def start(self):
        script_logger.log("Starting PyMobile tunnel server...")
        try:
            # Initialize the Tunneld server
            self.tunneld_server = Tunneld()
            
            # Start the server and capture output
            self.process = subprocess.Popen(
                [self.tunneld_server.start()],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Log stdout and stderr
            while True:
                stdout_line = self.process.stdout.readline()
                stderr_line = self.process.stderr.readline()
                
                if stdout_line:
                    script_logger.log(f"TUNNEL SERVER STDOUT: {stdout_line.strip()}")
                if stderr_line:
                    script_logger.log(f"TUNNEL SERVER STDERR: {stderr_line.strip()}")
                    
                # Check if process has finished
                if self.process.poll() is not None:
                    break

        except Exception as e:
            script_logger.log(f"Error starting tunnel server: {str(e)}")
            raise

    def shutdown(self):
        if self.process:
            script_logger.log("Shutting down PyMobile tunnel server...")
            try:
                self.process.terminate()  # Send SIGTERM
                try:
                    # Wait for the process to terminate gracefully
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # If process doesn't terminate within 5 seconds, force kill it
                    script_logger.log("Force killing tunnel server process...")
                    self.process.kill()
                    self.process.wait()
                
                script_logger.log("PyMobile tunnel server shutdown complete")
            except Exception as e:
                script_logger.log(f"Error during shutdown: {str(e)}")
                raise
            finally:
                self.process = None
                self.tunneld_server = None

def main():
    server = PyMobileTunnelServer()
    server.start()

if __name__ == "__main__":
    main()
