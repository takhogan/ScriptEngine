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

import time
import functools

start_time = time.time()

from dateutil import tz
# print(f"builtin initialization completed at {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.custom_thread_pool import CustomThreadPool
from ScriptEngine.custom_process_pool import CustomProcessPool
# print(f"non builtin initialization 1 completed at {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.common.constants.script_engine_constants import *
from ScriptEngine.common.script_engine_utils import datetime_to_local_str, imageFileExtensions, StateEvaluator, is_script_cancelled
# print(f"non builtin initialization 2 completed at {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.system_script_handler import SystemScriptHandler
# print(f"non builtin initialization 3 completed at {time.time() - start_time:.2f} seconds", flush=True)

from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.script_run_summary import log_run_summary
from ScriptEngine.common.host_statistics import describe_host_capabilities
script_logger = ScriptLogger()

# DEVICES_CONFIG_PATH comes from script_engine_constants (data root).
# print(f"script logger initialization completed at {time.time() - start_time:.2f} seconds", flush=True)




def hot_swap(current_action_group, current_script, include_scripts, recovery_script=None):
    if recovery_script is not None:
        pass
    pass

def str_timeout_to_datetime_timeout(timeout, src=None):
    import datetime
    if not isinstance(timeout, str):
        return timeout
    if src == 'deployment_server':
        timeout = datetime.datetime.strptime(timeout, "%Y-%m-%d %H:%M:%S")
        timeout = timeout.replace(tzinfo=tz.tzutc())
    else:
        dt, _, us = timeout.partition(".")
        utc_tz = tz.gettz('UTC')
        timeout = datetime.datetime.strptime(timeout[:-1], "%Y-%m-%dT%H:%M:%S")
        timeout = timeout.replace(tzinfo=tz.tzutc())

    return timeout


def parse_constants(raw_constants):
    """Split each --constants argument into [name, value, False].

    An argument is name:value, where value is a Python expression (the
    controller and ScriptScheduler pass repr()s), so a value can hold colons
    of its own (C:\\, https://) and meaningful whitespace: split on the first
    colon only and strip only the name. Returns (constants, rejected), where
    rejected are the arguments with no colon or no name, for the caller to log.
    """
    constants = []
    rejected = []
    for const in raw_constants or []:
        name, colon, value = const.partition(':')
        name = name.strip()
        if not colon or not name:
            rejected.append(const)
            continue
        constants.append([name, value, False])
    return constants, rejected


class InputsFileError(ValueError):
    """--inputs-file names a file that is not a UTF-8 JSON object."""


def load_inputs_file(path):
    """Reads --inputs-file: a UTF-8 JSON object of {input name: value}.

    The values are literals (an agent tool call's inputs): they are assigned to
    the run's inputs as they are and never evaluated, so nothing in them can run
    as Python. Raises InputsFileError for a file that cannot be read or is not
    a JSON object.
    """
    import json
    try:
        # utf-8-sig: a byte order mark, as some Windows editors write, is not text.
        with open(path, 'r', encoding='utf-8-sig') as inputs_file:
            inputs = json.load(inputs_file)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise InputsFileError('--inputs-file {}: cannot read it as UTF-8 JSON: {}'.format(path, e)) from None
    if not isinstance(inputs, dict):
        raise InputsFileError('--inputs-file {}: must hold a JSON object of input names to values, not {}'.format(
            path, type(inputs).__name__))
    return {name.strip(): value for name, value in inputs.items()}


def merge_literal_inputs(constants, literal_inputs):
    """The top-level run's input rows: one per --inputs-file value, then the
    --constants not named in the file (the file wins).

    A file value's row is [name, '', True]: like a caller's value for a default
    input, parse_inputs takes it from the input state as it is, without eval.
    The values themselves go in the input state (see load_and_run).
    """
    literal_inputs = literal_inputs or {}
    rows = [[name, '', True] for name in literal_inputs]
    rows += [constant for constant in (constants or []) if constant[0] not in literal_inputs]
    return rows


