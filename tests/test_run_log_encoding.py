import builtins

import ScriptEngine.script_executor as script_executor_mod
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.script_executor import ScriptExecutor

# imageToTextAction output seen on DESKTOP-C6GDVNF (2026-10-25): the OCR read a
# 'fi' ligature, which cp1252 has no byte for.
OCR_TEXT = 'Proﬁle'


def windows_default_open(file, mode='r', *args, **kwargs):
    # On Windows, open() without an encoding uses the ANSI code page.
    if 'b' not in mode and kwargs.get('encoding') is None:
        kwargs['encoding'] = 'cp1252'
    return builtins.open(file, mode, *args, **kwargs)


class FakeActionLog:
    def set_pre_file(self, *args, **kwargs):
        return None

    def set_post_file(self, *args, **kwargs):
        return None


class FakeLogger:
    def __init__(self):
        self.action_log = FakeActionLog()

    def log(self, *args, **kwargs):
        return None

    def get_action_log(self):
        return self.action_log


def build_executor(monkeypatch, tmp_path, state):
    monkeypatch.setattr(script_executor_mod, 'script_logger', FakeLogger())
    monkeypatch.setattr(script_executor_mod, 'open', windows_default_open, raising=False)
    executor = ScriptExecutor.__new__(ScriptExecutor)
    executor.props = {'script_name': 'BlueStacks_WAO_ReadAccountName'}
    executor.state = state
    executor.status = ScriptExecutionState.SUCCESS
    executor.log_folder = str(tmp_path) + '/'
    return executor


def test_outputs_log_keeps_ocr_text_on_a_cp1252_host(monkeypatch, tmp_path):
    executor = build_executor(monkeypatch, tmp_path, {'ocr_text': OCR_TEXT})
    executor.outputs = [['account_name', 'ocr_text', False]]
    output_state = {}

    executor.parse_outputs(output_state, str(tmp_path / 'outputs.txt'))

    assert output_state['account_name'] == OCR_TEXT
    assert OCR_TEXT in (tmp_path / 'outputs.txt').read_text(encoding='utf-8')


def test_inputs_log_keeps_ocr_text_on_a_cp1252_host(monkeypatch, tmp_path):
    executor = build_executor(monkeypatch, tmp_path, {})
    executor.inputs = [['account_name', 'None', True]]

    executor.parse_inputs({'account_name': OCR_TEXT})

    assert executor.state['account_name'] == OCR_TEXT
    assert OCR_TEXT in (tmp_path / 'inputs.txt').read_text(encoding='utf-8')
