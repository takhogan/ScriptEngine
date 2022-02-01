import sys

sys.path.append(".")
from script_loader import parse_zip
from script_executor import ScriptExecutor



if __name__=='__main__':
    script_object = parse_zip('./scripts/WarAndOrderIcon')
    main_script = ScriptExecutor(script_object)
    main_script.run(log_level='INFO')