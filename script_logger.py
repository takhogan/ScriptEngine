import multiprocessing


class ScriptLogger:
    def __init__(self, log_path):
        self.log_path = log_path + 'script-log.log'
        pass

    def log(self, text):
        print(text)
        with open(self.log_path, 'w') as log_file:
            log_file.write(text)
