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
            print('new script_logger instance', cls._instance.id, flush=True)

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
            return thread_local_storage.script_logger
        else:
            return ScriptLogger.get_instance()

    @staticmethod
    def configure_action_logger(action, script_counter, parent_action_log):
        script_logger = ScriptLogger.get_logger()
        script_logger.set_log_header(
            str(script_counter).zfill(5) + '-' + \
            action["actionName"] + '-' + str(action["actionGroup"])
        )
        script_logger.set_log_path_prefix(script_logger.get_log_folder() + script_logger.get_log_header() + '-')
        script_logger.set_action_log(ScriptActionLog(
            action,
            script_logger.get_log_folder(),
            script_logger.get_log_header(),
            script_counter
        ))
        if parent_action_log is not None:
            parent_action_log.add_child(script_logger.get_action_log())
        return script_logger.get_action_log()

    @staticmethod
    def configure_action_logger_from_strs(log_header, log_folder, log_level, action_log):
        script_logger = ScriptLogger.get_logger()
        script_logger.set_action_log(action_log)
        script_logger.set_log_file_path(log_folder + 'stdout.txt')
        script_logger.set_log_path_prefix(log_folder + log_header + '-')
        script_logger.set_log_folder(log_folder)
        script_logger.set_log_header(log_header)
        script_logger.set_log_level(log_level)

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        cls = self.__class__
        new_instance = object.__new__(cls)
        new_instance.id = uuid.uuid4()
        new_instance.action_log = self.action_log  # Deep copy if necessary
        new_instance.log_file_path = self.log_file_path
        new_instance.log_path_prefix = self.log_path_prefix
        new_instance.log_folder_path = self.log_folder_path
        new_instance.log_header = self.log_header
        new_instance.log_level = self.log_level
        print('new script_logger copy instance id', new_instance.id, flush=True)

        return new_instance

    def __reduce__(self):
        # when this class is deseralized is overwrites the current instance
        raise TypeError(f"Instances of {self.__class__.__name__} cannot be serialized.")

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

        print(text, *args, sep=sep, end=end, flush=flush)

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
        self.action_log = action_log

    def get_action_log(self) -> ScriptActionLog:
        return self.action_log

    def set_log_level(self, log_level : str):
        self.log_level = log_level

    def get_log_level(self) -> str:
        return self.log_level
