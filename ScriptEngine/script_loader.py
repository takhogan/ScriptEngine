import json
import os
import glob
import cv2
import numpy as np

from zipfile import ZipFile
from script_logger import ScriptLogger
script_logger = ScriptLogger()


def set_output_mask(positive_example, img_type_prefix, include_contained_area, exclude_matched_area):
    if include_contained_area and exclude_matched_area:
        if "containedAreaMask" not in positive_example:
            return positive_example
        positive_example[img_type_prefix + "outputMask"] = positive_example[
            img_type_prefix + "containedAreaMask"].copy()
    elif include_contained_area and not exclude_matched_area:
        if "containedAreaMask" not in positive_example or "mask" not in positive_example:
            return positive_example
        positive_example[img_type_prefix + "outputMask"] = cv2.bitwise_or(
            positive_example[img_type_prefix + "mask"].copy(),
            positive_example[img_type_prefix + "containedAreaMask"].copy()
        )
    elif not include_contained_area and exclude_matched_area:
        if "containedAreaMask" not in positive_example or "mask" not in positive_example:
            return positive_example
        positive_example[img_type_prefix + "outputMask"] = cv2.bitwise_and(
            positive_example[img_type_prefix + "mask"].copy(),
            positive_example[img_type_prefix + "containedAreaMask"].copy()
        )
    else:
        if "mask" not in positive_example:
            return positive_example
        positive_example[img_type_prefix + "outputMask"] = positive_example[img_type_prefix + "mask"].copy()
    positive_example[img_type_prefix + "outputMask_single_channel"] = np.uint8(
        cv2.cvtColor(positive_example[img_type_prefix + "outputMask"].copy(), cv2.COLOR_BGR2GRAY)
    )
    return positive_example

def script_to_string(script_name, action_rows):
    def childGroupLink_to_child(childGroupLink):
        if not childGroupLink["type"] == "outOfAttemptsHandler":
            return action_rows[childGroupLink["destRowIndex"]]["actions"][childGroupLink["destActionIndex"]]
        return None
    def dfs(action, depth, visited, unpack_childLink=True):
        string = ' ' * depth + str(action["actionName"]) + "-" + str(action["actionGroup"]) + '\n'
        for childGroupLink in action["childGroups"]:
            if unpack_childLink:
                child = childGroupLink_to_child(childGroupLink)
            else:
                child = childGroupLink
            if child is None:
                continue
            link_key = str(action["actionGroup"]) + "-" + str(child["actionGroup"])
            if link_key in visited:
                continue
            else:
                visited.add(link_key)
            string += dfs(child, depth + 1, visited)
        return string
    if len(action_rows) > 0:
        return dfs({
            "actionName" : "script",
            "actionGroup" : script_name,
            "childGroups" : action_rows[0]["actions"]
        }, 0, set(), unpack_childLink=False)
    else:
        return "script-" + script_name
def parse_script_file(
        script_name,
        action_rows_file_obj,
        props_file_obj,
        inputs_file_obj,
        outputs_file_obj,
        dir_path,
        script_zip=None):
    script_logger.log('SCRIPT LOAD: loading script ', script_name)
    def read_and_set_image(example, action, img_type):
        if img_type in example and not example[img_type] is None:
            script_logger.log(dir_path, example[img_type])
            example[img_type] = cv2.imread(dir_path + '/' + example[img_type])
    with action_rows_file_obj as action_rows_file:
        action_rows = json.load(action_rows_file)
    script_logger.log(script_to_string(script_name, action_rows))
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
                include_contained_area = (action["actionData"]['includeContainedAreaInOutput'] if 'includeContainedAreaInOutput' in action["actionData"] else False)
                exclude_matched_area = (action["actionData"]['excludeMatchedAreaFromOutput'] if 'excludeMatchedAreaFromOutput' in action["actionData"] else False)
                for example_index,positive_example in enumerate(action["actionData"]["positiveExamples"]):
                    if "mask" in positive_example and not positive_example["mask"] is None:
                        read_and_set_image(positive_example, action, "mask")
                        positive_example["mask_single_channel"] = np.uint8(cv2.cvtColor(positive_example["mask"].copy(), cv2.COLOR_BGR2GRAY))
                    read_and_set_image(positive_example, action, "containedAreaMask")
                    read_and_set_image(positive_example, action, "img")
                    set_output_mask(positive_example, '', include_contained_area, exclude_matched_area)

    with props_file_obj as props_file:
        props = json.load(props_file)

    with inputs_file_obj as inputs_file:
        inputs = json.load(inputs_file)

    with outputs_file_obj as outputs_file:
        outputs = json.load(outputs_file)

    return {
        'actionRows': action_rows,
        'props': props,
        'inputs' : inputs,
        'outputs' : outputs
    }
