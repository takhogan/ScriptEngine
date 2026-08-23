import os
import platform
import sys


def describe_host_capabilities():
    """One-line summary of the hardware and build this run is executing on.

    Logged once per run because several engine behaviours are derived from it and
    are otherwise invisible after the fact: the process pool sizes itself from
    os.cpu_count(), and a frozen build pays import and spawn costs a source build
    does not. Comparing two hosts' run logs is guesswork without it.

    Every lookup is best-effort — this is diagnostics, and it must never be the
    reason a run fails to start.
    """
    logical = os.cpu_count()
    parts = ['logical_cores={}'.format(logical)]

    model = ''
    try:
        model = (platform.processor() or '').strip()
        if not model or model in ('arm', 'i386', 'x86_64'):
            # platform.processor() returns the model string on Windows but only
            # the architecture on macOS/Linux, so ask the platform directly.
            import subprocess
            if sys.platform == 'darwin':
                model = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip() or model
            elif sys.platform.startswith('linux'):
                with open('/proc/cpuinfo', 'r') as cpuinfo:
                    for line in cpuinfo:
                        if line.startswith('model name'):
                            model = line.split(':', 1)[1].strip()
                            break
    except Exception:
        pass
    if model:
        parts.append('cpu="{}"'.format(model))
    parts.append('arch={}'.format(platform.machine() or 'unknown'))

    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
        if physical:
            parts.append('physical_cores={}'.format(physical))
        freq = psutil.cpu_freq()
        if freq is not None and freq.max:
            parts.append('cpu_max_mhz={:.0f}'.format(freq.max))
        parts.append('ram_gb={:.2f}'.format(psutil.virtual_memory().total / (1024 ** 3)))
    except Exception:
        pass

    # The pool is sized from cpu_count() at script_manager.py, and under the
    # 'spawn' start method each worker re-imports the whole engine — on a frozen
    # build, the whole bundle. Recording the number it will use makes that cost
    # attributable instead of mysterious.
    parts.append('process_pool_workers={}'.format(logical))
    parts.append('frozen={}'.format(bool(getattr(sys, 'frozen', False))))
    parts.append('python={}'.format(platform.python_version()))
    parts.append('platform={}'.format(platform.platform()))
    return ' '.join(parts)
