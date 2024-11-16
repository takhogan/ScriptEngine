import cv2
import numpy as np

from script_engine_utils import masked_mse
from script_logger import ScriptLogger
from image_matcher import ImageMatcher
script_logger = ScriptLogger()

class DetectSceneHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_match(
            sceneAction,
            screencap_im_bgr,
            floating_detect_obj,
            fixed_detect_obj,
            check_image_scale=True,
            output_cropping=None):
        screencap_compare = fixed_detect_obj["img"]
        scene_screencap_mask = fixed_detect_obj["mask"]
        scene_screencap_mask_single_channel = fixed_detect_obj["mask_single_channel"]
        screencap_outputmask_bgr = floating_detect_obj["outputMask"]
        object_mask_single_channel = floating_detect_obj["mask_single_channel"]


        mask_size = np.count_nonzero(scene_screencap_mask_single_channel)
        original_height,original_width = screencap_im_bgr.shape[0],screencap_im_bgr.shape[1]

        needs_rescale = screencap_im_bgr.shape != scene_screencap_mask.shape
        pre_log = 'Performing fixed location detectScene template comparison.' +\
            'Expected input size is {} input image input size is {}'.format(
                str(scene_screencap_mask.shape),
                str(screencap_im_bgr.shape)
            )
        script_logger.log(pre_log)
        if needs_rescale:
            screencap_im_bgr = cv2.resize(
                screencap_im_bgr,
                (scene_screencap_mask.shape[1], scene_screencap_mask.shape[0]),
                interpolation=cv2.INTER_AREA
            )
            resize_log = 'Resized input to expected size {}'.format(str(screencap_im_bgr.shape))
            pre_log += '\n' + resize_log
            script_logger.log(resize_log)
        mid_log_1 = 'Masking input'
        script_logger.log(mid_log_1)
        screencap_masked = cv2.bitwise_and(screencap_im_bgr, scene_screencap_mask)

        mid_log_2 = 'Performing masked MSE'
        script_logger.log(mid_log_2)

        ssim_coeff = masked_mse(screencap_masked, screencap_compare, mask_size * 3 * 255)

        mid_log_3 = 'Masked MSE returned a ssim coef of {}'.format(ssim_coeff)
        script_logger.log(mid_log_3)

        object_h,object_w = object_mask_single_channel.shape
        location_val = sceneAction["actionData"]["sceneLocation"][0]
        match_img_bgr = screencap_im_bgr[location_val[1]:location_val[1] + object_h, location_val[0]:location_val[0] + object_w].copy()

        mid_log_4 = 'Applying mask to output. Output has size of {}. Output mask has size of {}'.format(str(match_img_bgr.shape), str(screencap_outputmask_bgr.shape))
        script_logger.log(mid_log_4)

        match_img_bgr = cv2.bitwise_and(match_img_bgr, screencap_outputmask_bgr)

        mid_log_5 = ''
        if output_cropping is not None:
            match_img_bgr = match_img_bgr[output_cropping[0][1]:output_cropping[1][1],
            output_cropping[0][0]:output_cropping[1][0]]
            mid_log_5 = 'Cropping masked output'
            script_logger.log(mid_log_5)

        post_log = 'Final output image size is {}'.format(str(match_img_bgr.shape))
        script_logger.log(post_log)

        # cv2.rectangle(
        #     screencap_im_bgr,
        #     location_val,
        #     (
        #         location_val[0] + object_w,
        #         location_val[1] + object_h,
        #     ), (0, 0, int(255 * ssim_coeff)), 2
        # )

        result_im_bgr = ImageMatcher.create_result_im(
            sceneAction,
            screencap_im_bgr,
            object_mask_single_channel,
            [(location_val, ssim_coeff)],
            None,
            needs_rescale
        )

        if script_logger.get_log_level() == 'info':
            matching_overlay_relative_path = 'detectScene-matchOverlayed.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + matching_overlay_relative_path, result_im_bgr)
            script_logger.get_action_log().set_post_file('image', matching_overlay_relative_path)
            masked_img_relative_path = 'detectScene-maskApplied.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + masked_img_relative_path, screencap_masked)
            script_logger.get_action_log().add_supporting_file_reference('image', masked_img_relative_path)
            comparison_img_relative_path = 'detectScene-comparisonImage.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + comparison_img_relative_path, screencap_compare)
            script_logger.get_action_log().add_supporting_file_reference('image', comparison_img_relative_path)

        output_mask_single_channel = sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].copy()
        post_post_log = ''
        if needs_rescale:
            width_translation = original_width / int(sceneAction["actionData"]["sourceScreenWidth"])
            height_translation = original_height / int(sceneAction["actionData"]["sourceScreenHeight"])
            location_val = (location_val[0] * width_translation, location_val[1] * height_translation)

            post_post_log = 'Remapping scene location for resized input'
            script_logger.log(post_post_log)
            # script_logger.log('output shape', output_mask_single_channel.shape, (original_height, original_width))
            # output_mask_single_channel = cv2.resize(
            #     output_mask_single_channel,
            #     (original_height, original_width),
            #     interpolation=cv2.INTER_AREA
            # )
        final_log = 'Matched scene at location {}'.format(str(location_val))
        script_logger.log(final_log)

        script_logger.get_action_log().add_supporting_file(
            'text',
            'detectScene-log.txt',
            pre_log + '\n' + mid_log_1 + '\n' + mid_log_2 + '\n' +\
            mid_log_3 + '\n' + mid_log_4 + '\n' + mid_log_5 + '\n' +\
            post_log + '\n' + (post_post_log + '\n' if post_post_log != '' else '') +\
            final_log
        )

        return [{
            'input_type': 'shape',
            'point': location_val,
            'shape': output_mask_single_channel,
            'matched_area': match_img_bgr,
            'height': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[0],
            'width': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[1],
            'original_image': sceneAction['input_obj']['original_image'],
            'original_height': sceneAction['input_obj']['original_height'],
            'original_width': sceneAction['input_obj']['original_width'],
            'score': ssim_coeff,
            'n_matches' : 1
        }], ssim_coeff
