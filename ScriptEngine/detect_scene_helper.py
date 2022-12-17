import cv2
import numpy as np

from script_engine_utils import masked_mse
from image_matcher import ImageMatcher

class DetectSceneHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_match(sceneAction, screencap_im, dir_path, logs_path):
        screencap_mask = sceneAction["actionData"]["positiveExamples"][0]["mask"]
        screencap_mask_single_channel = sceneAction["actionData"]["positiveExamples"][0]["mask_single_channel"]
        mask_size = np.count_nonzero(screencap_mask_single_channel)
        if screencap_im.shape != screencap_mask.shape:
            screencap_im = cv2.resize(
                screencap_im,
                (screencap_mask.shape[1], screencap_mask.shape[0]),
                interpolation=cv2.INTER_AREA
            )
            print('not matching : ', screencap_im.shape, screencap_mask.shape)
        screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)
        screencap_compare = sceneAction["actionData"]["positiveExamples"][0]["img"]
        ssim_coeff = masked_mse(screencap_masked, screencap_compare, mask_size * 3 * 255)
        action_logs_path = logs_path + '-' + str(sceneAction["actionGroup"]) + '-sim-score-' + str(ssim_coeff)
        cv2.imwrite(action_logs_path + '-screencap-masked.png', screencap_masked)
        cv2.imwrite(action_logs_path + '-screencap-compare.png', screencap_compare)

        #TODO if the input is resized the coordinates will not be resized so there may be clicks in the wrong place
        return [{
            'input_type': 'shape',
            'point': [0, 0],
            'shape': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
            'matched_area': screencap_masked,
            'height': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[0],
            'width': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[1],
            'score': ssim_coeff
        }], ssim_coeff
