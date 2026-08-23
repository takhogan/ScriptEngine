import os
import sys


def data_root_from_argv(argv=None):
    """Reads --data-root out of the command line.

    Scanned straight from sys.argv rather than taken from argparse: the path
    constants below are module-level, so they are resolved at import time,
    long before any entry point parses its arguments. Entry points that use a
    strict parser have to declare the flag for it to be passable.
    """
    argv = sys.argv if argv is None else argv
    for index, argument in enumerate(argv):
        if argument == '--data-root' and index + 1 < len(argv):
            return argv[index + 1]
        if argument.startswith('--data-root='):
            return argument.split('=', 1)[1]
    return None


def default_user_data_folder():
    """Where Script-Engine-Controller keeps its runtime state when it did not tell us.

    The controller normally passes the exact folder in SCREENPLAN_DATA_ROOT
    when it spawns us. This mirrors Electron's userData location for the times
    an engine process is started by hand: state belongs in the per-user app
    data folder, not next to the install, which on macOS is the (world
    readable, admin-writable) directory containing the .app.
    """
    app_name = 'ScriptEngineController'
    if sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    elif sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, app_name)


# --data-root wins over the environment so an engine run by hand can point at
# another install without exporting anything.
DATA_ROOT = os.path.expanduser(
    data_root_from_argv() or os.environ.get('SCREENPLAN_DATA_ROOT') or default_user_data_folder()
)


def data_path(*parts):
    """Joins a path under the controller's data root."""
    return os.path.join(DATA_ROOT, *parts)


VIBER_CREDENTIALS_FILEPATH = 'assets\\viber_credentials.json'
RUNNING_SCRIPTS_PATH = data_path('tmp', 'running_scripts.json')
SERVICE_CREDENTIALS_FILE_PATH = '..\\assets\\service_credentials.json'
# Filename matches what the controller writes (locals.CA_CERT_PATH). It was
# spelled 'Scriptcontroller-' here, which resolves only because macOS and
# Windows filesystems are case-insensitive.
VERIFY_PATH = data_path('certs', 'ScriptController-CACert.pem')
# The token does NOT live under the data root: the controller pins it to the
# per-user app data folder alongside server_config.json, so that a data root
# shared between installations is not also a shared credential. The controller
# passes the exact path in SCREENPLAN_AUTH_HASH_PATH; the fallback mirrors
# where it pins it.
SERVER_AUTH_HASH_PATH = (
    os.environ.get('SCREENPLAN_AUTH_HASH_PATH')
    or os.path.join(default_user_data_folder(), 'server_auth_hash.json')
)
DEVICES_CONFIG_PATH = data_path('assets', 'host_devices_config.json')
LOGS_FOLDER = data_path('logs')
SCRIPTS_FOLDER = data_path('scripts')
SCRIPT_LIBRARY_FOLDER = data_path('scripts', 'scriptLibrary')
SYSTEM_SCRIPTS_FOLDER = data_path('scripts', 'systemScripts')
LOG_TREE_PATH = data_path('tmp', 'log_tree.json')
ENGINE_INTERRUPTS_FILE = data_path('tmp', '{}_engine_interrupts.json')
DETECT_OBJECT_RESULT_MARKER = 'X_Screenplan_DetectObject_Result'
