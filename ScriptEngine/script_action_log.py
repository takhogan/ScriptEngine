import uuid
import json

class ScriptActionLog:
    def __init__(self, action, log_folder, log_header):
        self.default_path_header = log_folder + log_header + '-'
        self.base_path = log_folder
        self.pre_file = None
        self.post_file = None
        self.supporting_files = []
        self.children = []
        self.id = str(uuid.uuid4())
        self.to_dict()

    def to_dict(self):
        with open(self.default_path_header + 'action-log.json', 'w') as action_log_file:
            json.dump({
                'base_path' : self.base_path,
                'id' : self.id,
                'pre_file' : {
                    'file_type' : self.pre_file[0],
                    'file_path' : self.pre_file[1]
                } if self.pre_file is not None else {},
                'post_file' : {
                    'file_type' : self.post_file[0],
                    'file_path' : self.post_file[1]
                } if self.post_file is not None else {},
                'supporting_files' : [
                    {
                        'file_type' : supporting_file[0],
                        'file_path' : supporting_file[1]
                    } for supporting_file in self.supporting_files
                ],
                'children' : [
                    {
                        'child_id' : child.get_id(),
                        'child_path' : child.get_action_log_path()
                    } for child in self.children
                ]
            }, action_log_file)

    def set_pre_file(self, file_type, relative_path, log_header=True):
        self.pre_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()

    def add_pre_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        self.pre_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()
        if file_type == 'text':
            with open(self.pre_file[1], 'w') as pre_file:
                pre_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def append_pre_file(self, file_type, file_contents, end='\n'):
        assert self.pre_file[0] == file_type
        if file_type == 'text':
            with open(self.pre_file[1], 'a') as pre_file:
                pre_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def set_post_file(self, file_type, relative_path, log_header=True):
        self.post_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()

    def add_post_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        self.post_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()
        if file_type == 'text':
            with open(self.post_file[1], 'w') as post_file:
                post_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def append_post_file(self, file_type, file_contents, end='\n'):
        assert self.post_file[0] == file_type
        if file_type == 'text':
            with open(self.post_file[1], 'a') as post_file:
                post_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def add_supporting_file_reference(self, file_type, relative_path, log_header=True):
        new_supporting_file_path = (
           self.default_path_header if log_header else self.base_path
        ) + relative_path
        for supporting_file_type,supporting_file_path in self.supporting_files:
            assert supporting_file_path != new_supporting_file_path
        self.supporting_files.append((file_type, new_supporting_file_path))
        self.to_dict()

    def add_supporting_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        new_supporting_file_path = (
            self.default_path_header if log_header else self.base_path
        ) + relative_path
        for supporting_file_type, supporting_file_path in self.supporting_files:
            assert supporting_file_path != new_supporting_file_path
        self.supporting_files.append((file_type, new_supporting_file_path))
        self.to_dict()
        if file_type == 'text':
            with open(new_supporting_file_path, 'w') as supporting_file:
                supporting_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def append_supporting_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        existing_supporting_file_path = (
            self.default_path_header if log_header else self.base_path
        ) + relative_path
        file_exists = False
        for supporting_file_type, supporting_file_path in self.supporting_files:
            if supporting_file_path == existing_supporting_file_path:
                file_exists = True
                assert supporting_file_type == file_type
        assert file_exists
        if file_type == 'text':
            with open(existing_supporting_file_path, 'a') as supporting_file:
                supporting_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def add_child_script(self, action_logger):
        self.children.append(action_logger)

    def get_id(self):
        return self.id

    def get_action_log_path(self):
        return self.default_path_header + 'action-log.json'