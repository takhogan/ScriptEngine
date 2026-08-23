"""Where a finished run's wall-clock went, reconstructed from the action-log tree.

Runs after the engine exits, like script_log_preview_generator, because every
input is already on disk: each action-log node carries `name`, `start_time` and
`elapsed`. Recording the same numbers a second time during the run would be a
parallel timing path that can drift from the one the controller reads.

The union of action intervals against the run's span separates three problems
that look identical in a run's total duration: more actions executed, each
action costing more, or time spent outside actions altogether.
"""

import argparse
import datetime
import re
import sys

from ScriptEngine.script_log_tree_generator import ScriptLogTreeGenerator


class ScriptRunTimingGenerator:
    @staticmethod
    def collect_entries(log_tree, entries):
        """Flatten the node tree into (name, start, elapsed), skipping unusable nodes."""
        start_time = ScriptRunTimingGenerator.parse_start_time(log_tree.get('start_time'))
        if start_time is not None:
            entries.append((log_tree.get('name') or '', start_time, log_tree.get('elapsed') or 0.0))
        for child in log_tree.get('children', []):
            ScriptRunTimingGenerator.collect_entries(child, entries)
        return entries

    @staticmethod
    def parse_start_time(start_time_str):
        try:
            return datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def summary_lines(entries):
        if not entries:
            return []

        intervals = sorted(
            (start, start + datetime.timedelta(seconds=elapsed or 0.0))
            for _, start, elapsed in entries
        )
        span_start = intervals[0][0]
        span_end = max(end for _, end in intervals)
        span = (span_end - span_start).total_seconds()

        # Actions overlap (the parallel executor runs several at once, and every
        # parent encloses its children), so summing elapsed would double-count.
        # Union the intervals instead.
        busy = 0.0
        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                busy += (current_end - current_start).total_seconds()
                current_start, current_end = start, end
        busy += (current_end - current_start).total_seconds()

        by_type = {}
        for name, _, elapsed in entries:
            action_type = re.sub(r'-\d+$', '', name or '')
            bucket = by_type.setdefault(action_type, [0, 0.0])
            bucket[0] += 1
            bucket[1] += elapsed or 0.0

        dead = max(span - busy, 0.0)
        lines = [
            'RUN TIMING: span={:.1f}s busy={:.1f}s ({:.0f}%) dead={:.1f}s ({:.0f}%) actions={}'.format(
                span, busy, (busy / span * 100) if span else 0.0,
                dead, (dead / span * 100) if span else 0.0, len(entries)
            )
        ]
        for action_type, (count, total) in sorted(by_type.items(), key=lambda kv: -kv[1][1]):
            lines.append(
                'RUN TIMING:   {:<26} n={:<5} total={:8.1f}s mean={:7.3f}s'.format(
                    action_type, count, total, total / count if count else 0.0
                )
            )
        return lines

    @staticmethod
    def assemble_run_timing_summary(action_log_path):
        log_tree = {
            'action_log_path': action_log_path
        }
        ScriptLogTreeGenerator.assemble_script_log_tree(log_tree)
        entries = ScriptRunTimingGenerator.collect_entries(log_tree, [])
        return ScriptRunTimingGenerator.summary_lines(entries)


def main():
    parser = argparse.ArgumentParser(description='Script Run Timing Generator')
    parser.add_argument('action_log_path', help='Path to the root action log file')
    parser.add_argument('output_file_name', nargs='?', help='Write the summary here instead of stdout')
    args = parser.parse_args()

    lines = ScriptRunTimingGenerator.assemble_run_timing_summary(args.action_log_path)
    if args.output_file_name:
        with open(args.output_file_name, 'w', encoding='utf-8') as summary_file:
            summary_file.write('\n'.join(lines) + '\n')
    else:
        sys.stdout.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
