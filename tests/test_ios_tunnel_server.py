"""Unit tests for the privileged iOS tunnel server entry point.

Nothing here starts a tunnel - that needs root and a device. What is worth
pinning down is the shape of the privileged process: that it refuses to run
unprivileged, that its defaults are the narrow ones, and that it does not drag
the rest of the engine in with it.
"""

import ast

import pytest

from ScriptEngine import ios_tunnel_server


def test_it_refuses_to_run_unprivileged(monkeypatch):
    monkeypatch.setattr(ios_tunnel_server.os, 'geteuid', lambda: 501)

    assert ios_tunnel_server.main([]) == ios_tunnel_server.EXIT_NOT_ROOT


def test_the_defaults_are_loopback_and_usb_only():
    args = ios_tunnel_server.parse_args([])

    # The API is unauthenticated, so it must not be reachable off this host.
    assert args.host == '127.0.0.1'
    assert args.port == 49151
    # Every monitor this daemon runs, it runs as root. Wi-fi adds Bonjour
    # browsing and mobdev2 a scan of the host's pairing records, neither of
    # which a plugged-in phone needs.
    assert args.wifi is False
    assert args.mobdev2 is False


def test_the_address_is_taken_from_pymobiledevice3_not_repeated():
    from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS

    args = ios_tunnel_server.parse_args([])

    # A client and this server disagreeing about where to meet would look like a
    # tunnel that never comes up, so the default comes from one place.
    assert (args.host, args.port) == TUNNELD_DEFAULT_ADDRESS


def test_a_missing_tunnel_transport_is_its_own_exit_code(monkeypatch):
    monkeypatch.setattr(ios_tunnel_server.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(
        'pymobiledevice3.remote.module_imports.verify_tunnel_imports', lambda: False
    )

    # Distinct from EXIT_NOT_ROOT so a packaged build that left a dependency out
    # is distinguishable in the launchd log from one that was started wrongly.
    assert ios_tunnel_server.main([]) == ios_tunnel_server.EXIT_IMPORTS_MISSING


def test_it_does_not_import_the_engine():
    # A root process has no business loading the engine's vision stack, its
    # data-root resolution or its logger - and it has no user to resolve a data
    # root for. Read from the module's own imports rather than from sys.modules,
    # which the rest of the suite has already filled.
    with open(ios_tunnel_server.__file__) as source_file:
        tree = ast.parse(source_file.read())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [name for name in imported if name.split('.')[0] == 'ScriptEngine']


@pytest.mark.parametrize('protocol', ('quic', 'tcp'))
def test_both_transports_are_accepted(protocol):
    assert ios_tunnel_server.parse_args(['--protocol', protocol]).protocol == protocol
