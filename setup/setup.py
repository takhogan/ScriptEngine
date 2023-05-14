import os
import subprocess

# List of requirement files
requirement_dirs = ['venv', 'venv_host_server', 'venv_scheduling_server']
requirement_files = list(map(lambda dir_name: 'setup/' + dir_name + '_requirements.txt', requirement_dirs))

# Create directories for virtual environments
base_dir = os.getcwd()  # Use the current working directory as the base directory
for requirement_dir in requirement_dirs:
    env_path = os.path.join(base_dir, requirement_dir)
    os.makedirs(env_path, exist_ok=True)


is_windows = (os.name == 'nt')
# Create virtual environments and activate them
for i, requirement_dir in enumerate(requirement_dirs):
    env_path = os.path.join(base_dir, requirement_dir)

    # Create virtual environment
    subprocess.run(['python', '-m', 'venv', env_path], check=True)

    # Activate virtual environment and install requirements

    activate_script = os.path.join(env_path, 'Scripts' if is_windows else 'bin', 'activate')
    activation_command = ['source'] if not is_windows else [] + [activate_script]
    pip_install_command = ['pip', 'install', '-r', requirement_files[i]]

    try:
        print(subprocess.run(f'{" ".join(activation_command)} && {" ".join(pip_install_command)} && deactivate', shell=True, check=True))
    except subprocess.CalledProcessError as e:
        print(f"Error installing requirements for {requirement_dir}: {e}")
