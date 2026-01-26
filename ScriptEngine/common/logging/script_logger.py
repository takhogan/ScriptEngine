from ScriptEngine.common.logging.script_action_log import ScriptActionLog
import sys
import threading
import traceback
thread_local_storage = threading.local()


class ScriptLogger:
    import queue
    _instance = None
    log_path = 'stdout.txt'
    _write_queue = queue.Queue()
    _writer_thread = None
    _writer_running = False

    def __new__(cls, *args, **kwargs):
        import uuid
        if not cls._instance:
            cls._instance = super(ScriptLogger, cls).__new__(cls, *args, **kwargs)
            cls._instance.id = uuid.uuid4()
            cls._instance.action_log = None
            cls._instance.log_file_path = None
            cls._instance.log_path_prefix = None
            cls._instance.log_folder_path = None
            cls._instance.log_header = None
            cls._instance.log_level = 'info'
            cls._instance.log_to_stdout = False 
            cls._instance._start_writer_thread()

        return cls._instance

    def _start_writer_thread(self):
        if not self._writer_thread or not self._writer_thread.is_alive():
            self._writer_running = True
            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self._writer_thread.start()

    def _writer_loop(self):
        import queue
        while self._writer_running:
            try:
                # Get message from queue with a timeout to allow for clean shutdown
                message = self._write_queue.get(timeout=1)
                if message is None:
                    break
                
                # Write to file
                assert self.log_file_path is not None, "log_file_path is not set"
                with open(self.log_file_path, 'a', encoding='utf-8', errors='replace') as log_file:
                    log_file.write(message)
                    log_file.flush()
            except queue.Empty:
                continue
            except Exception as e:
                import time
                print(f"Error in writer thread: {e}", file=sys.stderr)
                time.sleep(1)  # Prevent tight loop on errors
                traceback.print_exc()
                raise e

    def __del__(self):
        self._writer_running = False
        if self._writer_thread:
            self._writer_thread.join(timeout=1)

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
        import uuid
        cls = self.__class__
        new_instance = object.__new__(cls)
        new_instance.id = uuid.uuid4()
        new_instance.action_log = self.action_log  # Deep copy if necessary
        new_instance.log_file_path = self.log_file_path
        new_instance.log_path_prefix = self.log_path_prefix
        new_instance.log_folder_path = self.log_folder_path
        new_instance.log_header = self.log_header
        new_instance.log_level = self.log_level
        new_instance.log_to_stdout = self.log_to_stdout

        return new_instance

    def __reduce__(self):
        # when this class is deseralized is overwrites the current instance
        raise TypeError(f"Instances of {self.__class__.__name__} cannot be serialized.")

    def log(self, *args, sep=' ', end='\n', file=None, flush=True, log_header=True):
        import datetime
        header_str = str(self.log_header) if (log_header and self.log_header is not None) else ''
        text = f"{datetime.datetime.now()}: {header_str} {sep.join(map(str, args))}{end}"

        # Queue the message for non-blocking file writing
        if file is None:
            self._write_queue.put(text)
        else:
            file.write(text)
            if flush:
                file.flush()

        # Print to console with error handling (only if log_to_stdout is enabled)
        if self.log_to_stdout:
            try:
                print(text, sep=sep, end=end, flush=flush)
            except UnicodeEncodeError:
                # If console can't handle the encoding, try to print a sanitized version
                try:
                    # Remove or replace problematic characters
                    sanitized_text = text.encode('ascii', 'replace').decode('ascii')
                    print(sanitized_text, sep=sep, end=end, flush=flush)
                except Exception:
                    # If all else fails, print a basic message
                    print(f"{datetime.datetime.now()}: [Output contained unprintable characters]", 
                          flush=flush)

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

    def set_log_to_stdout(self, log_to_stdout : bool):
        self.log_to_stdout = log_to_stdout

    def get_log_to_stdout(self) -> bool:
        return self.log_to_stdout
