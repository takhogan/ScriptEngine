import threading


# Anything slower than this is worth a line at info on its own; below it, the
# per-run summary is the right granularity.
ADB_SLOW_COMMAND_SECONDS = 1.0


class AdbCommandStats:
    """Per-run tally of adb command latency, keyed by subcommand.

    Individual timings are debug-level because a run issues thousands of them.
    This aggregates them so the run summary can answer, at info, whether the
    device link was healthy — the question that decides whether a slow run is the
    emulator's fault or the engine's.
    """

    _lock = threading.Lock()
    _samples = {}

    @classmethod
    def record(cls, command, elapsed, failed=False, timed_out=False):
        try:
            with cls._lock:
                entry = cls._samples.setdefault(
                    command, {'durations': [], 'failed': 0, 'timed_out': 0}
                )
                entry['durations'].append(elapsed)
                if failed:
                    entry['failed'] += 1
                if timed_out:
                    entry['timed_out'] += 1
        except Exception:
            pass

    @classmethod
    def summary_lines(cls):
        with cls._lock:
            snapshot = {
                command: {
                    'durations': sorted(entry['durations']),
                    'failed': entry['failed'],
                    'timed_out': entry['timed_out'],
                }
                for command, entry in cls._samples.items()
            }
        lines = []
        for command, entry in sorted(snapshot.items(), key=lambda kv: -sum(kv[1]['durations'])):
            durations = entry['durations']
            if not durations:
                continue
            count = len(durations)
            total = sum(durations)
            median = durations[count // 2]
            p90 = durations[min(int(count * 0.9), count - 1)]
            lines.append(
                'adb {:<18} n={:<5} total={:7.1f}s med={:6.3f}s p90={:6.3f}s max={:6.3f}s failed={} timed_out={}'.format(
                    command, count, total, median, p90, durations[-1], entry['failed'], entry['timed_out']
                )
            )
        return lines
