import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ScriptEngine.script_action_executor import ScriptActionExecutor
from ScriptEngine.system_script_action_executor import SystemScriptActionExecutor
from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.script_action_executor as sae_mod
import ScriptEngine.system_script_action_executor as ssae_mod
import ScriptEngine.helpers.image_to_text_action_helper as image_to_text_action_helper_mod
import ScriptEngine.helpers.match_merge_helper as match_merge_helper_mod


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
    LOG_LEVELS = {'error': 0, 'info': 1, 'debug': 2}

    def __init__(self):
        self.action_log = FakeActionLog()
        # Default to the most permissive level so all artifact paths execute
        # under test (mirrors the pre-log-level unconditional behavior).
        self.log_level = 'debug'

    def log(self, *args, **kwargs):
        return None

    def should_log(self, level='info'):
        return self.LOG_LEVELS.get(level, 1) <= self.LOG_LEVELS.get(self.log_level, 1)

    def get_log_level(self):
        return self.log_level

    def set_log_level(self, level):
        self.log_level = level

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
    monkeypatch.setattr(image_to_text_action_helper_mod, "script_logger", logger)
    monkeypatch.setattr(match_merge_helper_mod, "script_logger", logger)
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
