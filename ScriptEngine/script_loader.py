import json
import os
import sys
import glob
import cv2
import numpy as np

from zipfile import ZipFile
from ScriptEngine.common.logging.script_logger import ScriptLogger
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
        script_zip=None,
        script_path_in_zip=None):
    script_logger.log('SCRIPT LOAD: loading script ', script_name)
    def read_and_set_image(example, action, img_type):
        if img_type in example and not example[img_type] is None:
            script_logger.log(dir_path, example[img_type])
            example[img_type] = cv2.imread(dir_path + '/' + example[img_type])
    def read_json_file(file_path):
        """Read JSON file from either zip or filesystem"""
        if script_zip is not None:
            # Read from zip file
            with script_zip.open(file_path, 'r') as f:
                return json.load(f)
        else:
            # Read from filesystem
            with open(file_path, 'r') as f:
                return json.load(f)
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
                positive_examples = action["actionData"]["positiveExamples"]
                # Normalize legacy format (flat list with detectType) to new format (pairs with floatingObject/fixedObject)
                if positive_examples and "floatingObject" not in positive_examples[0]:
                    first_floating = None
                    first_fixed = None
                    for positive_example in positive_examples:
                        if positive_example.get("detectType") == "floatingObject":
                            first_floating = positive_example
                            break
                    for positive_example in positive_examples:
                        if positive_example.get("detectType") == "fixedObject":
                            first_fixed = positive_example
                            break
                    pair = {"type": "templateMatchImage"}
                    if first_floating is not None:
                        pair["floatingObject"] = first_floating
                    if first_fixed is not None:
                        pair["fixedObject"] = first_fixed
                    action["actionData"]["positiveExamples"] = [pair]
                # Load images for each pair (new format only after normalization)
                for example_index, pair in enumerate(action["actionData"]["positiveExamples"]):
                    for obj_key in ["floatingObject", "fixedObject"]:
                        if obj_key not in pair:
                            continue
                        positive_example = pair[obj_key]
                        if "mask" in positive_example and positive_example["mask"] is not None:
                            read_and_set_image(positive_example, action, "mask")
                            positive_example["mask_single_channel"] = np.uint8(cv2.cvtColor(positive_example["mask"].copy(), cv2.COLOR_BGR2GRAY))
                        read_and_set_image(positive_example, action, "containedAreaMask")
                        read_and_set_image(positive_example, action, "img")
                        set_output_mask(positive_example, '', include_contained_area, exclude_matched_area)
            
            # Handle mouseInteractionAction and mouseMoveAction point lists
            if action["actionName"] in {"mouseInteractionAction", "mouseMoveAction"}:
                if "actionData" in action and "sourcePointList" in action["actionData"]:
                    source_point_list = action["actionData"]["sourcePointList"]
                    if isinstance(source_point_list, str):
                        # It's a file path, read the JSON file
                        if script_zip is not None and script_path_in_zip is not None:
                            # For zip files, construct the path within the zip
                            # script_path_in_zip is the base path within the zip (e.g., "scriptname" or "scriptname/include/includename")
                            # Normalize the path by removing leading slashes from source_point_list
                            normalized_path = source_point_list.lstrip('/')
                            zip_path = (script_path_in_zip + '/' + normalized_path).replace('\\', '/')
                            if zip_path in script_zip.namelist():
                                action["actionData"]["sourcePointList"] = read_json_file(zip_path)
                        elif script_zip is None:
                            # For regular files
                            file_path = dir_path + '/' + source_point_list
                            if os.path.exists(file_path):
                                action["actionData"]["sourcePointList"] = read_json_file(file_path)
                
                # For mouseMoveAction, also handle targetPointList
                if action["actionName"] == "mouseMoveAction":
                    if "actionData" in action and "targetPointList" in action["actionData"]:
                        target_point_list = action["actionData"]["targetPointList"]
                        if isinstance(target_point_list, str):
                            # It's a file path, read the JSON file
                            if script_zip is not None and script_path_in_zip is not None:
                                # For zip files, construct the path within the zip
                                # Normalize the path by removing leading slashes from target_point_list
                                normalized_path = target_point_list.lstrip('/')
                                zip_path = (script_path_in_zip + '/' + normalized_path).replace('\\', '/')
                                if zip_path in script_zip.namelist():
                                    action["actionData"]["targetPointList"] = read_json_file(zip_path)
                            elif script_zip is None:
                                # For regular files
                                file_path = dir_path + '/' + target_point_list
                                if os.path.exists(file_path):
                                    action["actionData"]["targetPointList"] = read_json_file(file_path)

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
            # Try /actionRows.json first, then /actions/actionRows.json
            action_rows_path = script_path + '/actionRows.json'
            if action_rows_path not in script_zip.namelist():
                action_rows_path = script_path + '/actions/actionRows.json'
            action_rows_file_obj = script_zip.open(action_rows_path, 'r')
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
                script_zip,
                script_path
            )
            use_library_scripts = script_obj['props']['deploymentToLibrary'] == 'true'
            if use_library_scripts:
                script_logger.log('mode use_library_scripts not supported for zip file, extract zip file to a directory')
                sys.exit(1)
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
                # Try /actionRows.json first, then /actions/actionRows.json
                action_rows_path = include_file_path + '/actionRows.json'
                if action_rows_path not in script_zip.namelist():
                    action_rows_path = include_file_path + '/actions/actionRows.json'
                action_rows_file_obj = script_zip.open(action_rows_path, 'r')
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
                    include_dir_path,
                    script_zip,
                    include_file_path
                )
                include_script_obj['props']['script_name'] = include_script_name
                include_script_obj['props']["dir_path"] = include_dir_path
                include_scripts[include_script_name] = include_script_obj
    else:
        script_path = script_file_path
        # Try /actionRows.json first, then /actions/actionRows.json
        action_rows_path = script_path + '/actionRows.json'
        if not os.path.exists(action_rows_path):
            action_rows_path = script_path + '/actions/actionRows.json'
        action_rows_file_obj = open(action_rows_path, 'r')
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
            dir_path,
            None,
            None
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
            # Try /actionRows.json first, then /actions/actionRows.json
            action_rows_path = include_parse_file_path + '/actionRows.json'
            if not os.path.exists(action_rows_path):
                action_rows_path = include_parse_file_path + '/actions/actionRows.json'
            action_rows_file_obj = open(action_rows_path, 'r')
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
                include_parse_file_path,
                None,
                None
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
