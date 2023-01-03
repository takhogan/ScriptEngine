import cv2
import numpy as np

from script_engine_utils import masked_mse
from image_matcher import ImageMatcher

class DetectSceneHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_match(
            sceneAction,
            screencap_im_bgr,
            screencap_compare,
            scene_screencap_mask,
            scene_screencap_mask_single_channel,
            object_mask_single_channel,
            screencap_outputmask_bgr,
            dir_path,
            logs_path,
            output_cropping=None):
        mask_size = np.count_nonzero(scene_screencap_mask_single_channel)
        if screencap_im_bgr.shape != scene_screencap_mask.shape:
            screencap_im_bgr = cv2.resize(
                screencap_im_bgr,
                (scene_screencap_mask.shape[1], scene_screencap_mask.shape[0]),
                interpolation=cv2.INTER_AREA
            )
            print('not matching : ', screencap_im_bgr.shape, scene_screencap_mask.shape)
        screencap_masked = cv2.bitwise_and(screencap_im_bgr, scene_screencap_mask)
        ssim_coeff = masked_mse(screencap_masked, screencap_compare, mask_size * 3 * 255)

        object_h,object_w = object_mask_single_channel.shape
        location_val = sceneAction["actionData"]["sceneLocation"][0]
        match_img_bgr = screencap_im_bgr[location_val[1]:location_val[1] + object_h, location_val[0]:location_val[0] + object_w].copy()
        match_img_bgr = cv2.bitwise_and(match_img_bgr, screencap_outputmask_bgr)
        print('output_cropping', output_cropping)
        if output_cropping is not None:
            match_img_bgr = match_img_bgr[output_cropping[0][1]:output_cropping[1][1],
            output_cropping[0][0]:output_cropping[1][0]]
        print('match_img_bgr.shape ', match_img_bgr.shape)
        action_logs_path = logs_path + '-' + str(sceneAction["actionGroup"]) + '-sim-score-' + str(ssim_coeff)

        cv2.rectangle(
            screencap_im_bgr,
            location_val,
            (
                location_val[0] + object_w,
                location_val[1] + object_h,
            ), (0, 0, 255), 2
        )

        cv2.imwrite(action_logs_path + '-screencap-matching-overlay.png', screencap_im_bgr)
        cv2.imwrite(action_logs_path + '-screencap-masked.png', screencap_masked)
        cv2.imwrite(action_logs_path + '-screencap-compare.png', screencap_compare)
        #TODO if the input is resized the coordinates will not be resized so there may be clicks in the wrong place
        return [{
            'input_type': 'shape',
            'point': location_val,
            'shape': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
            'matched_area': match_img_bgr,
            'height': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[0],
            'width': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[1],
            'score': ssim_coeff,
            'n_matches' : 1
        }], ssim_coeff
