from ScriptEngine.common.logging.script_action_log import ScriptActionLog
import sys
import threading
thread_local_storage = threading.local()


class ScriptLogger:
    import queue
    _instance = None
    log_path = 'stdout.txt'
    # error < info < debug. A message/artifact is kept when its own level is at
    # least as important as the configured one, i.e. rank(level) <= rank(log_level):
    #   error -> only error logs, no files, no video
    #   info  -> error + info logs, post files only (enough to render the video)
    #   debug -> everything: all logs, pre/post/supporting files
    LOG_LEVELS = {'error': 0, 'info': 1, 'debug': 2}
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
            cls._instance.log_to_stdout = True 
            cls._instance._start_writer_thread()

        return cls._instance

    def _start_writer_thread(self):
        if not self._writer_thread or not self._writer_thread.is_alive():
            self._writer_running = True
            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self._writer_thread.start()
            # Stop the writer before interpreter finalization: a daemon thread
            # holding the stdout buffer lock at shutdown aborts the process
            # with "Fatal Python error: _enter_buffered_busy".
            import atexit
            atexit.register(self._stop_writer_thread)

    def _stop_writer_thread(self):
        self._writer_running = False
        # Sentinel queues behind any pending messages, so the queue drains
        # before the loop exits.
        self._write_queue.put(None)
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2)

    def _writer_loop(self):
        import queue
        while True:
            try:
                # Get message from queue with a timeout to allow for clean shutdown.
                # Keep draining after _writer_running flips off — the None sentinel
                # marks the true end of the queue.
                try:
                    message = self._write_queue.get(timeout=1)
                except queue.Empty:
                    if not self._writer_running:
                        break
                    continue
                if message is None:
                    break

                # Queue entries are (text, write_to_log_file). Bare strings are
                # accepted so anything that queued before this shape existed still
                # behaves as it did.
                if isinstance(message, tuple):
                    message, write_to_log_file = message
                else:
                    write_to_log_file = True

                if self.log_to_stdout:
                    try:
                        sys.stdout.write(message)
                        sys.stdout.flush()
                    except UnicodeEncodeError:
                        try:
                            sys.stdout.write(message.encode('ascii', 'replace').decode('ascii'))
                            sys.stdout.flush()
                        except Exception:
                            pass
                    except Exception:
                        # stdout may be closed or finalized during interpreter shutdown
                        pass

                if write_to_log_file:
                    with open(self.log_file_path, 'a', encoding='utf-8', errors='replace') as log_file:
                        log_file.write(message)
                        log_file.flush()
            except queue.Empty:
                continue
            except Exception as e:
                import time
                print(f"Error in writer thread: {e}. Message: {message}", file=sys.stderr)
                time.sleep(1)  # Prevent tight loop on errors
                raise e

    def __del__(self):
        self._stop_writer_thread()

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

    def _level_rank(self, level):
        # Unknown levels are treated as 'info' so a typo never silently drops a log.
        return self.LOG_LEVELS.get(level, self.LOG_LEVELS['info'])

    def should_log(self, level='info'):
        """Whether a message or artifact of the given level is kept at the
        currently configured log level. Used both to gate text logs and to
        decide which action-log files (pre/post/supporting) get captured."""
        return self._level_rank(level) <= self._level_rank(self.log_level)

    def log(self, *args, sep=' ', end='\n', file=None, flush=True, log_header=True, level='info'):
        import datetime
        # Drop messages below the configured verbosity (applies to the write
        # queue and explicit-file writes alike).
        if not self.should_log(level):
            return
        header_str = str(self.log_header) if (log_header and self.log_header is not None) else ''
        text = f"{datetime.datetime.now()}: {header_str} {sep.join(map(str, args))}{end}"

        if file is None:
            self._write_queue.put((text, True))
        else:
            # An explicit `file` selects where the *persistent* copy goes, not
            # whether the message reaches stdout. Callers pass DummyFile() to keep
            # a line out of the log file while still emitting it on stdout -- the
            # device controller's `<--id-->...<--id-->` response frames, which the
            # host parses out of the child's stdout, are written this way. Sending
            # those to the log file instead (file=None) would work, but a
            # screen_capture response is a base64 JPEG of the whole screen.
            #
            # stdout used to be written unconditionally at the end of this method,
            # outside this branch. Moving it into _writer_loop made it reachable
            # only by messages that go through _write_queue, i.e. only file is
            # None, which silently dropped every explicit-file line. Queue it with
            # the log-file write suppressed instead of writing stdout from here:
            # the writer thread is the only thing touching stdout, so a large frame
            # cannot be split by a log line landing mid-write.
            file.write(text)
            if flush:
                file.flush()
            self._write_queue.put((text, False))

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
        # argparse already restricts choices; this guards programmatic callers.
        if log_level not in self.LOG_LEVELS:
            log_level = 'info'
        self.log_level = log_level

    def get_log_level(self) -> str:
        return self.log_level

    def set_log_to_stdout(self, log_to_stdout : bool):
        self.log_to_stdout = log_to_stdout

    def get_log_to_stdout(self) -> bool:
        return self.log_to_stdout
