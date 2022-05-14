import sys

sys.path.append(".")
from script_loader import parse_zip
from script_executor import ScriptExecutor



if __name__=='__main__':
    script_name = sys.argv[1]
    # if you want to open zip then you pass .zip in command line args
    script_object = parse_zip('./scripts/' + script_name)
    # print(script_object)
    main_script = ScriptExecutor(script_object)
    main_script.run(log_level='INFO')