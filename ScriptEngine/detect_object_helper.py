import cv2
import sys

sys.path.append("..")
from script_engine_utils import generate_context_switch_action
from script_execution_state import ScriptExecutionState
from image_matcher import ImageMatcher
from detect_scene_helper import DetectSceneHelper

class DetectObjectHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_detect_area(action, state):
        screencap_im_bgr = None
        match_point = None
        var_name = action["actionData"]["inputExpression"]
        if var_name is not None and len(var_name) > 0:
            print('detectObject-' + str(action["actionGroup"]), ' fetching variable ', var_name, 'from state')
            input_area = eval(var_name, state.copy())
            if len(input_area) > 0:
                if action["actionData"]["targetContext"] == "detectResult":
                    if input_area["input_type"] == "rectangle":
                        pass
                        # point_choice = (input_area["point"][0] + width_coord, input_area["point"][1] + height_coord)
                    elif input_area["input_type"] == "shape":
                        screencap_im_bgr = input_area["matched_area"]
                        match_point = (
                            input_area["point"][0],
                            input_area["point"][1]
                        )
        else:
            print('detectObject-' + str(action["actionGroup"]), ' no input expression')
        return screencap_im_bgr, match_point

    @staticmethod
    def update_update_queue(action, state, context, matches, update_queue):
        state_copy = state.copy()
        context_copy = context.copy()
        print('updating update queue')
        if len(matches) > 0:

            if str(action['actionData']['maxMatches']).isdigit():
                max_matches = int(action['actionData']['maxMatches'])
            else:
                max_matches = eval(action['actionData']['maxMatches'], state.copy())
            excess_matches = len(matches) - max_matches
            if excess_matches > 0:
                print('truncated {} excess matches'.format(excess_matches))
            for match in matches[1:max_matches]:
                switch_action = generate_context_switch_action(action["childGroups"], state_copy, context_copy, {
                    "state": {
                        action['actionData']['outputVarName']: match
                    }
                })
                update_queue.append(
                    [
                        'append',
                        'run_queue',
                        None,
                        switch_action
                    ]
                )
            update_queue.append(
                [
                    'update',
                    'state',
                    action['actionData']['outputVarName'],
                    matches[0]
                ]
            )
            update_queue.append(
                [
                    'update',
                    'status',
                    None,
                    ScriptExecutionState.SUCCESS
                ]
            )
            status = ScriptExecutionState.SUCCESS
        else:
            update_queue.append(
                [
                    'update',
                    'status',
                    None,
                    ScriptExecutionState.FAILURE
                ]
            )
            status = ScriptExecutionState.FAILURE
        return update_queue, status

    @staticmethod
    def handle_detect_object(
            action,
            screencap_im_bgr,
            state,
            context,
            run_queue,
            match_point=None,
            check_image_scale=False,
            script_mode='train',
            log_level='info',
            logs_path='./logs',
            dir_path='./logs',
            lazy_eval=False
    ):
        print('inside detectObject')
        screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
        if script_mode == "train" and log_level == 'info':
            cv2.imwrite(logs_path + '-search_img.png', screencap_search_bgr)
        is_detect_object_first_match = (
                action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
            'matchMode'] == 'firstMatch'
        )
        # if is match mode firstMatch or is a detectScene
        if is_detect_object_first_match or \
                action['actionData']['detectActionType'] == 'detectScene':
            matches, ssim_coeff = DetectSceneHelper.get_match(
                action,
                screencap_im_bgr.copy(),
                action["actionData"]["positiveExamples"][0]["sceneimg"],
                action["actionData"]["positiveExamples"][0]["scenemask"],
                action["actionData"]["positiveExamples"][0]["scenemask_single_channel"],
                action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                action["actionData"]["positiveExamples"][0]["outputMask"],
                dir_path,
                logs_path,
                log_level=log_level,
                check_image_scale=check_image_scale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                 "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                 ) else None
            )
            if ssim_coeff < float(action["actionData"]["threshold"]):
                matches = []
                if action['actionData']['detectActionType'] == 'detectScene':
                    print('detectObject-' + str(
                        action["actionGroup"]) + ' FAILED, detect mode detect scene, match % : ' + str(ssim_coeff))
                else:
                    print('detectObject-' + str(
                        action["actionGroup"]) + ' first match failed, detect mode detect object, match % : ',
                          str(ssim_coeff))
            else:
                print('detectObject-' + str(
                    action["actionGroup"]) + ' SUCCESS, detect mode detect scene, match % :' + str(ssim_coeff))

        # if is a detectObject and matchMode is bestMatch
        # or is a detectObject and matchMode firstMatch but did not find a firstmatch
        if (action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
            'matchMode'] == 'bestMatch') or \
                (is_detect_object_first_match and len(matches) == 0):
            matches = ImageMatcher.template_match(
                action,
                screencap_im_bgr,
                screencap_search_bgr,
                action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                action["actionData"]["positiveExamples"][0]["outputMask"],
                action["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
                action['actionData']['detectorName'],
                logs_path,
                script_mode,
                match_point,
                log_level=log_level,
                check_image_scale=check_image_scale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                 "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                 ) else None,
                threshold=float(action["actionData"]["threshold"]),
                use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
            )
        update_queue = []
        update_queue, status = DetectObjectHelper.update_update_queue(
            action, state, context, matches, update_queue
        )
        if lazy_eval:
            return status, update_queue
        else:
            return action, status, state, context, run_queue, update_queue
