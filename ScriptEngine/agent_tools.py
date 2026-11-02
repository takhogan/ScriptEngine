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

"""The engine's entry point for agent tooling: the controller's MCP tools that
need the engine's own code without running a script.

    python -m ScriptEngine.agent_tools TOOL --request REQUEST.json --output RESULT.json
    agent_tools TOOL --request ... --output ...      (the packaged executable)

script_manager runs scripts and nothing else. Each tool here reads one JSON
request and writes one JSON result, and runs no script, starts no device and
writes no run folder. A tool is a function `request -> result` in its own
module, named in TOOLS and imported only when it is called, so one tool's
dependencies never slow another's start.

Exit 0 means RESULT.json holds the tool's answer, which may itself be an
error the tool reports (`{"error": ..., "message": ...}`). Any other exit
means the tool failed; stderr says why. An unknown tool exits 2, so a
controller can tell an engine that predates a tool from one that failed.

To add a tool: write `def run(request) -> dict` (or any function of that
shape) in its module, add it to TOOLS, and add a test that calls `main`.
"""

import importlib
import json
import os
import sys

# tool name -> (module, function). Imported lazily.
TOOLS = {
    # Scores a script's detectObject actions on saved screens (the controller's score_detects).
    'score-detects': ('ScriptEngine.detect_scorer', 'score_detects'),
}

EXIT_UNKNOWN_TOOL = 2


def _quiet_logger():
    """The engine's logger writes to stdout and a run's log file; a tool has
    neither. Its answer is RESULT.json."""
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    script_logger = ScriptLogger()
    script_logger.set_log_to_stdout(False)
    script_logger.set_log_level('error')
    script_logger.set_log_file_path(os.devnull)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog='agent_tools', description='ScriptEngine tools for agents (no script is run)')
    parser.add_argument('tool', help='One of: ' + ', '.join(sorted(TOOLS)))
    parser.add_argument('--request', required=True, help='The request, a JSON file')
    parser.add_argument('--output', required=True, help='Where the result JSON is written')
    # Read by script_engine_constants straight from sys.argv, at import time.
    parser.add_argument('--data-root', help="Root of the controller's data folder; defaults to $SCREENPLAN_DATA_ROOT")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.tool not in TOOLS:
        print('agent_tools: unknown tool {}; this engine has: {}'.format(args.tool, ', '.join(sorted(TOOLS))), file=sys.stderr)
        return EXIT_UNKNOWN_TOOL
    _quiet_logger()
    with open(args.request, 'r', encoding='utf-8') as request_file:
        request = json.load(request_file)
    module_name, function_name = TOOLS[args.tool]
    tool = getattr(importlib.import_module(module_name), function_name)
    try:
        result = tool(request)
    except FileNotFoundError as e:
        result = {'error': 'not-found', 'message': str(e)}
    with open(args.output, 'w', encoding='utf-8') as output_file:
        json.dump(result, output_file)
    return 0


if __name__ == '__main__':
    import multiprocessing
    # A frozen executable re-enters here in any child process a library starts.
    multiprocessing.freeze_support()
    sys.exit(main())
