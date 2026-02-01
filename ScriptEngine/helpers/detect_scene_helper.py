# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import cv2
import numpy as np
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.constants.script_engine_constants import DETECT_OBJECT_RESULT_MARKER

script_logger = ScriptLogger()

def masked_mse(target_im, compare_im, mask_size):
    return 1 - np.sum(np.square(np.subtract(target_im, compare_im))) / mask_size

def apply_output_mask(screencap_im_bgr, location_val, output_mask_bgr, output_cropping=None):
    object_h, object_w = output_mask_bgr.shape[0], output_mask_bgr.shape[1]
    match_img_bgr = screencap_im_bgr[location_val[1]:location_val[1] + object_h, 
                                      location_val[0]:location_val[0] + object_w].copy()
    
    mid_log = 'Applying mask to output. Output has size of {}. Output mask has size of {}'.format(
        str(match_img_bgr.shape), str(output_mask_bgr.shape)
    )
    script_logger.log(mid_log)
    
    match_img_bgr = cv2.bitwise_and(match_img_bgr, output_mask_bgr)
    
    if output_cropping is not None:
        match_img_bgr = match_img_bgr[output_cropping[0][1]:output_cropping[1][1],
                                      output_cropping[0][0]:output_cropping[1][0]]
        crop_log = 'Cropping masked output'
        script_logger.log(crop_log)
    
    return match_img_bgr

class DetectSceneHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_match(
            sceneAction,
            screencap_im_bgr,
            floating_detect_obj,
            fixed_detect_obj,
            needs_rescale,
            output_cropping=None):
        screencap_compare = fixed_detect_obj["img"]
        scene_screencap_mask = fixed_detect_obj["mask"]
        scene_screencap_mask_single_channel = fixed_detect_obj["mask_single_channel"]
        screencap_outputmask_bgr = floating_detect_obj["outputMask"]
        object_mask_single_channel = floating_detect_obj["mask_single_channel"]


        mask_size = np.count_nonzero(scene_screencap_mask_single_channel)
        original_height,original_width = screencap_im_bgr.shape[0],screencap_im_bgr.shape[1]

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
        
        mid_log_4 = 'Applying output mask'
        mid_log_5 = ''
        match_img_bgr = apply_output_mask(
            screencap_im_bgr, 
            location_val, 
            screencap_outputmask_bgr,
            output_cropping
        )
        if output_cropping is not None:
            mid_log_5 = 'Cropping masked output'

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

        output_mask_single_channel = floating_detect_obj["outputMask_single_channel"].copy()
        post_post_log = ''
        if needs_rescale:
            width_translation = original_width / int(fixed_detect_obj["sourceScreenWidth"])
            height_translation = original_height / int(fixed_detect_obj["sourceScreenHeight"])
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

        # When input is a crop (e.g. from a prior floatingObject), add its origin
        # so output point is in full-screen coordinates (same as floatingObject path).
        match_point = sceneAction['input_obj'].get('match_point', (0, 0))
        output_point = (location_val[0] + match_point[0], location_val[1] + match_point[1])

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
            'point': output_point,
            'shape': output_mask_single_channel,
            'matched_area': match_img_bgr,
            'height': floating_detect_obj["outputMask_single_channel"].shape[0],
            'width': floating_detect_obj["outputMask_single_channel"].shape[1],
            'original_image': sceneAction['input_obj']['original_image'],
            'original_height': sceneAction['input_obj']['original_height'],
            'original_width': sceneAction['input_obj']['original_width'],
            'score': ssim_coeff,
            'n_matches' : 1,
            DETECT_OBJECT_RESULT_MARKER: True
        }], ssim_coeff, screencap_masked
