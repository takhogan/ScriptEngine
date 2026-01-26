import datetime
import uuid
import json


class ScriptActionLog:
    def __init__(self, action, log_folder, log_header, script_counter):
        self.default_path_header = log_folder + log_header + '-'
        self.base_path = log_folder
        self.pre_file = None
        self.post_file = None
        self.supporting_files = []
        self.children = []
        self.id = str(uuid.uuid4())
        self.name = action["actionName"] + '-' + str(action["actionGroup"])
        self.script_counter = script_counter
        self.status = 'RUNNING'
        self.summary = ''
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.script_log_folder = None
        self.target_system = action['actionData']['targetSystem']
        self.attributes = {}

        if action["actionName"] == "scriptReference":
            self.type = "script"
            self.script_name = action["actionData"]["scriptName"]
        else:
            self.type = "action"
            self.script_name = None

        if action["actionName"] == "scriptReference":
            self.attributes = {
                "branchingBehavior": action["actionData"]["branchingBehavior"],
                "runMode": action["actionData"]["runMode"],
                "actionOrder": action["actionData"]["actionOrder"],
                "scriptMaxActionAttempts": action["actionData"]["scriptMaxActionAttempts"]
            }
        elif action["actionName"] == "detectObject":
            self.attributes = {
                "detectActionType": action["actionData"]["detectActionType"]
            }

        self.to_dict()

    def to_dict(self):
        with open(self.default_path_header + 'action-log.json', 'w') as action_log_file:
            json.dump({
                'base_path' : self.base_path,
                'action_log_path' : self.get_action_log_path(),
                'id' : self.id,
                'name' : self.name,
                'target_system' : self.target_system,
                'script_name' : self.script_name,
                'script_log_folder': self.get_script_log_folder(),
                'script_counter' : self.get_script_counter(),
                'log_object_type' : self.type,
                'tree_entity_type' : 'node',
                'status' : self.get_status(),
                'summary' : self.summary,
                'start_time' : self.start_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
                'elapsed' : (datetime.datetime.now(datetime.timezone.utc) - self.start_time).total_seconds(),
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
                        'id' : child.get_id(),
                        'script_counter' : child.get_script_counter(),
                        'log_object_type' : child.get_type(),
                        'tree_entity_type' : 'child',
                        'action_log_path' : child.get_action_log_path()
                    } for child in self.children
                ],
                'attributes' : self.attributes
            }, action_log_file)

    def set_pre_file(self, file_type, relative_path : str, log_header : bool =True, absolute_path : bool =False):
        self.pre_file = (
            file_type,
            (
                (self.default_path_header if log_header else self.base_path) + relative_path
            ) if not absolute_path else relative_path
        )
        self.to_dict()

    def add_pre_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        self.pre_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()
        if file_type == 'text':
            with open(self.pre_file[1], 'w', encoding='utf-8', errors='replace') as pre_file:
                pre_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def append_pre_file(self, file_type, file_contents, end='\n'):
        if self.pre_file[0] != file_type:
            raise Exception(
                'Attempting to append contents of type ' + file_type +
                ' to file ' + str(self.pre_file) + ' of type ' + self.pre_file[0] +
                ' contents: ' + str(file_contents)
            )
        if file_type == 'text':
            with open(self.pre_file[1], 'a', encoding='utf-8', errors='replace') as pre_file:
                pre_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def set_post_file(self, file_type, relative_path, log_header=True, absolute_path=False):
        self.post_file = (
            file_type,
            (
                (self.default_path_header if log_header else self.base_path) + relative_path
            ) if not absolute_path else relative_path
        )
        self.to_dict()

    def add_post_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        self.post_file = (
            file_type,
            (self.default_path_header if log_header else self.base_path) + relative_path
        )
        self.to_dict()
        if file_type == 'text':
            with open(self.post_file[1], 'w', encoding='utf-8', errors='replace') as post_file:
                post_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def append_post_file(self, file_type, file_contents, end='\n'):
        if self.post_file[0] != file_type:
            raise Exception(
                'Attempting to append contents of type ' + file_type +
                ' to file ' + str(self.post_file) + ' of type ' + self.post_file[0] +
                ' contents: ' + str(file_contents)
            )
        if file_type == 'text':
            with open(self.post_file[1], 'a', encoding='utf-8', errors='replace') as post_file:
                post_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def add_supporting_file_reference(self, file_type, relative_path, log_header=True):
        new_supporting_file_path = (
           self.default_path_header if log_header else self.base_path
        ) + relative_path
        for supporting_file_type,supporting_file_path in self.supporting_files:
            if supporting_file_path == new_supporting_file_path:
                raise Exception('Attempting to add supporting file reference with path ' + new_supporting_file_path + ' but file already exists with path ' + supporting_file_path)
        self.supporting_files.append((file_type, new_supporting_file_path))
        self.to_dict()

    def add_supporting_absolute_file_reference(self, file_type, absolute_path):
        for supporting_file_type,supporting_file_path in self.supporting_files:
            if supporting_file_path == absolute_path:
                raise Exception('Attempting to add supporting file reference with absolute path ' + absolute_path + ' but file already exists with path ' + supporting_file_path)
        self.supporting_files.append((file_type, absolute_path))
        self.to_dict()

    def add_supporting_file(self, file_type, relative_path, file_contents, end='\n', log_header=True):
        new_supporting_file_path = (
            self.default_path_header if log_header else self.base_path
        ) + relative_path
        for supporting_file_type, supporting_file_path in self.supporting_files:
            if supporting_file_path == new_supporting_file_path:
                raise Exception('Attempting to add supporting file with path ' + new_supporting_file_path + ' but file already exists with path ' + supporting_file_path)
        self.supporting_files.append((file_type, new_supporting_file_path))
        self.to_dict()
        if file_type == 'text':
            with open(new_supporting_file_path, 'w', encoding='utf-8', errors='replace') as supporting_file:
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
                if supporting_file_type != file_type:
                    raise Exception(
                        'Attempting to append contents of type ' + file_type +
                        ' to file ' + str(supporting_file_path) + ' of type ' + supporting_file_type +
                        ' contents: ' + str(file_contents)
                    )
        if not file_exists:
            raise Exception('Attempting to append to non-existent file, contents of type ' + file_type +
                        ' to file ' + str(existing_supporting_file_path) +
                        ' contents: ' + str(file_contents))
        if file_type == 'text':
            with open(existing_supporting_file_path, 'a', encoding='utf-8', errors='replace') as supporting_file:
                supporting_file.write(file_contents + end)
        else:
            raise Exception('Unsupported File Type')

    def add_child(self, action_logger):
        self.children.append(action_logger)
        self.to_dict()

    def get_id(self):
        return self.id

    def get_type(self):
        return self.type

    def get_action_log_path(self):
        return self.default_path_header + 'action-log.json'

    def get_status(self):
        return self.status

    def set_status(self, status):
        self.status = status
        self.to_dict()
    
    def set_summary(self, summary):
        self.summary = summary

    def get_script_counter(self):
        return self.script_counter

    def get_script_log_folder(self):
        return self.script_log_folder

    def set_script_log_folder(self, script_log_folder_path):
        self.script_log_folder = script_log_folder_path
        self.to_dict()
