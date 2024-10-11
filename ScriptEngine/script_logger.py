import copy
import datetime
import threading
import uuid

from script_action_log import ScriptActionLog

thread_local_storage = threading.local()


class ScriptLogger:
    _instance = None
    log_path = 'stdout.txt'

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ScriptLogger, cls).__new__(cls, *args, **kwargs)
            cls._instance.id = uuid.uuid4()
            cls._instance.action_log = None
            cls._instance.log_file_path = None
            cls._instance.log_path_prefix = None
            cls._instance.log_folder_path = None
            cls._instance.log_header = None
            cls._instance.log_level = 'info'
        return cls._instance

    @classmethod
    def get_instance(cls):
        """Ensure that the singleton instance is returned."""
        return cls._instance

    @staticmethod
    def get_logger():
        """
        Check if thread-local logger exists, otherwise return the global singleton logger.
        """
        if hasattr(thread_local_storage, 'script_logger'):
            print("Using thread-local logger")
            return thread_local_storage.script_logger
        else:
            print("Using global singleton logger")
            return ScriptLogger.get_instance()

    def copy(self):
        """
        Return a shallow copy of the current instance, including a shallow copy of the action_log attribute.
        """
        # Create a shallow copy of the current instance
        new_copy = copy.copy(self)
        new_copy.id = uuid.uuid4()

        return new_copy

    def log(self, *args, sep=' ', end='\n', file=None, flush=True, log_header=True):
        text = str(datetime.datetime.now()) + ': ' + (
            self.log_header if log_header else ''
        ) + ' ' + sep.join(map(str, args)) + end
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

    def set_action_log(self, action_log : ScriptActionLog):
        print("setting action log", self.id)
        self.action_log = action_log

    def get_action_log(self) -> ScriptActionLog:
        print("getting action log", self.id)
        return self.action_log

    def set_log_level(self, log_level : str):
        self.log_level = log_level

    def get_log_level(self) -> str:
        return self.log_level
