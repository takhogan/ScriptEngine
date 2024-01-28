import multiprocessing
import datetime

class ScriptLogger:
    _instance = None
    log_path = 'stdout.txt'

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ScriptLogger, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def set_log_path(self, log_path):
        self.log_path = log_path

    def log(self, *args, sep=' ', end='\n', file=None, flush=False):
        text = str(datetime.datetime.now()) + ': ' + sep.join(map(str, args)) + end
        if file is None:
            with open(self.log_path, 'a') as log_file:
                log_file.write(text)
                if flush:
                    log_file.flush()
        else:
            file.write(text)
            if flush:
                file.flush()

        print(*args, sep=sep, end=end, flush=flush)