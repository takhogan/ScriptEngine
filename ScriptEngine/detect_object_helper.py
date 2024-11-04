import cv2
import sys
import numpy as np
sys.path.append("..")
from script_engine_utils import generate_context_switch_action, state_eval
from script_execution_state import ScriptExecutionState
from image_matcher import ImageMatcher
from detect_scene_helper import DetectSceneHelper
from script_logger import ScriptLogger
script_logger = ScriptLogger()


class DetectObjectHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_detect_area(action, state, output_type='matched_area'):
        screencap_im_bgr = None
        original_image = None
        match_point = (0, 0)
        original_width = 0
        original_height = 0
        fixed_scale = False
        var_name = action["actionData"]["inputExpression"]
        mid_log = ''
        if var_name is not None and len(var_name) > 0:
            if var_name not in state:
                pre_log = 'input named {} not in state'.format(var_name)
            else:
                pre_log = 'parsing inputExpression {} from state'.format(var_name)
            script_logger.log(pre_log)
            input_area = state_eval(var_name, {}, state)
            if len(input_area) > 0:
                mid_log = 'input expression exists but unable to parse'
                if input_area["input_type"] == "rectangle":
                    pass
                elif input_area["input_type"] == "shape":
                    if output_type == 'matched_area':
                        screencap_im_bgr = input_area["matched_area"]
                        match_point = (
                            input_area["point"][0],
                            input_area["point"][1]
                        )
                        original_height = input_area["original_height"]
                        original_width = input_area["original_width"]
                        original_image = input_area["original_image"]
                        fixed_scale = True

                        mid_log = 'parsed inputExpression, found matched area and match point {}'.format(
                            str(match_point)
                        )
                    elif output_type == 'matched_pixels':
                        screencap_im_bgr = input_area["matched_area"][np.where(input_area['shape'] > 1)]
                        match_point = (
                            input_area["point"][0],
                            input_area["point"][1]
                        )
                        original_height = input_area["original_height"]
                        original_width = input_area["original_width"]
                        original_image = input_area["original_image"]
                        fixed_scale = True
                        mid_log = 'parsed inputExpression, found matched pixels and match point {}'.format(
                            str(match_point)
                        )
                    script_logger.log(mid_log)

            else:
                pre_log = 'input named {} was in state but it was blank'
                script_logger.log(pre_log)

        else:
            pre_log = 'no input expression'
            script_logger.log(pre_log)

        script_logger.get_action_log().add_supporting_file(
            'text',
            'inputExpression-log.txt',
            pre_log + '\n' +(mid_log if mid_log != '' else '')
        )
        return {
            "screencap_im_bgr" : screencap_im_bgr,
            "match_point" : match_point,
            "original_height" : original_height,
            "original_width" : original_width,
            "original_image" : original_image,
            "fixed_scale" : fixed_scale
        }

    @staticmethod
    def update_update_queue(action, state, context, matches, update_queue):
        state_copy = state.copy()
        context_copy = context.copy()
        script_logger.log('updating update queue')
        if len(matches) > 0:
            update_update_queue_log = ''
            if str(action['actionData']['maxMatches']).isdigit():
                max_matches = int(action['actionData']['maxMatches'])
            else:
                max_matches = state_eval(action['actionData']['maxMatches'], {}, state)
            excess_matches = len(matches) - max_matches
            if excess_matches > 0:
                truncate_log = 'Truncated {} excess matches'.format(excess_matches)
                update_update_queue_log += truncate_log + '\n'
                script_logger.log(truncate_log)
            for match_index, match in enumerate(matches[1:max_matches]):
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
                context_switch_log = 'Creating contextSwitchAction-' +\
                                  str(switch_action['actionGroup']) + ' for match number ' + str(match_index) +\
                                  ' with children: ' + str(action["childGroups"])
                update_update_queue_log += context_switch_log + '\n'
                script_logger.log(context_switch_log)
            script_logger.get_action_log().append_supporting_file(
                'text',
                'detect_result.txt',
                update_update_queue_log
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
            script_mode='train'
    ):
        screencap_im_bgr = action['input_obj']['screencap_im_bgr']
        match_point = action['input_obj']['match_point']
        check_image_scale = not action['input_obj']['fixed_scale']
        script_logger.log('Starting handle detect object')
        if script_logger.get_log_level() == 'info':
            input_image_relative_path = 'detectObject-inputImage.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
            script_logger.get_action_log().set_pre_file(
                'image',
                input_image_relative_path
            )

        script_logger.get_action_log().add_supporting_file(
            'text',
            'detect_result.txt',
            ''
        )
        screencap_search_bgr = action["actionData"]["positiveExamples"][0]["img"]
        if script_mode == "train" and script_logger.get_log_level() == 'info':
            template_image_relative_path = 'templateImage.png'
            cv2.imwrite(
                script_logger.get_log_path_prefix() + template_image_relative_path, screencap_search_bgr
            )
            script_logger.get_action_log().add_supporting_file_reference(
                'image',
                template_image_relative_path
            )
        is_detect_object_first_match = (
                action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
            'matchMode'] == 'firstMatch'
        )
        # if is match mode firstMatch or is a detectScene
        detect_scene_result_log = ''
        if is_detect_object_first_match or \
                action['actionData']['detectActionType'] == 'detectScene':
            detect_scene_pre_log = 'Performing detectActionType detect scene'
            script_logger.log(detect_scene_pre_log)
            detect_scene_result_log += detect_scene_pre_log + '\n'

            matches, ssim_coeff = DetectSceneHelper.get_match(
                action,
                screencap_im_bgr.copy(),
                action["actionData"]["positiveExamples"][0]["sceneimg"],
                action["actionData"]["positiveExamples"][0]["scenemask"],
                action["actionData"]["positiveExamples"][0]["scenemask_single_channel"],
                action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                action["actionData"]["positiveExamples"][0]["outputMask"],
                check_image_scale=check_image_scale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                 "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                 ) else None
            )
            if ssim_coeff < float(action["actionData"]["threshold"]):
                matches = []
                if action['actionData']['detectActionType'] == 'detectScene':
                    detect_scene_result_log = 'detect mode detectScene failed.' +\
                                              ' threshold of {} was greater than similarity score of {}'.format(
                                                  action["actionData"]["threshold"],
                                                  ssim_coeff
                                              )
                else:
                    detect_scene_result_log = 'firstMatch detect mode detectScene failed. switching to detectObject' + \
                                              ' threshold of {} was greater than similarity score of {}'.format(
                                                  action["actionData"]["threshold"],
                                                  ssim_coeff
                                              )
            else:
                detect_scene_result_log = 'detectScene successful.' + \
                                          ' threshold of {} was less than similarity score of {}'.format(
                                              action["actionData"]["threshold"],
                                              ssim_coeff
                                          )
            script_logger.log(detect_scene_result_log)

        # if is a detectObject and matchMode is bestMatch
        # or is a detectObject and matchMode firstMatch but did not find a firstmatch
        detect_object_result_log = ''
        if (action['actionData']['detectActionType'] == 'detectObject' and action['actionData'][
            'matchMode'] == 'bestMatch') or \
                (is_detect_object_first_match and len(matches) == 0):
            detect_object_result_log = 'Performing detectActionType detect object'
            script_logger.log(detect_object_result_log)

            matches = ImageMatcher.template_match(
                action,
                screencap_im_bgr,
                screencap_search_bgr,
                action["actionData"]["positiveExamples"][0]["mask_single_channel"],
                action["actionData"]["positiveExamples"][0]["outputMask"],
                action["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
                action['actionData']['detectorName'],
                script_mode,
                match_point,
                check_image_scale=check_image_scale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                 "excludeMatchedAreaFromOutput" in action['actionData']['detectorAttributes']
                 ) else None,
                threshold=float(action["actionData"]["threshold"]),
                use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
            )

        script_logger.get_action_log().append_supporting_file(
            'text',
            'detect_result.txt',
            (detect_scene_result_log + '\n' if detect_scene_result_log != '' else '') +
            detect_object_result_log
        )
        script_logger.log('Completed handle detect object')
        return action, matches

    @staticmethod
    def handle_detect_action_result(detect_action_result, state, context, run_queue):
        (action, matches) = detect_action_result
        update_queue = []
        # matches are added to the update queue and then added to the state after handle_action returns
        update_queue, status = DetectObjectHelper.update_update_queue(
            action, state, context, matches, update_queue
        )
        return action, status, state, context, run_queue, update_queue
