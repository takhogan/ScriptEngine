"""ADBDeviceManager.get_device_name_to_emulator_name_mapping against a fake adb.

The mapping is how an Android emulator (avd) that is already running is
found: `adb devices` lists `emulator-5554`, and `adb -s emulator-5554 emu avd
name` names its AVD. Its call passed stdout and stderr to safe_subprocess_run,
which captures output itself, so subprocess.run refused it and configuring a
running AVD failed: a stopDevice run on one ended ERROR (2026-11-04).
"""

import os
import stat
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ScriptEngine.common import script_engine_utils
from ScriptEngine.managers.adb_device_manager import ADBDeviceManager


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """The shared ScriptLogger needs a file, or its writer thread prints a
    traceback after the run (see test_ios_device_manager.py)."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('emulator-name-logs') / 'test.txt'))
    return logger


def fake_adb(tmp_path, name_exit=0):
    """An adb that lists two emulators and a network device, and names the
    emulators as the emulator console does (CRLF, then OK)."""
    adb = tmp_path / 'adb'
    adb.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = devices ]; then\n'
        '  printf "List of devices attached\\nemulator-5554\\tdevice\\nemulator-5556\\tdevice\\n10.0.0.20:5555\\tdevice\\n\\n"\n'
        '  exit 0\n'
        'fi\n'
        f'if [ "$3 $4 $5" = "emu avd name" ]; then\n'
        f'  [ {name_exit} -ne 0 ] && {{ echo "error: no emulator" >&2; exit {name_exit}; }}\n'
        '  case "$2" in\n'
        '    emulator-5554) printf "Small_Phone_API_34\\r\\nOK\\r\\n" ;;\n'
        '    emulator-5556) printf "Pixel_7_API_35\\r\\nOK\\r\\n" ;;\n'
        '  esac\n'
        '  exit 0\n'
        'fi\n'
        'exit 1\n'
    )
    adb.chmod(adb.stat().st_mode | stat.S_IXUSR)
    return str(adb)


def manager_with(adb_path):
    manager = ADBDeviceManager.__new__(ADBDeviceManager)
    manager.adb_path = adb_path
    return manager


def test_each_running_emulator_is_found_by_its_avd_name(tmp_path):
    mapping = manager_with(fake_adb(tmp_path)).get_device_name_to_emulator_name_mapping()
    assert mapping == {'Small_Phone_API_34': 'emulator-5554', 'Pixel_7_API_35': 'emulator-5556'}


def test_an_emulator_that_cannot_be_named_is_left_out(tmp_path):
    mapping = manager_with(fake_adb(tmp_path, name_exit=1)).get_device_name_to_emulator_name_mapping()
    assert mapping == {}


def test_a_command_that_times_out_once_answers_the_retry(tmp_path, monkeypatch):
    """The retry after a timeout used to drop its result, so the caller got None."""
    import subprocess

    calls = []
    real_run = subprocess.run

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(args, kwargs.get('timeout'))
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', run)
    result = script_engine_utils.safe_subprocess_run([fake_adb(tmp_path), 'devices'])
    assert result is not None and result.returncode == 0
    assert b'emulator-5554' in result.stdout
    assert len(calls) == 2
