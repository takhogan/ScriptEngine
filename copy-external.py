import os
import shutil
from pathlib import Path

def copy_py_files():
    # Source directories
    scheduler_dir = Path('../ScriptScheduler')
    utils_dir = scheduler_dir / 'utils'
    
    # Destination directories
    dest_dir = Path('./external')
    dest_utils_dir = dest_dir / 'utils'
    
    # Create directories
    dest_dir.mkdir(exist_ok=True)
    dest_utils_dir.mkdir(exist_ok=True)
    
    # Copy files from ScriptScheduler root
    for py_file in scheduler_dir.glob('*.py'):
        shutil.copy2(py_file, dest_dir)
        print(f'Copied {py_file} to {dest_dir}')
    
    # Copy files from utils directory
    for py_file in utils_dir.glob('*.py'):
        shutil.copy2(py_file, dest_utils_dir)
        print(f'Copied {py_file} to {dest_utils_dir}')

if __name__ == '__main__':
    copy_py_files()