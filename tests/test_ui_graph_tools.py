"""The UI mapper's host jobs as agent tools (ui_graph_tools.py): agent_tools
ui-graph-ingest, ui-graph-check and ui-graph-gc on a tiny data root.

The runs are written by the mapper's own test fixtures (its tests/fixtures.py),
so they are in the format its extractor reads. Skipped when no mapper checkout
is beside this engine checkout and SCREENPLAN_MAPPER_DIR names none.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from ScriptEngine import agent_tools, ui_graph_tools

MAPPER = Path(ui_graph_tools.mapper_checkout())
pytestmark = pytest.mark.skipif(not (MAPPER / 'ui_mapper').is_dir(), reason='no ScreenPlanUIMapper checkout at {}'.format(MAPPER))

RUN = '00004-Example-2027-01-14 10-00-00'


def _fixtures():
    spec = importlib.util.spec_from_file_location('ui_mapper_test_fixtures', MAPPER / 'tests' / 'fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def data_root(tmp_path):
    fixtures = _fixtures()
    for i in range(5):
        fixtures.write_run(str(tmp_path), '{:05d}-Example-2027-01-1{} 10-00-00'.format(i, i), fixtures.alternating(6),
                           seed=i, start=1.8e9 + 3600 * i)
    return tmp_path


def _call(tmp_path, tool, request):
    request_file = tmp_path / 'request.json'
    request_file.write_text(json.dumps(request))
    output = tmp_path / 'out.json'
    assert agent_tools.main([tool, '--request', str(request_file), '--output', str(output)]) == 0
    return json.loads(output.read_text())


def test_ingest_folds_a_run_in_and_writes_its_report(data_root, tmp_path):
    out = _call(tmp_path, 'ui-graph-ingest', {'runFolder': RUN, 'host': 'Mac-01', 'dataRoot': str(data_root)})
    assert out['app'] == 'example' and out['workspace'] == 'Default'
    # The app had no graph: it started from the other runs on disk.
    assert out['started'] == {'example': 4}
    assert out['verdict'].startswith('passed')
    assert os.path.exists(out['report'])
    assert os.path.exists(data_root / 'ui-graphs' / 'Default' / 'example' / 'live.json')
    again = _call(tmp_path, 'ui-graph-ingest', {'runFolder': RUN, 'host': 'Mac-01', 'dataRoot': str(data_root)})
    assert again['already'] is True


def test_check_folds_the_run_in_first_and_names_its_report(data_root, tmp_path):
    out = _call(tmp_path, 'ui-graph-check', {'runFolder': RUN, 'host': 'Mac-01', 'dataRoot': str(data_root)})
    assert out['app'] == 'example' and os.path.exists(out['report'])
    assert json.loads(Path(out['report']).read_text())['verdict'] == out['verdict']


def test_gc_forgets_the_reports_of_runs_that_are_gone(data_root, tmp_path):
    _call(tmp_path, 'ui-graph-ingest', {'runFolder': RUN, 'dataRoot': str(data_root)})
    shutil.rmtree(data_root / 'logs' / '00000-Example-2027-01-10 10-00-00')
    assert _call(tmp_path, 'ui-graph-gc', {'dataRoot': str(data_root)}) == {'deleted': 1}


def test_a_run_the_mapper_cannot_read_is_skipped_not_a_failure(data_root, tmp_path):
    empty = '00009-Empty-2027-01-19 10-00-00'
    (data_root / 'logs' / empty).mkdir()
    out = _call(tmp_path, 'ui-graph-ingest', {'runFolder': empty, 'dataRoot': str(data_root)})
    assert out['run'] == empty and out['skipped']
    assert _call(tmp_path, 'ui-graph-check', {'runFolder': empty, 'dataRoot': str(data_root)})['skipped']


def test_only_a_run_folder_name(data_root, tmp_path):
    for bad in ('../logs', 'logs/x', '', None, '.hidden'):
        out = _call(tmp_path, 'ui-graph-ingest', {'runFolder': bad, 'dataRoot': str(data_root)})
        assert out['error'] == 'invalid', bad


def test_without_a_mapper_the_tools_answer_no_mapper(tmp_path):
    # A child process, so ui_mapper is not already imported, with the mapper's
    # checkout pointed at an empty folder.
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'dataRoot': str(tmp_path)}))
    output = tmp_path / 'out.json'
    env = {**os.environ, 'SCREENPLAN_MAPPER_DIR': str(tmp_path / 'nothing-here'), 'PYTHONPATH': str(ENGINE_ROOT)}
    done = subprocess.run(
        [sys.executable, '-m', 'ScriptEngine.agent_tools', 'ui-graph-gc', '--request', str(request), '--output', str(output)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(output.read_text())
    assert out['error'] == 'no-mapper' and 'nothing-here' in out['message']
