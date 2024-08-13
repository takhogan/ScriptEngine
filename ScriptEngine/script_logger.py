import datetime
from script_action_log import ScriptActionLog


class ScriptLogger:
    _instance = None
    log_path = 'stdout.txt'

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ScriptLogger, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        self.action_log = None
        self.log_file_path = None
        self.log_path_prefix = None
        self.log_folder_path = None
        self.log_header = None
        self.log_level = 'info'

    def set_log_file_path(self, log_file_path):
        self.log_file_path = log_file_path

    def set_log_header(self, log_header : str):
        self.log_header = log_header

    def get_log_header(self) -> str:
        return self.log_header

    def set_log_path_prefix(self, log_path_prefix : str):
        self.log_path_prefix = log_path_prefix

    def get_log_path_prefix(self) -> str:
        return self.log_path_prefix

    def set_log_folder(self, log_folder_path : str):
        self.log_folder_path = log_folder_path

    def get_log_folder(self) -> str:
        return self.log_folder_path

    def log(self, *args, sep=' ', end='\n', file=None, flush=True, log_header=True):
        text = str(datetime.datetime.now()) + ': ' + (
            self.log_header if log_header else ''
        ) + sep.join(map(str, args)) + end
        if file is None:
            with open(self.log_file_path, 'a') as log_file:
                log_file.write(text)
                if flush:
                    log_file.flush()
        else:
            file.write(text)
            if flush:
                file.flush()

        print(*args, sep=sep, end=end, flush=flush)

    def set_action_log(self, action_log : ScriptActionLog):
        self.action_log = action_log

    def get_action_log(self) -> ScriptActionLog:
        return self.action_log

    def set_log_level(self, log_level : str):
        self.log_level = log_level

    def get_log_level(self) -> str:
        return self.log_level
