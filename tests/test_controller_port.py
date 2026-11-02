import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ScriptEngine.common.constants.script_engine_constants import DEFAULT_CONTROLLER_PORT, controller_port


class ControllerPortTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.folder.name, 'server_config.json')

    def tearDown(self):
        self.folder.cleanup()

    def write(self, contents):
        with open(self.config_path, 'w') as config_file:
            config_file.write(contents)

    def test_configured_port_is_used(self):
        self.write(json.dumps({'port': 3859, 'logLevel': 'debug'}))
        self.assertEqual(controller_port(self.config_path), 3859)

    def test_anything_unusable_means_the_default(self):
        self.assertEqual(controller_port(self.config_path), DEFAULT_CONTROLLER_PORT)
        for contents in ['{}', '{"port": "3859"}', '{"port": true}', '{"port": 70000}', '[]', '{not json']:
            self.write(contents)
            self.assertEqual(controller_port(self.config_path), DEFAULT_CONTROLLER_PORT, contents)


if __name__ == '__main__':
    unittest.main()
