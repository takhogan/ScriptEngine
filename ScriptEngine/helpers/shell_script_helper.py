import subprocess
import os


from ScriptEngine.common.script_engine_utils import apply_state_to_cmd_str
from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()

class ShellScriptHelper:

    
    @staticmethod
    def run_shell_script(action, state):
        pre_log = 'Running Shell Script: {}'.format(action["actionData"]["shellScript"])
        script_logger.log(pre_log)
        cwd = "./"
        if len(action["actionData"]["cwd"]) > 0:
            cwd = action["actionData"]["cwd"]
        pre_log_2 = 'Shell Script options: openinNewWindow: {} awaitScript: {} cwd: {}'.format(
            str(action["actionData"]["openInNewWindow"]),
            str(action["actionData"]["awaitScript"]),
            cwd
        )
        script_logger.log(pre_log_2)
        if action["actionData"]["openInNewWindow"]:
            run_command = "start cmd /K " + apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using os.system'.format(run_command)
            script_logger.log(mid_log)

            return_code = os.system("cd {};".format(cwd) + run_command)

            post_log = 'Command completed successfully'
            script_logger.log(post_log)

            state[action["actionData"]["pipeOutputVarName"]] = ""
            state[action["actionData"]["returnCodeOutputVarName"]] =return_code

            post_post_log = "shell output: {} code: {}".format(
                state[action["actionData"]["pipeOutputVarName"]],
                state[action["actionData"]["returnCodeOutputVarName"]]
            )
            script_logger.log(post_post_log)
            post_log += '\n' + post_post_log

        elif action["actionData"]["awaitScript"]:
            await_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using subprocess.run cwd="/", shell=True, capture_output=True'.format(
                await_command
            )
            script_logger.log(mid_log)

            outputs = subprocess.run(await_command, cwd=cwd, shell=True, capture_output=True)

            post_log = 'Command completed successfully'
            script_logger.log(post_log)
            script_logger.log(outputs)
            state[action["actionData"]["pipeOutputVarName"]] = outputs.stdout.decode('utf-8') + '\n' + outputs.stderr.decode('utf-8')
            state[action["actionData"]["returnCodeOutputVarName"]] = outputs.returncode

            post_post_log = "shell output: {} code: {}".format(
                state[action["actionData"]["pipeOutputVarName"]],
                state[action["actionData"]["returnCodeOutputVarName"]]
            )
            script_logger.log(post_post_log)
            post_log += '\n' + post_post_log
        else:
            process_command = apply_state_to_cmd_str(action["actionData"]["shellScript"], state)

            mid_log = 'Running command {} using subprocess.Popen cwd="/", shell=True'.format(
                process_command
            )
            script_logger.log(mid_log)
            proc = subprocess.Popen(process_command, cwd=cwd, shell=True)

            post_log = 'Command process started successfully'
            script_logger.log(post_log)
        script_logger.get_action_log().add_post_file(
            'text',
            'shellScript-log.txt',
            pre_log + '\n' + pre_log_2 + '\n' + mid_log + '\n' + post_log
        )
        return state