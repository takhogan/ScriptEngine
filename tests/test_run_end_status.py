import asyncio
import datetime
import logging
import threading

import pytest
from dateutil import tz

import ScriptEngine.script_executor as script_executor_mod
from ScriptEngine.common.enums import ScriptExecutionState, ScriptExecutionStatusDetail
from ScriptEngine.custom_thread_pool import CustomThreadPool
from ScriptEngine.script_executor import ScriptExecutor

# A run that reaches its end time, or that the controller cancels, ends with
# soft_shutdown cancelling the io tasks still queued. On DESKTOP-OJMDROM
# (2026-10-31, Windows_DoHourlyTasksForAccount) each cancelled task's callback
# printed a CancelledError traceback to stderr, and the controller marked the
# run ERROR because of it.


class RecordingActionLog:
    def __init__(self):
        self.statuses = []

    def set_status(self, status):
        self.statuses.append(status)

    def set_script_log_folder(self, path):
        return None

    def set_post_file(self, *args, **kwargs):
        return None


class FakeLogger:
    def __init__(self):
        self.action_log = RecordingActionLog()

    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return self.action_log

    def set_action_log(self, action_log):
        self.action_log = action_log

    def set_log_header(self, *args):
        return None

    def get_log_header(self):
        return ''

    def get_log_folder(self):
        return ''

    def set_log_path_prefix(self, *args):
        return None


def test_cancelled_io_tasks_print_nothing_at_shutdown(caplog):
    pool = CustomThreadPool(max_workers=1)
    release = threading.Event()
    pool.submit(release.wait)
    queued = [pool.submit(lambda: None) for _ in range(3)]

    with caplog.at_level(logging.DEBUG):
        asyncio.run(pool.soft_shutdown(FakeLogger(), timeout=0.2))
        release.set()

    assert all(future.cancelled() for future in queued)
    assert not [record for record in caplog.records if 'exception calling callback' in record.getMessage()]
    assert not [record for record in caplog.records if record.exc_info and record.exc_info[0] is not None]


def test_a_task_that_raises_is_still_logged(caplog):
    pool = CustomThreadPool(max_workers=1)

    def fail():
        raise ValueError('disk full')

    with caplog.at_level(logging.ERROR):
        future = pool.submit(fail)
        pool.shutdown(wait=True)

    assert isinstance(future.exception(), ValueError)
    assert any('io_executor task failed' in record.getMessage() for record in caplog.records)


class ChildScript(ScriptExecutor):
    """The child a scriptReference starts, down to what run() and check_if_done
    read. Its actions do nothing, so run() stops at check_if_done."""

    def __init__(self, script, include_scripts, timeout, base_script_name, base_start_time_str, script_id, *args,
                 context=None, screen_plan_server_attached=False, **kwargs):
        self.props = {'script_name': script['name']}
        self.timeout = timeout
        self.base_script_name = base_script_name
        self.base_start_time_str = base_start_time_str
        self.script_id = script_id
        self.screen_plan_server_attached = screen_plan_server_attached
        self.context = dict(context, script_counter=1, script_timer=None, action_attempts=[0], success_states=None)
        self.actions = [{'actionGroup': 1}]
        self.run_queue = []
        self.status = ScriptExecutionState.STARTING
        self.status_detail = None

    def execute_actions(self):
        return None

    def set_parent_action_log(self, action_log):
        return None

    def create_log_folders(self, **kwargs):
        return ''

    def parse_inputs(self, state):
        return None

    def set_log_paths(self):
        return None

    def parse_outputs(self, state, path):
        return None


def build_parent(monkeypatch, timeout, running_scripts=None):
    logger = FakeLogger()
    monkeypatch.setattr(script_executor_mod, 'script_logger', logger)
    monkeypatch.setattr(script_executor_mod, 'raise_if_low_disk', lambda: None)
    monkeypatch.setattr(script_executor_mod, 'get_running_scripts', lambda: running_scripts or [])
    parent = ScriptExecutor.__new__(ScriptExecutor)
    parent.props = {'script_name': 'Windows_DoHourlyTasksForAccount', 'timeout': timeout}
    parent.include_scripts = {'BlueStacks_ExampleGame_CityView_DoEastTasks': {'name': 'BlueStacks_ExampleGame_CityView_DoEastTasks'}}
    parent.context = {
        'script_attributes': {},
        'script_counter': 1,
        'script_timer': None,
        'skip_input_parsing': None,
        'script_memory_mode': 'high',
    }
    parent.state = {}
    parent.run_queue = []
    parent.status_detail = None
    parent.base_script_name = 'Windows_DoHourlyTasksForAccount'
    parent.base_start_time_str = '2026-10-31 21:02:23'
    parent.script_id = 'f8010dae-6d5d-4e05-a330-2fce59fdb62c'
    parent.device_controller = parent.engine_manager = parent.io_executor = None
    parent.script_action_executor = parent.process_executor = None
    parent.call_stack = []
    parent.log_folder = ''
    parent.screen_plan_server_attached = running_scripts is not None
    parent.workspace = 'Default'
    parent.system_script = False
    parent.set_log_paths = lambda: None
    monkeypatch.setattr(script_executor_mod, 'ScriptExecutor', ChildScript)
    return parent, logger