def write_root_outputs(run_folder, run_record):
    """{run folder}/outputs.json: the outputs of the script that was run, the
    names its outputs.json defines with the values the top-level executor's
    state holds for them when the run ends, however it ends. Names with no value
    are left out; a run that never loaded its script has none."""
    import os
    from ScriptEngine.common.run_outputs import OUTPUTS_JSON_FILENAME, outputs_from_state, write_outputs_json
    main_script = run_record.get('main_script')
    state = main_script.state if main_script is not None else {}
    outputs = outputs_from_state(run_record.get('output_names') or [], state)
    try:
        write_outputs_json(os.path.join(run_folder, OUTPUTS_JSON_FILENAME), outputs)
    except Exception as e:
        script_logger.log('SCRIPT MANAGER: could not write the run\'s outputs.json', e, level='error')


def format_env_outputs(env_dict):
    """
    Format environment variables in a cross-platform manner.
    Returns a string that can be used with:
    - Mac/Linux: source <(python3 script.py --write-env)
    - Windows: python script.py --write-env | Invoke-Expression
    """
    import os
    import platform
    import shlex
    
    lines = []
    system = platform.system().lower()
    
    for key, value in env_dict.items():
        # Convert value to string and escape special characters
        value_str = str(value)
        
        if system == 'windows':
            # PowerShell format: Set-Item -Path Env:VAR -Value "value"
            # Escape quotes and backticks for PowerShell
            escaped_value = value_str.replace('"', '`"').replace('$', '`$').replace('`', '``')
            lines.append(f'Set-Item -Path Env:{key} -Value "{escaped_value}"')
        else:
            # Unix/Mac format: export VAR="value"
            # Use shlex.quote for proper shell escaping
            escaped_value = shlex.quote(value_str)
            lines.append(f'export {key}={escaped_value}')
    
    return '\n'.join(lines)

async def close_threads_and_processes(io_executor, process_executor, timeout=30):
    import asyncio
    await asyncio.gather(io_executor.soft_shutdown(script_logger, timeout), process_executor.soft_shutdown(script_logger, timeout))

def load_and_run(script_name, script_id, timeout, constants=None, start_time=None, start_time_str : str=None, device_details=None, system_script=False, screen_plan_server_attached=False, read_env=False, write_env=False, workspace="Default", restart_device_on_crash=False, literal_inputs=None, approved_secrets=None):
    """Runs the script. literal_inputs are --inputs-file's values; approved_secrets
    is --approved-secrets (None: no secret gate). However the run ends, the run
    folder gets an outputs.json (write_root_outputs)."""
    from ScriptEngine.common import secret_gate
    run_folder = script_logger.get_log_folder()
    secret_gate.configure(approved_secrets)
    run_record = {}
    try:
        _load_and_run(
            script_name, script_id, timeout, constants=constants, start_time=start_time,
            start_time_str=start_time_str, device_details=device_details, system_script=system_script,
            screen_plan_server_attached=screen_plan_server_attached, read_env=read_env, write_env=write_env,
            workspace=workspace, restart_device_on_crash=restart_device_on_crash,
            literal_inputs=literal_inputs, run_record=run_record
        )
    finally:
        write_root_outputs(run_folder, run_record)


def end_run_for_approval(approval, run_folder, root_action_log):
    """The run reached a secret it is not approved to read (secret_gate). Says
    so where the controller looks: needs_approval.json, and NEEDS_APPROVAL as
    the root action log's status, written before this returns. No errors.txt
    and nothing on stderr, either of which would make the run an ERROR."""
    import json
    import os
    from ScriptEngine.common import secret_gate
    script_logger.log(
        'SCRIPT MANAGER: run stopped for approval: secret {} in {} ({})'.format(
            approval.secret, approval.script, approval.action),
        level='error'
    )
    with open(os.path.join(run_folder, secret_gate.NEEDS_APPROVAL_FILENAME), 'w', encoding='utf-8') as needs_approval_file:
        json.dump(approval.to_dict(), needs_approval_file)
    if root_action_log is not None:
        root_action_log.add_supporting_file_reference('text', secret_gate.NEEDS_APPROVAL_FILENAME, log_header=False, force=True)
        root_action_log.set_summary('needs approval: secret {}'.format(approval.secret))
        root_action_log.set_status(secret_gate.NEEDS_APPROVAL)
        root_action_log.flush_now()


