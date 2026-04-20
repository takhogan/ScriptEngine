import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ScriptEngine.script_action_executor import ScriptActionExecutor
from ScriptEngine.system_script_action_executor import SystemScriptActionExecutor
from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod
import ScriptEngine.system_script_action_executor as ssae_mod


class FakeActionLog:
    def __init__(self):
        self.summary = None

    def set_summary(self, summary):
        self.summary = summary

    def add_post_file(self, *args, **kwargs):
        return None

    def append_post_file(self, *args, **kwargs):
        return None

    def add_pre_file(self, *args, **kwargs):
        return None

    def add_supporting_file(self, *args, **kwargs):
        return None

    def append_supporting_file(self, *args, **kwargs):
        return None

    def add_supporting_file_reference(self, *args, **kwargs):
        return None

    def set_pre_file(self, *args, **kwargs):
        return None

    def set_post_file(self, *args, **kwargs):
        return None


class FakeLogger:
    def __init__(self):
        self.action_log = FakeActionLog()

    def log(self, *args, **kwargs):
        return None

    def copy(self):
        return self

    def get_action_log(self):
        return self.action_log

    def get_log_path_prefix(self):
        return "/tmp/test-log"


class FakeIOExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


class FakeDeviceController:
    def __init__(self):
        self.actions = {}
        self.attrs = {"width": 300, "height": 200, "xmax": 1, "ymax": 1}

    def ensure_device_initialized(self, target):
        return None

    def get_device_attribute(self, target, attr):
        return self.attrs[attr]

    def get_device_action(self, target, action_name):
        return self.actions[action_name]


@pytest.fixture
def device_executor(monkeypatch):
    logger = FakeLogger()
    monkeypatch.setattr(sae_mod, "script_logger", logger)
    io = FakeIOExecutor()
    dc = FakeDeviceController()
    executor = ScriptActionExecutor(
        device_controller=dc,
        io_executor=io,
        props={"scriptMode": "test", "script_name": "script", "dir_path": "/tmp"},
        screen_plan_server_attached=False,
    )
    return executor, dc, io, logger


@pytest.fixture
def system_executor(monkeypatch):
    logger = FakeLogger()
    monkeypatch.setattr(ssae_mod, "script_logger", logger)
    io = FakeIOExecutor()
    executor = SystemScriptActionExecutor(
        base_script_name="script",
        props={"dir_path": "/tmp"},
        io_executor=io,
        screen_plan_server_attached=False,
    )
    return executor, io, logger


@pytest.fixture
def base_context():
    return {"mouse_down": False, "last_mouse_position": (0, 0), "script_counter": 1, "script_timer": 0}


@pytest.fixture
def empty_state():
    return {}


@pytest.fixture
def run_queue():
    return []


__all__ = ["ScriptExecutionState"]