def script_reference(run_mode):
    return {
        'actionName': 'scriptReference',
        'actionGroup': 22,
        'actionData': {
            'targetSystem': 'none',
            'scriptName': 'BlueStacks_ExampleGame_CityView_DoEastTasks',
            'runMode': run_mode,
            'branchingBehavior': 'firstMatch',
            'scriptAttributes': {},
            'scriptMaxActionAttempts': '50',
        },
    }


def utc_in(seconds):
    return datetime.datetime.now(datetime.timezone.utc).astimezone(tz.tzutc()) + datetime.timedelta(seconds=seconds)


@pytest.mark.parametrize('run_mode', ['run', 'runOne', 'runToFailure'])
def test_script_stopped_by_its_end_time_is_timed_out(monkeypatch, run_mode):
    parent, logger = build_parent(monkeypatch, timeout=utc_in(-1))

    _, status, _, _, _, _ = parent.handle_action(script_reference(run_mode))

    assert logger.action_log.statuses == ['TIMED_OUT']
    assert status == ScriptExecutionState.FAILURE


def test_script_the_controller_cancelled_is_cancelled(monkeypatch):
    other_run = {
        'script_id': 'another-run',
        'start_time_str': '2026-10-31 21:40:00',
        'script_name': 'BlueStacks_ExampleGame_Attack140Monsters',
        'parallel': False,
    }
    parent, logger = build_parent(monkeypatch, timeout=utc_in(600), running_scripts=[other_run])

    parent.handle_action(script_reference('run'))

    assert logger.action_log.statuses == ['CANCELLED']


def test_script_out_of_attempts_is_still_a_failure(monkeypatch):
    parent, logger = build_parent(monkeypatch, timeout=utc_in(600))
    monkeypatch.setattr(ChildScript, 'execute_actions', lambda self: self.context.__setitem__('action_attempts', [51]))

    parent.handle_action(script_reference('run'))

    assert logger.action_log.statuses == ['FAILURE']


def test_script_that_finished_a_branch_before_its_end_time_is_a_success(monkeypatch):
    parent, logger = build_parent(monkeypatch, timeout=utc_in(-1))

    def finish_branch(self):
        self.status = ScriptExecutionState.FINISHED_BRANCH

    monkeypatch.setattr(ChildScript, 'execute_actions', finish_branch)

    _, status, _, _, _, _ = parent.handle_action(script_reference('run'))

    assert status == ScriptExecutionState.SUCCESS
    assert logger.action_log.statuses == ['SUCCESS']


def test_status_detail_values_are_the_contract_strings():
    assert ScriptExecutionStatusDetail.TIMED_OUT.name == 'TIMED_OUT'
    assert ScriptExecutionStatusDetail.CANCELLED.name == 'CANCELLED'


# A child stopped by the run's end time can stop before the action that sets
# one of its outputs. On DESKTOP-OJMDROM (2026-11-02, Windows_DoHourlyTasksForAccount)
# BlueStacks_ExampleGame_LandView_CountFreeMarches was stopped just before it assigned
# N_FREE_MARCHES, and reading that output raised a NameError that ended the run
# as ERROR instead of TIMED_OUT.


def child_with_outputs(monkeypatch, status, state):
    import ScriptEngine.common.script_engine_utils as script_engine_utils_mod
    logger = FakeLogger()
    monkeypatch.setattr(script_executor_mod, 'script_logger', logger)
    monkeypatch.setattr(script_engine_utils_mod, 'script_logger', logger)
    child = ScriptExecutor.__new__(ScriptExecutor)
    child.props = {'script_name': 'BlueStacks_ExampleGame_LandView_CountFreeMarches'}
    child.outputs = [
        ['N_FREE_MARCHES', 'N_FREE_MARCHES', False],
        ['SHOW_MORE_MARCHES_COMPLETED', 'SHOW_MORE_MARCHES_COMPLETED', False],
    ]
    child.state = state
    child.status = status
    return child


def test_output_a_failed_child_never_set_is_none(monkeypatch, tmp_path):
    child = child_with_outputs(
        monkeypatch, ScriptExecutionState.FINISHED_FAILURE, {'SHOW_MORE_MARCHES_COMPLETED': True}
    )
    parent_state = {}

    child.parse_outputs(parent_state, str(tmp_path / 'outputs.txt'))

    assert parent_state == {'N_FREE_MARCHES': None, 'SHOW_MORE_MARCHES_COMPLETED': True}


def test_output_a_finished_child_never_set_still_raises(monkeypatch, tmp_path):
    child = child_with_outputs(
        monkeypatch, ScriptExecutionState.FINISHED, {'SHOW_MORE_MARCHES_COMPLETED': True}
    )

    with pytest.raises(NameError):
        child.parse_outputs({}, str(tmp_path / 'outputs.txt'))
