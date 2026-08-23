"""In-process facts about a finished run that no post-process can recover.

Run timing is deliberately absent: it is reconstructed from the action-log
tree by script_run_timing_generator after the engine exits. What remains here
is state that dies with the process — adb latency, resource counters, and the
executor lifecycle.
"""

from ScriptEngine.common.logging.script_logger import ScriptLogger

script_logger = ScriptLogger()


def log_run_summary(process_executor=None):
    """Log the in-process half of the run summary, at info.

    Assembled at exit rather than streamed so it costs nothing during the run and
    so the numbers describe the whole run rather than a moment in it. Each block
    is guarded independently — a summary that fails to build must not turn a
    successful run into a failed one.
    """
    try:
        from ScriptEngine.managers.adb_command_stats import AdbCommandStats
        adb_lines = AdbCommandStats.summary_lines()
        if adb_lines:
            script_logger.log('ADB SUMMARY: per-command latency for this run', level='info')
            for line in adb_lines:
                script_logger.log('ADB SUMMARY:   ' + line, level='info')
    except Exception:
        pass

    try:
        if process_executor is not None:
            script_logger.log('RUN SUMMARY: ' + process_executor.lifecycle_summary(), level='info')
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
        script_logger.log('RESOURCE SUMMARY: engine ' + ' '.join(parts), level='info')

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
            script_logger.log(
                'RESOURCE SUMMARY:   worker ' + ' '.join(
                    '{}={}'.format(key, '{:.1f}'.format(value) if isinstance(value, float) else value)
                    for key, value in child.items()
                ),
                level='info'
            )
        if not children:
            script_logger.log(
                'RESOURCE SUMMARY:   no worker samples captured (run shorter than one monitor tick)',
                level='info'
            )
    except Exception:
        pass
