import sys

sys.path.append(".")
from zipfile import ZipFile
import json
import os
import glob
import datetime
from avd_controller import AVD
from python_host_controller import python_host

def parse_script_file(action_rows_file_obj, props_file_obj):
    with action_rows_file_obj as action_rows_file:
        action_rows = json.load(action_rows_file)
    with props_file_obj as props_file:
        props = json.load(props_file)
    return {
        'actionRows': action_rows,
        'props': props,
    }

def parse_zip(script_file_path):
    # is_backslash_system = script_file_path.count('/') > script_file_path.count('\\')
    dir_path = os.path.splitext(script_file_path)[0]
    if os.path.splitext(script_file_path)[1] == '.zip':
        script_path = os.path.splitext(os.path.basename(script_file_path))[0]
        with ZipFile(script_file_path) as script_zip:
            action_rows_file_obj = script_zip.open(script_path + '/actions/actionRows.json', 'r')
            props_file_obj = script_zip.open(script_path + '/props.json', 'r')
            script_obj = parse_script_file(action_rows_file_obj,props_file_obj)
            script_obj['props']["script_path"] = script_file_path
            script_obj['props']["script_name"] = script_path
            script_obj['include'] = {}
            for file_path_split in filter(lambda namelist: namelist[-1] == 'props.json',
                                          filter(lambda namelist: len(namelist) == 4,
                                                 filter(lambda namelist: namelist[0] != '__MACOSX',
                                                        map(lambda namelist: namelist.split('/'),
                                                            script_zip.namelist())))):
                file_path_split = file_path_split[:-1]
                include_script_name = file_path_split[-1]
                include_file_path = '/'.join(file_path_split)
                action_rows_file_obj = script_zip.open(include_file_path + '/actions/actionRows.json', 'r')
                props_file_obj = script_zip.open(include_file_path + '/props.json', 'r')
                include_script_obj = parse_script_file(action_rows_file_obj, props_file_obj)
                include_script_obj['props']['script_name'] = include_script_name
                include_script_obj['props']["dir_path"] = '/'.join(dir_path.split('/')[:-1] + include_file_path.split('/'))
                script_obj['include'][include_script_name] = include_script_obj
    else:
        script_path = script_file_path
        action_rows_file_obj = open(script_path + '/actions/actionRows.json', 'r')
        props_file_obj = open(script_path + '/props.json', 'r')
        script_obj = parse_script_file(action_rows_file_obj, props_file_obj)
        script_obj['props']["script_path"] = script_file_path
        script_obj['props']["script_name"] = script_path.split('/')[-1]
        script_obj['include'] = {}
        for include_file_path in glob.glob(script_path + '/include/*/'):
            include_file_path = include_file_path[:-1]
            include_script_name = include_file_path.split('/')[-1]
            action_rows_file_obj = open(include_file_path + '/actions/actionRows.json', 'r')
            props_file_obj = open(include_file_path + '/props.json', 'r')
            include_script_obj = parse_script_file(action_rows_file_obj, props_file_obj)
            include_script_obj['props']['script_name'] = include_script_name.split('/')[-1]
            include_script_obj['props']["dir_path"] = '/'.join(include_file_path.split('/')[:-1])
            script_obj['include'][include_script_name] = include_script_obj
    props = script_obj['props']
    script_obj['props']['python_host'] = python_host(props)
    script_obj['props']['avd'] = AVD(props['adbPath'], props['emulatorPath'], props['deviceName'],
                                     script_obj['props']['python_host'])
    script_obj['props']["dir_path"] = dir_path
    script_obj['props']["start_time"] = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    return script_obj
