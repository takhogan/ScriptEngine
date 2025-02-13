import subprocess
import sys
import os
import platform
from datetime import datetime, timedelta
from typing import List, Optional
import uuid
import argparse

def run_script_manager(
    script_name: str,
    start_time_str: Optional[str] = None,
    end_time_str: Optional[str] = None,
    log_level: str = "info",
    script_id: Optional[str] = None,
    device_details: str = "",
    system_script: bool = False,
    server_attached: bool = False,
    args: List[str] = None
) -> subprocess.Popen:
    """
    Launch the script manager with the specified parameters
    
    Args:
        script_name: Name of the script to run
        start_time_str: Start time in format 'YYYY-MM-DD HH:MM:SS'
        end_time_str: End time in format 'YYYY-MM-DD HH:MM:SS' 
        log_level: Logging level (default: "info")
        script_id: Unique identifier for the script run (UUID string)
        device_details: Device configuration details
        system_script: Whether this is a system script
        server_attached: Whether the script is being run with a server attached
        args: Additional arguments to pass to the script
    """
    # Generate UUID if not provided
    if script_id is None:
        script_id = str(uuid.uuid4())

    # Determine python executable path based on platform
    if platform.system() == "Windows":
        python_cmd = os.path.normpath("../ScriptEngine/venv/Scripts/python")
        script_path = os.path.normpath("../ScriptEngine/ScriptEngine/script_manager.py")
    else:
        python_cmd = "../ScriptEngine/venv/bin/python3"
        script_path = "../ScriptEngine/ScriptEngine/script_manager.py"

    # Set default times if not provided
    if not start_time_str:
        start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not end_time_str:
        end_time = datetime.now() + timedelta(minutes=30)
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

    # Build command arguments
    cmd_args = [
        python_cmd,
        script_path,
        script_name,
        start_time_str,
        end_time_str,
        log_level,
        script_id,
        device_details,
        str(system_script).lower(),
        str(server_attached).lower()
    ]

    # Add additional arguments if provided
    if args:
        cmd_args.extend(args)

    # Launch the process
    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy()
    )
    
    return process

def execute_and_monitor_script(
    script_name: str,
    log_level: str = "info",
    device_details: str = "",
    system_script: bool = False,
    server_attached: bool = False,
    **kwargs
) -> int:
    """
    Execute a script and monitor its output in real-time
    
    Args:
        script_name: Name of the script to run
        log_level: Logging level (default: "info")
        device_details: Device configuration details
        system_script: Whether this is a system script
        server_attached: Whether the script is being run with a server attached
        **kwargs: Additional keyword arguments to pass to run_script_manager
    
    Returns:
        int: Return code from the process
    """
    process = run_script_manager(
        script_name=script_name,
        log_level=log_level,
        device_details=device_details,
        system_script=system_script,
        server_attached=server_attached,
        **kwargs
    )
    
    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    # Get the return code
    return_code = process.poll()
    print(f"Process completed with return code: {return_code}")
    return return_code

if __name__ == "__main__":
    # Example usage
    execute_and_monitor_script("example_script")