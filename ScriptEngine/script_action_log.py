

class ScriptActionLog:
    def __init__(self, action, base_path):
        pass

    def set_pre_file(self, file_type, relative_path):
        pass

    def add_pre_file(self, file_type, relative_path, file_contents):
        pass

    def append_pre_file(self, file_type, file_contents):
        pass

    def set_post_file(self, file_type, relative_path):
        pass

    def add_post_file(self, file_type, relative_path, file_contents):
        pass

    def add_supporting_file_reference(self, file_type, relative_path):
        pass

    def add_supporting_file(self, file_type, relative_path, file_contents):
        pass

    def append_supporting_file(self, file_type, relative_path, file_contents):
        pass

    def default_file(self, fields, title) -> str:
        pass