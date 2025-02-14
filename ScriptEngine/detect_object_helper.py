import time

start_time = time.time()

import cv2
import sys
import numpy as np
sys.path.append("..")
from script_engine_utils import generate_context_switch_action, state_eval
from script_execution_state import ScriptExecutionState
from image_matcher import ImageMatcher
from detect_scene_helper import DetectSceneHelper
from script_logger import ScriptLogger,thread_local_storage
script_logger = ScriptLogger()
print(f"detect object imports took {time.time() - start_time:.2f} seconds", flush=True)

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
            if max_matches > 1:
                matches = matches[:max_matches]
            else:
                matches = matches[0]
            # for match_index, match in enumerate(matches[1:max_matches]):
            #     switch_action = generate_context_switch_action(action["childGroups"], state_copy, context_copy, {
            #         "state": {
            #             action['actionData']['outputVarName']: match
            #         }
            #     })
            #     update_queue.append(
            #         [
            #             'append',
            #             'run_queue',
            #             None,
            #             switch_action
            #         ]
            #     )
            #     context_switch_log = 'Creating contextSwitchAction-' +\
            #                       str(switch_action['actionGroup']) + ' for match number ' + str(match_index) +\
            #                       ' with children: ' + str(action["childGroups"])
            #     update_update_queue_log += context_switch_log + '\n'
            #     script_logger.log(context_switch_log)
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

        script_logger.get_action_log().add_supporting_file(
            'text',
            'detect_result.txt',
            ''
        )
        fixed_detect_obj = None
        for positive_example in action["actionData"]["positiveExamples"]:
            if positive_example["detectType"] == "fixedObject":
                fixed_detect_obj = positive_example
                break
        floating_detect_obj = None
        for positive_example in action["actionData"]["positiveExamples"]:
            if positive_example["detectType"] == "floatingObject":
                floating_detect_obj = positive_example
                break
        is_detect_object_first_match = (
                action['actionData']['detectActionType'] == 'floatingObject' and action['actionData'][
            'matchMode'] == 'firstMatch'
        )

        log_objs = {
            'base': (screencap_im_bgr.copy(), floating_detect_obj),
            'fixedObject' : None,
            'floatingObject' : None
        }


        # if is match mode firstMatch or is a detectScene
        detect_scene_result_log = ''
        if is_detect_object_first_match or \
                action['actionData']['detectActionType'] == 'fixedObject':
            detect_scene_pre_log = 'Performing detectActionType detect scene'
            script_logger.log(detect_scene_pre_log)
            detect_scene_result_log += detect_scene_pre_log + '\n'

            needs_rescale = screencap_im_bgr.shape != fixed_detect_obj["mask"].shape
            matches, ssim_coeff, screencap_masked = DetectSceneHelper.get_match(
                action,
                screencap_im_bgr,
                floating_detect_obj,
                fixed_detect_obj,
                needs_rescale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                    (action['actionData']["excludeMatchedAreaFromOutput"] if 'excludeMatchedAreaFromOutput' in action['actionData'] else False)
                ) else None
            )
            log_objs['fixedObject'] = (
                matches, screencap_masked, fixed_detect_obj, needs_rescale
            )
            if matches[0]['score'] < float(action["actionData"]["threshold"]):
                matches = []
                if action['actionData']['detectActionType'] == 'fixedObject':
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
        if (action['actionData']['detectActionType'] == 'floatingObject' and action['actionData'][
            'matchMode'] == 'bestMatch') or \
                (is_detect_object_first_match and len(matches) == 0):
            detect_object_result_log = 'Performing detectActionType detect object'
            script_logger.log(detect_object_result_log)
            matches, match_result = ImageMatcher.template_match(
                action,
                screencap_im_bgr,
                floating_detect_obj,
                action['actionData']['detectorName'],
                script_mode,
                match_point,
                check_image_scale=check_image_scale,
                output_cropping=action["actionData"]["maskLocation"] if
                (action["actionData"]["maskLocation"] != 'null' and
                    (action['actionData']["excludeMatchedAreaFromOutput"] if 'excludeMatchedAreaFromOutput' in action['actionData'] else False)
                ) else None,
                threshold=float(action["actionData"]["threshold"]),
                use_color=action["actionData"]["useColor"] == "true" or action["actionData"]["useColor"]
            )

            log_objs['floatingObject'] = (
                matches, match_result
            )

        script_logger.get_action_log().append_supporting_file(
            'text',
            'detect_result.txt',
            (detect_scene_result_log + '\n' if detect_scene_result_log != '' else '') +
            detect_object_result_log
        )
        script_logger.log('Completed handle detect object')
        return action, matches, log_objs


    @staticmethod
    def create_detect_action_log_images(thread_script_logger, action, log_obj):
        thread_local_storage.script_logger = thread_script_logger
        script_logger = ScriptLogger.get_logger()
        script_logger.log('Creating log images for action', action["actionGroup"], script_logger.get_action_log().name)

        (screencap_im_bgr, floating_detect_obj) = log_obj['base']

        # Check if image is valid before writing
        if screencap_im_bgr is None or not isinstance(screencap_im_bgr, np.ndarray):
            script_logger.log('Invalid input image format, skipping log image creation')
            return
        
        if screencap_im_bgr.dtype not in [np.uint8, np.uint16]:
            script_logger.log('input image corrupted')

        input_image_relative_path = 'detectObject-inputImage.png'
        script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + input_image_relative_path)
        cv2.imwrite(script_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
        script_logger.log('Successfully wrote to file: ' + input_image_relative_path)
        script_logger.get_action_log().set_pre_file(
            'image',
            input_image_relative_path
        )

        script_logger.log('Writing template image')


        template_image_relative_path = 'templateImage.png'
        script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + template_image_relative_path)
        cv2.imwrite(
            script_logger.get_log_path_prefix() + template_image_relative_path, floating_detect_obj["img"]
        )
        script_logger.log('Successfully wrote to file: ' + template_image_relative_path)
        script_logger.get_action_log().add_supporting_file_reference(
            'image',
            template_image_relative_path
        )


        if log_obj['fixedObject'] is not None:
            (matches, screencap_masked, fixed_detect_obj, needs_rescale) = log_obj['fixedObject']
            result_im_bgr = ImageMatcher.create_result_im(
                action,
                screencap_im_bgr,
                floating_detect_obj["mask_single_channel"],
                matches,
                None,
                needs_rescale
            )

            matching_overlay_relative_path = 'detectScene-matchOverlayed.png'
            script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + matching_overlay_relative_path)
            cv2.imwrite(script_logger.get_log_path_prefix() + matching_overlay_relative_path, result_im_bgr)
            script_logger.log('Successfully wrote to file: ' + matching_overlay_relative_path)
            script_logger.get_action_log().set_post_file('image', matching_overlay_relative_path)

            masked_img_relative_path = 'detectScene-maskApplied.png'
            script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + masked_img_relative_path)
            cv2.imwrite(script_logger.get_log_path_prefix() + masked_img_relative_path, screencap_masked)
            script_logger.log('Successfully wrote to file: ' + masked_img_relative_path)
            script_logger.get_action_log().add_supporting_file_reference('image', masked_img_relative_path)

            comparison_img_relative_path = 'detectScene-comparisonImage.png'
            script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + comparison_img_relative_path)
            cv2.imwrite(script_logger.get_log_path_prefix() + comparison_img_relative_path, fixed_detect_obj["img"])
            script_logger.log('Successfully wrote to file: ' + comparison_img_relative_path)
            script_logger.get_action_log().add_supporting_file_reference('image', comparison_img_relative_path)

        if log_obj['floatingObject'] is not None:
            (
                matches, match_result
            ) = log_obj['floatingObject']

            result_im_bgr = ImageMatcher.create_result_im(
                action,
                screencap_im_bgr,
                floating_detect_obj["img"],
                matches,
                match_result,
                False
            )

            matching_overlay_relative_path = 'detectObject-matchOverlayed.png'
            script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + matching_overlay_relative_path)
            cv2.imwrite(script_logger.get_log_path_prefix() + matching_overlay_relative_path, result_im_bgr)
            script_logger.log('Successfully wrote to file: ' + matching_overlay_relative_path)
            script_logger.get_action_log().set_post_file('image', matching_overlay_relative_path)

            comparison_img_relative_path = 'detectObject-matchingHeatMap.png'
            script_logger.log('Writing to file: ' + script_logger.get_log_path_prefix() + comparison_img_relative_path)
            cv2.imwrite(script_logger.get_log_path_prefix() + comparison_img_relative_path, match_result * 255)
            script_logger.log('Successfully wrote to file: ' + comparison_img_relative_path)
            script_logger.get_action_log().add_supporting_file_reference('image', comparison_img_relative_path)


    @staticmethod
    def handle_detect_action_result(io_executor, detect_action_result, state, context, run_queue):
        (action, matches, log_obj) = detect_action_result

        if script_logger.get_log_level() == 'info':
            script_logger.log('DetectObjectHelper: starting detect object log thread')
            thread_script_logger = script_logger.copy()
            # DetectObjectHelper.create_detect_action_log_images(thread_script_logger, action, log_obj)
            io_executor.submit(DetectObjectHelper.create_detect_action_log_images, thread_script_logger, action, log_obj)

        if len(matches) > 0:
            status = ScriptExecutionState.SUCCESS
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
            if max_matches > 1:
                matches = matches[:max_matches]
            else:
                matches = matches[0]
            state[action['actionData']['outputVarName']] = matches
        else:
            status = ScriptExecutionState.FAILURE
        return action, status, state, context, run_queue

print(f"detect object module initialization took {time.time() - start_time:.2f} seconds", flush=True)
