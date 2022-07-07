import PyInstaller.__main__

PyInstaller.__main__.run([
    # 'script_manager.py'
    'extra/adb_screen_recorder.py',
    '--onefile'
])