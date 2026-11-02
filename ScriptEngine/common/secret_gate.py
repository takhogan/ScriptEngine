"""The run-time secret gate (agent-toolkits plan §7 item 3, §9).

script_manager's --approved-secrets names the user secrets this run may read.
Without the flag there is no gate and every getSecret reads its secret as it
always has. With it (an agent tool call passes it, empty unless the user
approved secrets for this call), a getSecret for a secret not on the list sends
no request and stops the whole run: the engine raises SecretApprovalRequired,
which nothing between the action and load_and_run catches, and load_and_run
ends the run as NEEDS_APPROVAL (needs_approval.json, exit code 3, nothing on
stderr). Device passwords (a PiKVM's login) are not user secrets and are not
gated.
"""

from ScriptEngine.common.enums import ScriptExecutionState

NEEDS_APPROVAL = ScriptExecutionState.NEEDS_APPROVAL.name
NEEDS_APPROVAL_FILENAME = 'needs_approval.json'
NEEDS_APPROVAL_EXIT_CODE = 3

# None: no gate. A frozenset (possibly empty): the secrets this run may read.
_approved_secrets = None


class SecretApprovalRequired(Exception):
    """A getSecret reached a secret this run is not approved to read.

    `script` is the name of the script holding the action. The action does not
    know it, so the ScriptExecutor that ran the action fills it in on the way
    up (ScriptExecutor.handle_action)."""

    def __init__(self, secret, action, script=None):
        self.secret = secret
        self.action = action
        self.script = script
        super().__init__('secret {!r} needs the user\'s approval for this run ({})'.format(secret, action))

    def to_dict(self):
        return {
            'status': NEEDS_APPROVAL,
            'secret': self.secret,
            'script': self.script,
            'action': self.action,
        }


def configure(approved_secrets):
    """None turns the gate off; a list (even an empty one) turns it on."""
    global _approved_secrets
    _approved_secrets = None if approved_secrets is None else frozenset(approved_secrets)


def approved_secrets():
    return _approved_secrets


def check_get_secret(action):
    """Raises SecretApprovalRequired when the gate is on and the getSecret
    action names a secret it does not let through. Call it before anything is
    sent."""
    if _approved_secrets is None:
        return
    secret_name = action['actionData']['secretName']
    if secret_name in _approved_secrets:
        return
    raise SecretApprovalRequired(
        secret_name,
        '{}-{}'.format(action['actionName'], action['actionGroup'])
    )
