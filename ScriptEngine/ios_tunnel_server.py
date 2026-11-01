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

"""
The RSD tunnel server for iOS 17+ devices. Runs as root, and does nothing else.

From iOS 17 every developer service - screenshots included - is reachable only
over a tunnel to the device, and creating that tunnel means creating a `utun`
interface, which macOS gates on uid 0. So one privileged process has to exist.
This is it, and it is deliberately the smallest one that will do:

  * It takes no instructions from the application. The only thing that reaches
    it at runtime is its own command line, fixed when the launchd job is
    installed. Everything else goes through tunneld's loopback HTTP API, which
    only lists and creates tunnels.
  * It imports pymobiledevice3 and nothing from ScriptEngine. A root process
    should not be pulling in the engine's own modules, its data-root resolution
    or its logger - it has no user to resolve a data root for, and the launchd
    job captures stdout and stderr to a file of its own.

docs/ios-device-support-plan.md section 8 is the design this belongs to,
including why it is a launchd daemon registered through SMAppService rather
than a `sudo` call per use.

Replaces managers/pymobile_tunnel_server_manager.py, which passed the return
value of `Tunneld().start()` to subprocess.Popen as if it were a command line
and so could never have run.
"""

import argparse
import logging
import os
import sys

# tunneld's own default, and what pymobiledevice3's client side looks for unless
# it is told otherwise. Imported rather than repeated so that a client and this
# server cannot disagree about where to meet.
from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS

logger = logging.getLogger('screenplan.ios-tunnel')

# Exit codes, so the launchd job's log says which failure this was rather than
# only that the process died.
EXIT_NOT_ROOT = 2
EXIT_IMPORTS_MISSING = 3


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Serve RSD tunnels to attached iOS 17+ devices on the loopback interface.'
    )
    parser.add_argument('--host', default=TUNNELD_DEFAULT_ADDRESS[0],
                        help='Address to serve the tunnel API on (default: %(default)s). Loopback '
                             'only: the API is unauthenticated.')
    parser.add_argument('--port', type=int, default=TUNNELD_DEFAULT_ADDRESS[1],
                        help='Port for the tunnel API (default: %(default)s).')
    parser.add_argument('--protocol', choices=('quic', 'tcp'), default=None,
                        help="Tunnel transport. Defaults to pymobiledevice3's own choice, which "
                             'depends on the Python version.')
    # Off by default, and each one is a flag rather than a default because every
    # monitor this process runs is something it does as root. ScreenPlan drives
    # phones that are plugged in, which is what the usbmux and usb monitors
    # cover; wi-fi and mobdev2 add Bonjour browsing and a scan of the host's
    # pairing records for devices that are not attached at all.
    parser.add_argument('--wifi', action='store_true', help='Also tunnel to devices found over wi-fi.')
    parser.add_argument('--mobdev2', action='store_true',
                        help="Also tunnel to devices found in this host's pairing records.")
    return parser.parse_args(argv)


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout
    )
    args = parse_args(argv)

    # Checked here as well as by launchd so that someone running this by hand
    # gets a sentence instead of a traceback from deep inside the tunnel code.
    if os.geteuid() != 0:
        logger.error(
            'The iOS tunnel server has to run as root: it creates a utun network interface, '
            'which macOS does not allow otherwise. It is meant to be started by its launchd '
            'job, not by hand.'
        )
        return EXIT_NOT_ROOT

    # Imported here, after the root check: these are the optional extras that
    # carry the tunnel transports, and a missing one should be reported as
    # itself rather than as an ImportError at module load.
    from pymobiledevice3.remote.common import TunnelProtocol
    from pymobiledevice3.remote.module_imports import verify_tunnel_imports
    from pymobiledevice3.tunneld.server import TunneldRunner

    if not verify_tunnel_imports():
        logger.error(
            'pymobiledevice3 cannot create tunnels in this build: its tunnel transport could not '
            'be imported. On a packaged build this means a dependency was left out of the bundle.'
        )
        return EXIT_IMPORTS_MISSING

    protocol = TunnelProtocol(args.protocol) if args.protocol else TunnelProtocol.DEFAULT
    logger.info(
        'serving iOS tunnels on %s:%s over %s (wifi=%s, mobdev2=%s)',
        args.host, args.port, protocol.value, args.wifi, args.mobdev2
    )
    # Blocks for the lifetime of the daemon. launchd restarts it if it exits.
    TunneldRunner.create(
        args.host, args.port,
        protocol=protocol,
        usb_monitor=True,
        usbmux_monitor=True,
        wifi_monitor=args.wifi,
        mobdev2_monitor=args.mobdev2
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