def _load_and_run(script_name, script_id, timeout, constants=None, start_time=None, start_time_str : str=None, device_details=None, system_script=False, screen_plan_server_attached=False, read_env=False, write_env=False, workspace="Default", restart_device_on_crash=False, literal_inputs=None, run_record=None):
    import os
    import json
    import datetime
    import traceback
    import sys
    import asyncio
    script_logger.log('SCRIPT_MANAGER: ', ' script trigger time: ',
          datetime_to_local_str(str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')),
          'actual script start time: ', datetime.datetime.now(), ' scheduled end time: ',
          datetime_to_local_str(timeout), level='info')
    import numpy as np
    np.set_printoptions(threshold=3, edgeitems=0, linewidth=80, precision=2, suppress=True)
    script_logger.log('constants : ', constants, level='info')
    if literal_inputs:
        # The values go to inputs.txt; a value can be 100 KB of file content.
        script_logger.log('inputs from --inputs-file : ', sorted(literal_inputs), level='info')
    from ScriptEngine.common.secret_gate import SecretApprovalRequired, NEEDS_APPROVAL_EXIT_CODE
    run_folder = script_logger.get_log_folder()
    run_record = {} if run_record is None else run_record
    # Runs off the main thread; ScriptExecutor.check_if_done raises between
    # actions once it finds 2 GB or less free, which lands in the except below.
    from ScriptEngine.common import disk_space_monitor
    disk_space_stop = disk_space_monitor.start(script_logger.get_log_folder())
    from ScriptEngine.script_loader import parse_script
    script_object = parse_script(script_name, system_script, workspace)
    from ScriptEngine.common.run_outputs import script_output_names
    run_record['output_names'] = script_output_names(script_object)
    device_params = {}
    # '' and the literal 'null' are how "nothing attached" arrives from the
    # controller; collapse them to None once so the run has a single answer to
    # "was a device selected?" — the branch below and the error a device-bound
    # action raises when device_params stays empty both read it.
    device_selection = None if device_details in (None, '', 'null') else device_details
    if device_selection is not None:
        if device_selection.startswith('file'):
            file_path = ''.join(device_selection.split(':')[1:])
            file_type = os.path.splitext(file_path)[1]
            script_logger.log('SCRIPT MANAGER: loading input source', file_path, 'file exists', os.path.exists(file_path), level='info')
            import cv2
            if file_type[1:] in imageFileExtensions:
                input_img = cv2.imread(file_path)
                height,width,_ = input_img.shape
                device_params = {
                    'script-engine-device-type': 'file',
                    'screenshot' : lambda: input_img,
                    'width' : width,
                    'height' : height,
                }
            else:
                raise Exception('file type not supported "' + file_type + '"')
        else:
            with open(DEVICES_CONFIG_PATH, 'r') as devices_config_file:
                devices_config = json.load(devices_config_file)
                if device_selection in devices_config:
                    device_params = devices_config[device_selection]
                    # The record's own type (avd, pikvm, ios, ...). This was
                    # hard-coded 'bluestacks' for every configured device, so a
                    # run against a PiKVM or an iPhone was labelled an emulator.
                    # Only 'file' is ever compared against it, which is why it
                    # went unnoticed; it is still what the run log shows. A
                    # record from before `type` was stored has its id prefix.
                    device_params['script-engine-device-type'] = (
                        device_params.get('type') or device_selection.split(':')[0]
                    )
                else:
                    script_logger.log('SCRIPT MANAGER: device config for ', device_selection, ' not found! ', level='error')
    script_logger.log('SCRIPT MANAGER: loading adb_args', device_params, level='info')
    errored = False
    needs_approval = False
    root_action_log = None
    from ScriptEngine.device_controller import DeviceController
    from ScriptEngine.script_executor import ScriptExecutor
    from ScriptEngine.engine_manager import EngineManager
    from ScriptEngine.script_action_executor import ScriptActionExecutor
    from ScriptEngine.parallelized_script_executor import ParallelizedScriptExecutor
    from ScriptEngine.managers.device_secrets_manager import DeviceSecretsManager
    with CustomThreadPool(max_workers=50) as io_executor, CustomProcessPool(max_workers=os.cpu_count()) as process_executor:
        # Samples the write queues while the run happens; see backpressure_monitor
        # for why the after-the-fact async_elapsed gap is not enough.
        from ScriptEngine.common.logging import backpressure_monitor
        backpressure_stop = backpressure_monitor.start(io_executor, process_executor)
        secrets_manager = DeviceSecretsManager()
        # The selection goes along with the resolved params: when it names a device
        # host_devices_config.json does not hold, device_params is left empty above and
        # only the original selection can say why.
        # The script's end time doubles as the deadline for restart_device_on_crash:
        # past it there is no run left to recover the device for.
        # Cancelling the run likewise leaves nothing to recover it for.
        device_controller = DeviceController(
            script_object['props'], device_params, io_executor, secrets_manager, device_selection,
            restart_device_on_crash=restart_device_on_crash, restart_deadline=timeout,
            cancel_check=functools.partial(is_script_cancelled, script_id) if screen_plan_server_attached else None
        )
        engine_manager = EngineManager(script_id, script_logger.get_log_folder())
        script_action_executor = ScriptActionExecutor(device_controller, io_executor, script_object['props'], screen_plan_server_attached)
        # TODO: might need fixing
        # logger = multiprocessing.log_to_stderr()
        # logger.setLevel(multiprocessing.SUBDEBUG)

        base_script_object = script_object.copy()
        base_script_object['inputs'] = merge_literal_inputs(constants, literal_inputs)
        base_include_scripts = script_object['include']

        # action logger for the script running the scriptReference
        script_logger.configure_action_logger(script_object['props']['scriptReference'], 1, None)
        main_script = ScriptExecutor(
            base_script_object,
            base_include_scripts,
            timeout,
            script_name,
            start_time_str,
            script_id,
            device_controller,
            engine_manager,
            io_executor,
            script_action_executor,
            process_executor,
            script_start_time=start_time,
            screen_plan_server_attached=screen_plan_server_attached,
            workspace=workspace,
            system_script=system_script
        )
        run_record['main_script'] = main_script

        try:
            # Prepare input state - include environment variables if read-env is enabled
            input_state = {}
            if read_env:
                import os
                input_state.update(os.environ)
            # Literal values, never evaluated; they win over --constants and
            # the environment (merge_literal_inputs).
            input_state.update(literal_inputs or {})

            main_script.parse_inputs(input_state)
            # action logger for the scriptReference
            main_script.context["script_counter"] += 1
            script_logger.configure_action_logger(
                script_object['props']['scriptReference'],
                main_script.context["script_counter"],
                script_logger.get_action_log()
            )
            # The run's root node, 00001-scriptReference-0: the controller takes
            # the run's status from it.
            root_action_log = script_logger.get_action_log()
            # force keeps the global run log as a supporting file even at error
            # level, where supporting artifacts are otherwise dropped.
            script_logger.get_action_log().add_supporting_file_reference('text', 'global-stdout.txt', log_header=False, force=True)
            if system_script:
                handle_result = SystemScriptHandler.handle_system_script(device_controller, script_name, {})
                if handle_result == "return":
                    script_logger.get_action_log().set_status(ScriptExecutionState.SUCCESS.name)
                else:
                    main_script.handle_action(
                        script_object['props']['scriptReference']
                    )
            else:
                main_script.handle_action(
                    script_object['props']['scriptReference']
                )
        except SecretApprovalRequired as approval:
            asyncio.run(close_threads_and_processes(io_executor, process_executor))
            end_run_for_approval(approval, run_folder, root_action_log)
            needs_approval = True
        except:
            script_logger.log('Script Execution interrupted by exception', level='error')
            asyncio.run(close_threads_and_processes(io_executor, process_executor))

            traceback.print_exc()
            # force keeps the error log as a supporting file even at error level,
            # where supporting artifacts are otherwise dropped.
            script_logger.get_action_log().add_supporting_file('text', 'errors.txt', traceback.format_exc(), log_header=False, force=True)
            errored = True
        else:
            script_logger.log('Script Execution completed', level='error')
            asyncio.run(close_threads_and_processes(io_executor, process_executor))
            # force keeps the completion log as a supporting file even at error
            # level, where supporting artifacts are otherwise dropped.
            script_logger.get_action_log().add_supporting_file('text', 'completed.txt', 'Script Execution completed', log_header=False, force=True)
            
            if write_env:
                output_state = {}
                outputs_log_file_path = script_logger.get_log_folder() + 'outputs.txt'
                main_script.parse_outputs(output_state, outputs_log_file_path)
                env_output = format_env_outputs(output_state)
                print(env_output, flush=True)
                sys.exit(0)
    
    try:
        backpressure_stop.set()
    except Exception:
        pass
    disk_space_stop.set()
    log_run_summary(locals().get('process_executor'))
    script_logger.log('Script Manager process completed', level='error')
    if needs_approval:
        sys.exit(NEEDS_APPROVAL_EXIT_CODE)
    if errored:
        sys.exit(1)
    # script_logger.log('completed script ', script_name, datetime.datetime.now())
    # update_running_scripts_file(script_name, 'pop')


# print(f"Final Method initialization took {time.time() - start_time:.2f} seconds", flush=True)

def main():
    import multiprocessing
    import os
    import sys
    import datetime
    import traceback
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')
    try:
        import argparse
        parser = argparse.ArgumentParser(description='Script Manager CLI')
        
        # Required arguments
        parser.add_argument('--script-name', '-s', required=True, help='Name of the script to run')
        
        # Optional arguments
        parser.add_argument('--start-time', '-st', help='Script start time (format: YYYY-MM-DD HH:MM:SS)')
        parser.add_argument('--end-time', '-et', help='Script end time (format: YYYY-MM-DD HH:MM:SS)')
        parser.add_argument('--log-level', '-l', default='info', choices=['debug', 'info', 'error'],
                            help='Logging level: debug = all logs + all files (pre/post/supporting); '
                                 'info = info/error logs + post files only (enough to render the log video); '
                                 'error = high-level logs only, no files, no video')
        parser.add_argument('--script-id', '-id', help='Script ID (UUID)')
        parser.add_argument('--device', '-d', help='Device details')
        parser.add_argument('--system-script', '-sys', action='store_true', help='Whether this is a system script')
        parser.add_argument('--workspace', '-w', default='Default', help='Workspace name (defaults to "Default"). Only used for library scripts.')
        parser.add_argument('--screen-plan-server-attached', '-spsa', action='store_true', help='Whether a screenplan client server is attached')
        parser.add_argument('--constants', '-c', nargs='*', help='Constants in format key:value')
        parser.add_argument('--inputs-file',
                            help='A UTF-8 JSON object of {input name: value}: literal values for the run\'s inputs, '
                                 'assigned as they are, never evaluated. A name also given in --constants takes '
                                 'the value from this file.')
        parser.add_argument('--approved-secrets', nargs='*', metavar='NAME',
                            help='Turns on the secret gate: a getSecret for a secret not named here reads nothing '
                                 'and stops the run with status NEEDS_APPROVAL (needs_approval.json, exit code 3). '
                                 'Given with no names, no secret may be read. Absent, every secret is read as before.')
        parser.add_argument('--read-env', action='store_true', help='Read environment variables and pass them to parse_inputs')
        parser.add_argument('--restart-device-on-crash', '-rdc', action='store_true',
                            help='When reconnecting to the device fails, stop the device, wait a few seconds, '
                                 'start it again and retry the connection. Keeps retrying until the script end time.')
        # parser.add_argument('--write-env', action='store_true', help='Output script outputs as environment variable exports (cross-platform)')
        parser.add_argument('--log-stdout', action='store_true', default=True, help='Enable logging to stdout (default: False)')
        # Declared so --data-root is a documented argument and this strict
        # parser does not reject it. Its value is read straight from sys.argv by
        # script_engine_constants at import time, because the path constants
        # there are resolved long before this parser runs.
        parser.add_argument('--data-root',
                            help="Root of the controller's data folder (tmp/, logs/, certs/, scripts/). "
                                 'Defaults to $SCREENPLAN_DATA_ROOT, then the per-user app data folder.')

        args = parser.parse_args()
        
        script_name = args.script_name
        
        if args.start_time:
            start_time_str = args.start_time
            start_time = str_timeout_to_datetime_timeout(start_time_str, src='deployment_server')
        else:
            start_time = datetime.datetime.now(datetime.timezone.utc)
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        
        end_time = str_timeout_to_datetime_timeout(args.end_time, src='deployment_server') if args.end_time else None
        log_level = args.log_level
        import uuid
        script_id = args.script_id if args.script_id else uuid.uuid4()
        device_details = None if (not args.device or args.device == '' or args.device == 'null') else args.device
        system_script = args.system_script
        
        constants, rejected_constants = parse_constants(args.constants)
        
        log_folder = LOGS_FOLDER + '/' + str(0).zfill(5) + '-' +\
                    script_name + '-' + datetime_to_local_str(start_time, delim='-') + '/'
        os.makedirs(log_folder, exist_ok=True)
    except Exception as e:
        print(f"Error in initial setup: {e}", file=sys.stderr)
        traceback.print_exc()

    script_logger.set_log_file_path(log_folder + 'global-stdout.txt')
    script_logger.set_log_folder(log_folder)
    script_logger.set_log_header('SCRIPT MANAGER')
    script_logger.set_log_path_prefix(script_logger.get_log_folder() + script_logger.get_log_header() + '-')

    script_logger.set_log_level(log_level)
    script_logger.set_log_to_stdout(args.log_stdout)
    script_logger.log(f'SCRIPT MANAGER: Process ID: {os.getpid()}', level='info')
    script_logger.log('SCRIPT MANAGER: host capabilities', describe_host_capabilities(), level='info')
    script_logger.log('SCRIPT MANAGER: parsed args ', sys.argv, level='debug')
    for rejected in rejected_constants:
        script_logger.log('SCRIPT MANAGER: ignoring constant with no name:value form', repr(rejected), level='error')
    script_logger.log('SCRIPT MANAGER: log_folder', log_folder, start_time, level='info')

    literal_inputs = None
    if args.inputs_file is not None:
        try:
            literal_inputs = load_inputs_file(args.inputs_file)
        except InputsFileError as e:
            script_logger.log('SCRIPT MANAGER: ' + str(e), level='error')
            print(str(e), file=sys.stderr, flush=True)
            write_root_outputs(log_folder, {})
            sys.exit(1)

    script_logger.log('SCRIPT MANAGER: loading script {} and running with log level {}'.format(
        script_name, script_logger.get_log_level()), level='error'
    )
    script_timeout = (start_time + datetime.timedelta(minutes=30)).astimezone(tz=tz.tzutc()) if end_time is None else end_time

    StateEvaluator.configure_script_context(
        script_name=script_name,
        script_id=str(script_id),
        timeout=script_timeout,
        script_start_time=start_time,
        device_details=device_details,
    )

    load_and_run(
        script_name,
        script_id,
        timeout=script_timeout,
        start_time=start_time,
        start_time_str=start_time_str,
        constants=constants,
        device_details=device_details,
        system_script=system_script,
        screen_plan_server_attached=args.screen_plan_server_attached,
        read_env=args.read_env,
        workspace=args.workspace,
        restart_device_on_crash=args.restart_device_on_crash,
        literal_inputs=literal_inputs,
        approved_secrets=args.approved_secrets
        # write_env=args.write_env
    )

if __name__ == '__main__':
    main()
