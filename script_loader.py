import sys

sys.path.append(".")
from zipfile import ZipFile
import json
import os
import glob
import datetime
import cv2
import numpy as np

def parse_script_file(action_rows_file_obj, props_file_obj, dir_path):
    with action_rows_file_obj as action_rows_file:
        action_rows = json.load(action_rows_file)
    for action_row in action_rows:
        for action in action_row["actions"]:
            detect_type_action = action["actionName"] in {
                "clickAction",
                "mouseScrollAction",
                "declareScene",
                "dragLocationSource",
                "dragLocationTarget",
                "detectObject"
            }
            if detect_type_action:
                include_contained_area = 'includeContainedAreaInOutput' in action["actionData"]["detectorAttributes"]
                exclude_matched_area = 'excludeMatchedAreaFromOutput' in action["actionData"]["detectorAttributes"]
                for positive_example in action["actionData"]["positiveExamples"]:
                    positive_example["mask"] = cv2.imread(dir_path + '/' + action["actionData"]["positiveExamples"][0]["mask"])
                    positive_example["mask_single_channel"] = np.uint8(cv2.cvtColor(positive_example["mask"].copy(), cv2.COLOR_BGR2GRAY))
                    positive_example["containedAreaMask"] = cv2.imread(dir_path + '/' + action["actionData"]["positiveExamples"][0]["containedAreaMask"])
                    positive_example["img"] = cv2.imread(dir_path + '/' + action["actionData"]["positiveExamples"][0]["img"])
                    if include_contained_area and exclude_matched_area:
                        positive_example["outputMask"] = positive_example["containedAreaMask"].copy()
                    elif include_contained_area and not exclude_matched_area:
                        positive_example["outputMask"] = cv2.bitwise_or(positive_example["mask"].copy(), positive_example["containedAreaMask"].copy())
                    elif not include_contained_area and exclude_matched_area:
                        positive_example["outputMask"] = cv2.bitwise_and(positive_example["mask"].copy(), positive_example["containedAreaMask"].copy())
                    else:
                        positive_example["outputMask"] = positive_example["mask"].copy()
                    positive_example["outputMask_single_channel"] = np.uint8(cv2.cvtColor(positive_example["outputMask"].copy(), cv2.COLOR_BGR2GRAY))



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
            script_obj = parse_script_file(action_rows_file_obj,props_file_obj, dir_path)
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
                include_dir_path = '/'.join(dir_path.split('/')[:-1] + include_file_path.split('/'))
                include_script_obj = parse_script_file(action_rows_file_obj, props_file_obj, include_dir_path)
                include_script_obj['props']['script_name'] = include_script_name
                include_script_obj['props']["dir_path"] = include_dir_path
                script_obj['include'][include_script_name] = include_script_obj
    else:
        script_path = script_file_path
        action_rows_file_obj = open(script_path + '/actions/actionRows.json', 'r')
        props_file_obj = open(script_path + '/props.json', 'r')
        script_obj = parse_script_file(action_rows_file_obj, props_file_obj, dir_path)
        script_obj['props']["script_path"] = script_file_path
        script_obj['props']["script_name"] = script_path.split('/')[-1]
        script_obj['include'] = {}
        for include_file_path in map(lambda filepath: filepath.replace('\\','/'), glob.glob(script_path + '/include/*/')):
            include_file_path = include_file_path[:-1]
            include_script_name = include_file_path.split('/')[-1]
            action_rows_file_obj = open(include_file_path + '/actions/actionRows.json', 'r')
            props_file_obj = open(include_file_path + '/props.json', 'r')
            include_dir_path = include_file_path
            include_script_obj = parse_script_file(action_rows_file_obj, props_file_obj, include_dir_path)
            include_script_obj['props']['script_name'] = include_script_name.split('/')[-1]
            include_script_obj['props']["dir_path"] = include_dir_path
            script_obj['include'][include_script_name] = include_script_obj
    props = script_obj['props']
    script_obj['props']["dir_path"] = dir_path
    script_obj['props']["start_time"] = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    return script_obj
