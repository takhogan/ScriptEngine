"""What a PiKVM keyboard can type, checked before a key is sent.

pikvm_lib sends a character it has no key for as Key{char} (KeyÉ), which the
PiKVM ignores, so text with an accented letter lost it without a word; and a
CRLF was two presses of Enter, two line breaks in a Windows editor. A
VDI_WriteFile that types the wrong bytes writes a wrong file, so a keyboard
action's text is typed exactly or not at all (agent-toolkits plan §7, item 5).

pikvm_lib refuses such text itself from the agent-toolkits branch on
(pikvm_lib.keymaps.TYPEABLE_CHARACTERS). This check is the engine's own, so the
protection holds on a host still running an older pikvm_lib. The two sets are
the same: printable ASCII, tab, "\\n" and "\\r", what the library's US-layout
keymap has a key for.
"""
import string

TYPEABLE_CHARACTERS = frozenset(string.ascii_letters + string.digits + string.punctuation + ' \t\n\r')


class UntypeableTextError(ValueError):
    """Text holds a character the device has no key for. Nothing was typed."""


def describe_untypeable(char, position, is_secret=False):
    # A secret's character is not named: the message goes to the run log.
    what = 'a character of a secret' if is_secret else '{!r} (U+{:04X})'.format(char, ord(char))
    return 'cannot type {} at position {} of the typed text: the PiKVM keyboard has no key for it, so nothing was typed'.format(
        what, position)


def prepare_typed_keys(keys, secret_flags):
    """The keys to send for a keyboard action's keys (one character each, or a
    named key such as 'enter' from {enter}), with which came from a secret.

    "\\r\\n" becomes one "\\n" and a lone "\\r" a "\\n": each line break is one
    Enter. Raises UntypeableTextError naming the first character there is no
    key for, and its position among keys, before anything is typed. Named keys
    pass as they are.
    """
    for position, (key, is_secret) in enumerate(zip(keys, secret_flags)):
        if len(key) == 1 and key not in TYPEABLE_CHARACTERS:
            raise UntypeableTextError(describe_untypeable(key, position, is_secret))
    prepared_keys = []
    prepared_flags = []
    position = 0
    while position < len(keys):
        key, is_secret = keys[position], secret_flags[position]
        if key == '\r':
            key = '\n'
            if position + 1 < len(keys) and keys[position + 1] == '\n':
                is_secret = is_secret or secret_flags[position + 1]
                position += 1
        prepared_keys.append(key)
        prepared_flags.append(is_secret)
        position += 1
    return prepared_keys, prepared_flags
