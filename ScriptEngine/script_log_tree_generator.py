import sys
import json
import os

from ScriptEngine.common.constants.script_engine_constants import LOG_TREE_PATH, resolve_data_path

bin_path = os.path.abspath("bin")
os.environ["PATH"] += os.pathsep + bin_path

class ScriptLogTreeGenerator:
    def __init__(self):
        pass

    @staticmethod
    def assemble_script_log_tree(child_obj):
        action_log_dict = None
        # Recorded relative to the data root; absolute for logs written
        # before that rule, which resolve_data_path passes through.
        with open(resolve_data_path(child_obj['action_log_path']), 'r') as action_log_file:
            action_log_dict = json.load(action_log_file)
        if action_log_dict is not None:
            child_obj.update(action_log_dict)
            for child in action_log_dict['children']:
                ScriptLogTreeGenerator.assemble_script_log_tree(child)

if __name__ == '__main__':
    log_tree = {
        'action_log_path' : sys.argv[1]
    }
    ScriptLogTreeGenerator.assemble_script_log_tree(log_tree)
    with open(LOG_TREE_PATH, 'w') as log_tree_file:
        json.dump(log_tree, log_tree_file)
