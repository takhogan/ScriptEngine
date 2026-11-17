# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""The run's clock: the wall clock, or a virtual one on a simulated device.

The time a script can see goes through here: sleepStatement, the timer of
countToThresholdAction, timeAction, the delays between repeated clicks and
after a random-variable action, and the script's own timeout. On a real
device these are time.time() and time.sleep(). A simulated device
(managers/simulated_device_manager.py) makes the clock virtual: the time is
the wall clock plus an offset, a sleep adds to the offset instead of waiting,
and the device adds what a screenshot would have taken. Work the engine does
for real (a detect, OCR) still takes its real time, so a run on the sim keeps
the order of events it would have on the device, without the waiting
(UI_MAPPER.md §4, "Time").

Sleeps in parallel branches add up rather than overlap, so a simulated run
can be later on its clock than the device would be; a time a script computes
itself in a Python expression (datetime.datetime.now()) is the wall clock.
"""
import datetime as _datetime
import threading
import time as _time

_lock = threading.Lock()
_virtual = False
_offset = 0.0


def make_virtual():
    global _virtual
    _virtual = True


def is_virtual():
    return _virtual


def advance(seconds):
    """Moves a virtual clock forward; nothing on the wall clock."""
    global _offset
    if seconds and seconds > 0:
        with _lock:
            _offset += float(seconds)


def time():
    return _time.time() + _offset


def sleep(seconds):
    if _virtual:
        advance(seconds)
    elif seconds and seconds > 0:
        _time.sleep(seconds)


def now(tz=None):
    """datetime.datetime.now(tz) on this clock."""
    return _datetime.datetime.fromtimestamp(time(), tz)


def utcnow():
    """datetime.datetime.utcnow() on this clock: naive, in UTC."""
    return _datetime.datetime.fromtimestamp(time(), _datetime.timezone.utc).replace(tzinfo=None)


def reset():
    """Back to the wall clock (tests)."""
    global _virtual, _offset
    with _lock:
        _virtual = False
        _offset = 0.0
