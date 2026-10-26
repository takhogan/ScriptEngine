import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from ScriptEngine.common.logging.script_action_log import ScriptActionLog
from ScriptEngine.common.logging.script_logger import ScriptLogger, thread_local_storage


@pytest.fixture
def run_folder(tmp_path):
    folder = tmp_path / 'logs' / '00001-test-run'
    folder.mkdir(parents=True)
    return str(folder) + '/'


@pytest.fixture
def configure_action(run_folder, monkeypatch):
    # The shared writer thread writes queued log lines to the singleton's file.
    monkeypatch.setattr(ScriptLogger(), 'log_file_path', run_folder + 'global-stdout.txt')
    logger = ScriptLogger().copy()
    logger.set_log_to_stdout(False)
    logger.set_log_file_path(run_folder + 'stdout.txt')

    def configure(level, action_name, counter):
        header = '{:05}-{}-{}'.format(counter, action_name, counter)
        logger.set_log_level(level)
        logger.set_log_folder(run_folder)
        logger.set_log_header(header)
        logger.set_log_path_prefix(run_folder + header + '-')
        action_log = ScriptActionLog(
            {'actionName': action_name, 'actionGroup': counter, 'actionData': {'targetSystem': 'desktop', 'detectActionType': 'floatingObject'}},
            run_folder, header, counter
        )
        logger.set_action_log(action_log)
        thread_local_storage.script_logger = logger
        return run_folder + header + '-'

    configure.logger = logger
    yield configure
    if hasattr(thread_local_storage, 'script_logger'):
        del thread_local_storage.script_logger
