"""In-process facts about a finished run that no post-process can recover.

Run timing is deliberately absent: it is reconstructed from the action-log
tree by script_run_timing_generator after the engine exits. What remains here
is state that dies with the process — adb latency, resource counters, and the
executor lifecycle.

The summary is both logged at info and written to run_summary.txt at the top
level of the run's log folder, so reading it does not mean grepping it back out
of a global-stdout.txt that is mostly per-action noise.
"""

from ScriptEngine.common.logging.script_logger import ScriptLogger

script_logger = ScriptLogger()

RUN_SUMMARY_FILENAME = 'run_summary.txt'


def build_run_summary(process_executor=None):
    """Assemble the summary lines.

    Each block is guarded independently — a summary that fails to build must not
    turn a successful run into a failed one — so a block that raises costs its own
    lines and nothing else.
    """
    lines = []

    try:
        from ScriptEngine.managers.adb_command_stats import AdbCommandStats
        adb_lines = AdbCommandStats.summary_lines()
        if adb_lines:
            lines.append('ADB SUMMARY: per-command latency for this run')
            lines += ['ADB SUMMARY:   ' + line for line in adb_lines]
    except Exception:
        pass

    try:
        if process_executor is not None:
            lines.append('RUN SUMMARY: ' + process_executor.lifecycle_summary())
    except Exception:
        pass

    try:
        import psutil
        process = psutil.Process()
        cpu = process.cpu_times()
        memory = process.memory_info()
        parts = [
            'cpu_user={:.1f}s'.format(cpu.user),
            'cpu_system={:.1f}s'.format(cpu.system),
            'rss_peak_mb={:.0f}'.format(getattr(memory, 'peak_wset', memory.rss) / (1024 ** 2)),
        ]
        try:
            io_counters = process.io_counters()
            parts += [
                'read_mb={:.1f}'.format(io_counters.read_bytes / (1024 ** 2)),
                'write_mb={:.1f}'.format(io_counters.write_bytes / (1024 ** 2)),
                'read_ops={}'.format(io_counters.read_count),
                'write_ops={}'.format(io_counters.write_count),
            ]
        except Exception:
            # io_counters needs privileges on some platforms and is absent on macOS.
            pass
        lines.append('RESOURCE SUMMARY: engine ' + ' '.join(parts))
    except Exception:
        pass

    # Pool workers do the image encoding and most of the writing, so the engine
    # process alone understates the run. They are already shut down here, so this
    # reports the backpressure monitor's last reading of them while they were
    # alive rather than asking processes that no longer exist.
    try:
        from ScriptEngine.common.logging import backpressure_monitor
        children = backpressure_monitor.last_child_snapshot()
        for child in children:
            lines.append(
                'RESOURCE SUMMARY:   worker ' + ' '.join(
                    '{}={}'.format(key, '{:.1f}'.format(value) if isinstance(value, float) else value)
                    for key, value in child.items()
                )
            )
        if not children:
            lines.append(
                'RESOURCE SUMMARY:   no worker samples captured (run shorter than one monitor tick)'
            )
    except Exception:
        pass

    return lines


def write_run_summary(lines):
    """Write the summary to run_summary.txt beside the run's other top-level logs.

    Written directly rather than through ScriptLogger's queue: this runs at exit,
    after the writer thread has been asked to stop, and the file is small enough
    that a synchronous write costs less than the risk of it never draining.
    """
    if not lines:
        return None
    try:
        log_folder = script_logger.get_log_folder()
        if not log_folder:
            return None
        summary_path = log_folder + RUN_SUMMARY_FILENAME
        with open(summary_path, 'w', encoding='utf-8', errors='replace') as summary_file:
            summary_file.write('\n'.join(lines) + '\n')
        return summary_path
    except Exception:
        return None


def log_run_summary(process_executor=None):
    """Log the in-process half of the run summary at info, and persist it.

    Assembled at exit rather than streamed so it costs nothing during the run and
    so the numbers describe the whole run rather than a moment in it.
    """
    lines = build_run_summary(process_executor)

    for line in lines:
        try:
            script_logger.log(line, level='info')
        except Exception:
            pass

    summary_path = write_run_summary(lines)
    if summary_path is not None:
        try:
            script_logger.log('RUN SUMMARY: written to ' + summary_path, level='info')
        except Exception:
            pass
    return summary_path
