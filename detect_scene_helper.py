import cv2
import numpy as np

from script_engine_utils import masked_mse
from image_matcher import ImageMatcher

class DetectSceneHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_match(sceneAction, screencap_im, dir_path, logs_path):
        print(sceneAction["actionData"]["positiveExamples"][0])
        screencap_mask = sceneAction["actionData"]["positiveExamples"][0]["mask"]
        screencap_mask_single_channel = sceneAction["actionData"]["positiveExamples"][0]["mask_single_channel"]
        mask_size = np.count_nonzero(screencap_mask_single_channel)
        # print(action['actionData']['img'])
        # print(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"])
        # print(self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["img"])
        # print(screencap_im.shape)
        # print(screencap_mask.shape)
        screencap_masked = cv2.bitwise_and(screencap_im, screencap_mask)
        screencap_compare = sceneAction["actionData"]["positiveExamples"][0]["img"]
        ssim_coeff = masked_mse(screencap_masked, screencap_compare, mask_size * 3 * 255)
        cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-masked.png', screencap_masked)
        cv2.imwrite(logs_path + 'sim-score-' + str(ssim_coeff) + '-screencap-compare.png', screencap_compare)
        # if "location" not in sceneAction["actionData"]:
        #     print(screencap_mask_single_channel.shape)
        #     for row_index in range(0, screencap_mask_single_channel.shape[0]):
        #         for col_index in range(0, screencap_mask_single_channel.shape[1]):
        #             if screencap_mask_single_channel[row_index, col_index] > 0:
        #                 print('please update detectScene location: ', col_index, ', ', row_index)
        #                 exit(0)
        #     exit(0)
        return [{
            'input_type': 'shape',
            'point': [0, 0],
            'shape': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"],
            'height': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[0],
            'width': sceneAction["actionData"]["positiveExamples"][0]["outputMask_single_channel"].shape[1],
            'score': ssim_coeff
        }], ssim_coeff
