import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ScriptEngine.common.script_engine_utils import state_eval
from ScriptEngine.script_manager import parse_constants

# The controller and ScriptScheduler pass each run input as
# --constants name:repr(value). The engine used to split on every colon and
# drop any argument that did not come out as exactly two parts, so a Windows
# path or a URL never reached the script, with nothing in the log.


class ParseConstantsTest(unittest.TestCase):
    def assert_round_trip(self, name, value):
        constants, rejected = parse_constants([name + ':' + repr(value)])
        self.assertEqual(rejected, [])
        self.assertEqual(len(constants), 1)
        parsed_name, expression, is_default = constants[0]
        self.assertEqual(parsed_name, name)
        self.assertFalse(is_default)
        # parse_inputs in script_executor evaluates the expression this way.
        self.assertEqual(state_eval(expression, {}, {}), value)

    def test_windows_path(self):
        self.assert_round_trip('path', 'C:\\Users\\me\\Documents\\notes.txt')

    def test_url(self):
        self.assert_round_trip('url', 'https://example.com:8443/a?b=c:d')

    def test_multi_line_string(self):
        self.assert_round_trip('contents', 'first: line\r\nsecond:\tline\n\nlast line: C:\\x\n')

    def test_trailing_and_leading_spaces(self):
        self.assert_round_trip('padded', '  value with spaces   ')

    def test_value_expression_is_kept_as_given(self):
        constants, _ = parse_constants([' name :{"a": 1}  '])
        self.assertEqual(constants, [['name', '{"a": 1}  ', False]])

    def test_empty_value(self):
        constants, rejected = parse_constants(['name:'])
        self.assertEqual(constants, [['name', '', False]])
        self.assertEqual(rejected, [])

    def test_arguments_without_a_name_are_rejected(self):
        constants, rejected = parse_constants(['novalue', ':nameless', 'ok:1'])
        self.assertEqual(constants, [['ok', '1', False]])
        self.assertEqual(rejected, ['novalue', ':nameless'])

    def test_no_constants(self):
        self.assertEqual(parse_constants(None), ([], []))


if __name__ == '__main__':
    unittest.main()
