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

"""The UI mapper's host jobs as agent tools (agent_tools ui-graph-*).

ScreenPlanUIMapper learns an app's screens from run logs and runs the run
check on each finished run (its repository's README; the controller's
UI_MAPPER.md, §4.1 and §5). Its code lives in its own repository. It runs
here, inside the engine's agent_tools, so a packaged controller needs no
executable of its own for it, and no signature of its own:

- from source, `ui_mapper` is imported from the mapper's checkout:
  $SCREENPLAN_MAPPER_DIR, else ScreenPlanUIMapper beside this engine checkout;
- in a frozen build, script_engine.spec bundles the same checkout's
  `ui_mapper` package into agent_tools, so the import finds it there.

Each tool takes `{"runFolder", "host", "dataRoot"}` (gc only `dataRoot`)
and answers the mapper job's summary, the line `ui_mapper ingest|check|gc`
prints last. A run the mapper does not read (a simulated one, a run with no
action log) is `{"run": ..., "skipped": reason}`. An engine built without the
mapper answers `{"error": "no-mapper", "message": ...}`.

Progress lines go to stderr, which the controller keeps the tail of.
"""

import os
import sys

MAPPER_DIR_ENV = 'SCREENPLAN_MAPPER_DIR'
MAPPER_REPO = 'ScreenPlanUIMapper'


class MapperMissing(Exception):
    pass


def mapper_checkout(env=None):
    """The mapper's source checkout: $SCREENPLAN_MAPPER_DIR, else
    ScreenPlanUIMapper beside this engine checkout (or worktree)."""
    env = os.environ if env is None else env
    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(env.get(MAPPER_DIR_ENV) or os.path.join(engine_root, '..', MAPPER_REPO))


def _import_mapper():
    """(jobs, extract, DataRoot) from ui_mapper, imported on the first call."""
    try:
        import ui_mapper  # noqa: F401  bundled in a frozen build, or already on the path
    except ImportError:
        checkout = mapper_checkout()
        if getattr(sys, 'frozen', False) or not os.path.isdir(os.path.join(checkout, 'ui_mapper')):
            where = 'this engine was built without it' if getattr(sys, 'frozen', False) \
                else 'no checkout at {} (set {})'.format(checkout, MAPPER_DIR_ENV)
            raise MapperMissing('the UI mapper is not available: ' + where)
        sys.path.insert(0, checkout)
    from ui_mapper import extract, jobs
    from ui_mapper.paths import DataRoot
    return jobs, extract, DataRoot


def _log(line):
    print(line, file=sys.stderr, flush=True)


def _run_folder(request):
    folder = request.get('runFolder')
    if not isinstance(folder, str) or not folder or folder != os.path.basename(folder) or folder.startswith('.'):
        raise ValueError('runFolder must be a run folder name')
    return folder


def _job(request, body, needs_run=True):
    try:
        jobs, extract, DataRoot = _import_mapper()
    except MapperMissing as e:
        return {'error': 'no-mapper', 'message': str(e)}
    try:
        folder = _run_folder(request) if needs_run else None
    except ValueError as e:
        return {'error': 'invalid', 'message': str(e)}
    root = DataRoot(request.get('dataRoot'))
    return body(jobs, extract, root, folder, request.get('host') or '')


def _ingest(jobs, extract, root, folder, host):
    try:
        return jobs.ingest(root, folder, host=host, log=_log)
    except extract.NotExtracted as e:
        return {'run': folder, 'skipped': str(e)}


def _check(jobs, extract, root, folder, host):
    done = jobs.find_report(root, folder)
    if done is None:
        skipped = _ingest(jobs, extract, root, folder, host)
        if 'skipped' in skipped:
            return skipped
        done = jobs.find_report(root, folder)
    ws, app, rep = done
    return {'run': folder, 'workspace': ws, 'app': app, 'report': jobs.report_path(root, ws, app, folder),
            'verdict': rep.get('verdict')}


def _gc(jobs, extract, root, folder, host):
    return jobs.gc(root)


def ingest_tool(request):
    """ui-graph-ingest: fold a finished run into its app's live graph and keep its report."""
    return _job(request, _ingest)


def check_tool(request):
    """ui-graph-check: a run's report, folding the run in first when it is not yet."""
    return _job(request, _check)


def gc_tool(request):
    """ui-graph-gc: forget the reports of runs whose folder is gone."""
    return _job(request, _gc, needs_run=False)