# self.use_library = use_library if use_library is not None \
#             else (True if self.props['deploymentToLibrary'] == 'true' else False)
def parse_zip(script_name, system_script=False):
    # is_backslash_system = script_file_path.count('/') > script_file_path.count('\\')
    script_file_path = (
        './scripts/scriptLibrary/' if not system_script else
        './scripts/systemScripts/'
    ) + script_name
    dir_path = os.path.splitext(script_file_path)[0]
    if os.path.splitext(script_file_path)[1] == '.zip':
        script_path = os.path.splitext(os.path.basename(script_file_path))[0]
        # TODO this method is referencing files outside of the zip, will not work if uncompressed file is not there
        with ZipFile(script_file_path) as script_zip:
            action_rows_file_obj = script_zip.open(script_path + '/actions/actionRows.json', 'r')
            props_file_obj = script_zip.open(script_path + '/props.json', 'r')
            inputs_file_obj = script_zip.open(script_path + '/inputs.json', 'r')
            outputs_file_obj = script_zip.open(script_path + '/outputs.json', 'r')
            script_name = script_path
            script_obj = parse_script_file(
                script_name,
                action_rows_file_obj,
                props_file_obj,
                inputs_file_obj,
                outputs_file_obj,
                dir_path,
                script_zip
            )
            use_library_scripts = script_obj['props']['deploymentToLibrary'] == 'true'
            if use_library_scripts:
                script_logger.log('mode use_library_scripts not supported for zip file, extract zip file to a directory')
                exit(1)
            script_obj['props']["script_path"] = script_file_path
            script_obj['props']["script_name"] = script_name
            include_scripts = {}
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
                inputs_file_obj = script_zip.open(include_file_path + '/inputs.json', 'r')
                outputs_file_obj = script_zip.open(include_file_path + '/outputs.json', 'r')
                include_dir_path = '/'.join(dir_path.split('/')[:-1] + include_file_path.split('/'))
                include_script_obj = parse_script_file(
                    include_script_name,
                    action_rows_file_obj,
                    props_file_obj,
                    inputs_file_obj,
                    outputs_file_obj,
                    include_dir_path
                )
                include_script_obj['props']['script_name'] = include_script_name
                include_script_obj['props']["dir_path"] = include_dir_path
                include_scripts[include_script_name] = include_script_obj
    else:
        script_path = script_file_path
        action_rows_file_obj = open(script_path + '/actions/actionRows.json', 'r')
        props_file_obj = open(script_path + '/props.json', 'r')
        inputs_file_obj = open(script_path + '/inputs.json', 'r')
        outputs_file_obj = open(script_path + '/outputs.json', 'r')
        script_name = script_path.split('/')[-1]
        script_obj = parse_script_file(
            script_name,
            action_rows_file_obj,
            props_file_obj,
            inputs_file_obj,
            outputs_file_obj,
            dir_path
        )
        use_library_scripts = script_obj['props']['deploymentToLibrary'] == 'true'
        action_rows_file_obj.close()
        props_file_obj.close()
        inputs_file_obj.close()

        script_obj['props']["script_path"] = script_file_path
        script_obj['props']["script_name"] = script_name
        include_scripts = {}
        for include_file_path in map(lambda filepath: filepath.replace('\\','/'), glob.glob(script_path + '/include/*/')):
            include_file_path = include_file_path[:-1]
            include_script_name = include_file_path.split('/')[-1]
            include_parse_file_path = './scripts/scriptLibrary/' + os.path.basename(include_file_path) \
                if use_library_scripts else include_file_path
            action_rows_file_obj = open(include_parse_file_path + '/actions/actionRows.json', 'r')
            props_file_obj = open(include_parse_file_path + '/props.json', 'r')
            inputs_file_obj = open(include_parse_file_path + '/inputs.json', 'r')
            outputs_file_obj = open(include_parse_file_path + '/outputs.json', 'r')
            include_dir_path = include_file_path
            include_script_obj = parse_script_file(
                include_script_name,
                action_rows_file_obj,
                props_file_obj,
                inputs_file_obj,
                outputs_file_obj,
                include_parse_file_path
            )
            action_rows_file_obj.close()
            props_file_obj.close()
            inputs_file_obj.close()
            include_script_obj['props']['script_name'] = include_script_name
            include_script_obj['props']["dir_path"] = include_dir_path
            include_scripts[include_script_name] = include_script_obj
    script_obj['props']["dir_path"] = dir_path
    include_scripts[script_name] = script_obj
    script_obj['include'] = include_scripts
    return script_obj
