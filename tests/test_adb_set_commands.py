"""set_commands reads the touch device from `adb shell getevent -p`, which it
stops after a few seconds. A getevent that never exits must not hold the run:
on 2026-11-22 one on a just-started BlueStacks instance held a run's first
detect for 37 minutes, because the reader thread was joined before getevent
was ended."""

import os
import stat
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ScriptEngine.managers.adb_device_manager import ADBDeviceManager

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='the fake adb is a shell script')

GETEVENT_OUTPUT = r'''add device 1: /dev/input/event2
  name:     "Power Button"
add device 2: /dev/input/event4
  name:     "BlueStacks Virtual Touch"
  events:
    KEY (0001): 014a
    ABS (0003): 0035  : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
add device 3: /dev/input/event5
  name:     "BlueStacks Virtual Keyboard"
'''


@pytest.fixture(autouse=True, scope='module')
def logger_writes_somewhere(tmp_path_factory):
    """The shared ScriptLogger needs a file, or its writer thread prints a
    traceback after the run (see test_ios_device_manager.py)."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger

    logger = ScriptLogger()
    logger.set_log_file_path(str(tmp_path_factory.mktemp('set-commands-logs') / 'test.txt'))
    return logger


def fake_adb(tmp_path, body):
    """An adb that prints getevent -p's output and then runs `body`."""
    output = tmp_path / 'getevent.txt'
    output.write_text(GETEVENT_OUTPUT)
    script = tmp_path / 'adb'
    script.write_text(f'#!/bin/sh\ncat "{output}"\n{body}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def manager_with(adb_path):
    manager = ADBDeviceManager.__new__(ADBDeviceManager)
    manager.adb_path = adb_path
    manager.full_ip = '127.0.0.1:5565'
    manager.stop_command_gather = False
    return manager


def test_getevent_that_exits_finds_the_touch_device(tmp_path):
    manager = manager_with(fake_adb(tmp_path, 'exit 0'))
    assert manager.set_commands(timeout=1) == '/dev/input/event4'
    assert manager.touch_has_btn_touch is True
    assert manager.touch_slot_protocol is False


def test_getevent_that_never_exits_is_ended_after_the_timeout(tmp_path):
    # exec: the shell becomes the sleep, so ending the process closes the pipe.
    manager = manager_with(fake_adb(tmp_path, 'exec sleep 30'))
    started = time.monotonic()
    device_path = manager.set_commands(timeout=1)
    elapsed = time.monotonic() - started
    assert device_path == '/dev/input/event4'
    assert elapsed < 5, f'set_commands waited {elapsed:.1f}s on a getevent that never exits'


def test_reader_left_behind_when_another_process_holds_the_pipe(tmp_path):
    # A background child keeps stdout open after adb itself is killed, so the
    # reader cannot reach end of file: set_commands still returns.
    manager = manager_with(fake_adb(tmp_path, 'sleep 30 &\nexec sleep 30'))
    started = time.monotonic()
    device_path = manager.set_commands(timeout=1, reader_join_timeout=1)
    elapsed = time.monotonic() - started
    assert device_path == '/dev/input/event4'
    assert elapsed < 6, f'set_commands waited {elapsed:.1f}s on a blocked reader'
