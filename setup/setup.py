import os
import subprocess
import sys

from setup_tesseract import setup_tesseract

# Virtual environments to create, each paired with setup/<name>_requirements.txt
requirement_dirs = ['venv', 'venv_host_server', 'venv_scheduling_server']

# Resolve paths from this file's location so the script works from any directory
setup_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(setup_dir)

is_windows = (os.name == 'nt')

# Use the interpreter running this script to build the venvs
python_command = sys.executable
print(f'Using Python {sys.version.split()[0]} at {python_command}')

failed = []
for requirement_dir in requirement_dirs:
    env_path = os.path.join(base_dir, requirement_dir)
    requirement_file = os.path.join(setup_dir, requirement_dir + '_requirements.txt')

    print(f'\n=== {requirement_dir} ===')
    subprocess.run([python_command, '-m', 'venv', env_path], check=True)

    # Call the venv's own python directly instead of activating it in a shell
    env_python = os.path.join(env_path, 'Scripts' if is_windows else 'bin', 'python')
    subprocess.run([env_python, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)

    if not os.path.isfile(requirement_file):
        print(f'Warning: {requirement_file} not found, {requirement_dir} created without packages')
        continue

    try:
        subprocess.run([env_python, '-m', 'pip', 'install', '-r', requirement_file], check=True)
    except subprocess.CalledProcessError as e:
        print(f'Error installing requirements for {requirement_dir}: {e}')
        failed.append(requirement_dir)

    # tesserocr isn't installable from venv_requirements.txt on Windows, so the script venv gets it separately
    if requirement_dir == 'venv':
        try:
            setup_tesseract(env_python)
        except Exception as e:
            print(f'Error setting up tesseract for {requirement_dir}: {e}')
            failed.append(requirement_dir + ' (tesseract)')

if failed:
    print(f'\nSetup finished with errors in: {", ".join(failed)}')
    sys.exit(1)
print('\nSetup finished')
