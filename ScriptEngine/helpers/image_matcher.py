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
import random
from ScriptEngine.common.script_engine_utils import dist
from ScriptEngine.common.types import ScreenPlanImage, TemplateMatch

MINIMUM_MATCH_PIXEL_SPACING = 15
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.log_overlay import Overlay, bgr_to_hex, int_point

script_logger = ScriptLogger()
class ImageMatcher:
    def __init__(self):
        pass

    @staticmethod
    def template_match(detectObject,
                       screencap_im_bgr, floating_detect_obj,
                       detector_name, script_mode, match_point,
                       check_image_scale=True,
                       output_cropping=None,
                       threshold=0.96, use_color=True, use_mask=True) -> tuple[list[ScreenPlanImage], np.ndarray]:
        if detector_name == "pixelDifference":
            matches, match_result = ImageMatcher.produce_template_matches(
                detectObject,
                screencap_im_bgr,
                floating_detect_obj,
                check_image_scale=check_image_scale,
                output_cropping=output_cropping,
                threshold=threshold,
                use_color=use_color,
                use_mask=use_mask
            )
        elif detector_name == "scaledPixelDifference":
            pass
        elif detector_name == "logisticClassifier":
            script_logger.log("logistic detector unimplemented ", level='error')
            exit(0)
        else:
            script_logger.log("detector unimplemented! ", level='error')
            exit(0)

        h, w = floating_detect_obj["outputMask_single_channel"].shape[0:2]

        n_matches = len(matches)
        return [
            ScreenPlanImage(
                input_type='shape',
                point=(
                    (m.point[0] + match_point[0], m.point[1] + match_point[1])
                    if match_point is not None
                    else m.point
                ),
                output_mask=floating_detect_obj["outputMask_single_channel"],
                matched_area=m.matched_area,
                height=h,
                width=w,
                original_image=detectObject['input_obj']['original_image'],
                original_image_blurred=detectObject['input_obj'].get('original_image_blurred'),
                original_height=detectObject['input_obj']['original_height'],
                original_width=detectObject['input_obj']['original_width'],
                score=m.score,
                n_matches=n_matches,
                detect_object_result=True,
            )
            for m in matches
        ], match_result


    @staticmethod
    def produce_template_matches(
            detectObject,
            screencap_im_bgr,
            floating_detect_obj,
            check_image_scale,
            output_cropping=None,
            threshold=0.96, use_color=True, use_mask=True, script_mode='test') -> tuple[list[TemplateMatch], np.ndarray]:
        # https://docs.opencv.org/3.4/de/da9/tutorial_template_matching.html
        screencap_search_bgr = floating_detect_obj["img"]
        screencap_mask_gray = floating_detect_obj["mask_single_channel"]
        screencap_outputmask_bgr = floating_detect_obj["outputMask"]
        source_screen_height = floating_detect_obj["sourceScreenHeight"]
        source_screen_width = floating_detect_obj["sourceScreenWidth"]

        capture_height = screencap_im_bgr.shape[0]
        capture_width = screencap_im_bgr.shape[1]
        is_dims_mismatch = check_image_scale and (capture_width != source_screen_width or capture_height != source_screen_height)
        height_translation = 1
        width_translation = 1
        match_result = None
        thresholded_match_results = None
        is_match_error = False
        threshold_match_results = lambda match_results: np.where(
            ~np.isnan(match_results) & (np.inf > match_results) & (match_results >= threshold)
        )
        use_resized_im_only = detectObject["actionData"]["useImageRescaledToScreenOnly"] == "true" or detectObject["actionData"]["useImageRescaledToScreenOnly"]

        pre_log = 'Performing template match with options use_color {}, use_mask {}\n'.format(
            str(use_color), str(use_mask)
        ) + ' on image of size {}, search image of size {} and mask of size {}'.format(
            str(screencap_im_bgr.shape),
            str(screencap_search_bgr.shape),
            str(screencap_mask_gray.shape)
        )
        script_logger.log(pre_log, level='debug')
        script_logger.get_action_log().append_supporting_file(
            'text',
            'detect_result.txt',
            '\n' + pre_log
        )
        resized_im_log = ''
        if not use_resized_im_only:
            try:
                script_logger.log('Starting match template', level='debug')
                match_result = cv2.matchTemplate(
                    cv2.cvtColor(screencap_im_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im_bgr,
                    cv2.cvtColor(screencap_search_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_search_bgr,
                    cv2.TM_CCOEFF_NORMED,result=None,
                    mask=screencap_mask_gray if use_mask else None
                )
                script_logger.log('Finished match template', level='debug')
            except cv2.error as e:
                is_match_error = True

            if match_result is not None:
                thresholded_match_results = threshold_match_results(match_result)
        else:
            resized_im_log = 'Skipping unresized template match as use resized image only is selected'
            script_logger.log(resized_im_log)
            pre_log += '\n' + resized_im_log
        if ((
            is_match_error
            or (thresholded_match_results is not None
            and len(thresholded_match_results[0]) == 0)
        ) and is_dims_mismatch) or use_resized_im_only:
            parse_resized_img = True
            try:
                screencap_im_bgr_resized = cv2.resize(
                    screencap_im_bgr.copy(),
                    (source_screen_width, source_screen_height),
                    interpolation=cv2.INTER_AREA
                )
                mid_log = ('Unresized template match failed. ' if resized_im_log == '' else '') + \
                          'Performing resized template match' +\
                          ' on image of size {}, search image of size {} and mask of size {}.\n'.format(
                    str(screencap_im_bgr.shape),
                    str(screencap_search_bgr.shape),
                    str(screencap_mask_gray.shape)
                )
                mid_log += f'Resized image to fit original dimensions width {source_screen_width} and height {source_screen_height}'
                script_logger.log(mid_log, level='debug')
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'detect_result.txt',
                    '\n' + mid_log
                )
                script_logger.log('Starting match template', level='debug')
                match_result_resized = cv2.matchTemplate(
                    cv2.cvtColor(screencap_im_bgr_resized.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im_bgr_resized,
                    cv2.cvtColor(screencap_search_bgr.copy(),
                                 cv2.COLOR_BGR2GRAY) if not use_color else screencap_search_bgr,
                    cv2.TM_CCOEFF_NORMED, result=None,
                    mask=screencap_mask_gray if use_mask else None
                )
                script_logger.log('Finished match template', level='debug')

                # script_logger.log('match_result_resize ', threshold_match_results(match_result_resized))
                # exit(0)
            except cv2.error as e:
                if is_match_error:
                    script_logger.log('error in resized match template : ', e, level='error')
                    exit(1)
                else:
                    parse_resized_img = False
            if parse_resized_img:
                screencap_im_bgr = screencap_im_bgr_resized
                match_result = match_result_resized
                thresholded_match_results = threshold_match_results(match_result)
                height_translation = capture_height/source_screen_height
                width_translation = capture_width/source_screen_width
        # if there is an erorr resize image to original dims, pass translation factor to filter_matches

        return ImageMatcher.filter_matches(
            detectObject,
            match_result,
            thresholded_match_results,
            screencap_im_bgr,
            screencap_search_bgr,
            screencap_outputmask_bgr,
            height_translation=height_translation,
            width_translation=width_translation,
            script_mode=script_mode,
            output_cropping=output_cropping
        )

    @staticmethod
    def filter_matches(
            detectObject,
            match_result,
            thresholded_match_results,
            screencap_im_bgr,
            screencap_search_bgr,
            screencap_outputmask_bgr,
            height_translation=1,
            width_translation=1,
            script_mode='test', output_cropping=None) -> tuple[list[TemplateMatch], np.ndarray]:

        h, w = screencap_search_bgr.shape[0:2]
        dist_threshold = max(min(h, w) * 0.2, MINIMUM_MATCH_PIXEL_SPACING)
        matches: list[TemplateMatch] = []
        match_img_index = 1
        if thresholded_match_results is None:
            script_logger.log('image matching failed as thresholded_match_results is None, check inputExpression of action', level='error')
            exit(1)
        if output_cropping is not None:
            output_cropping = (
                (int(output_cropping[0][0]), int(output_cropping[0][1])),
                (int(output_cropping[1][0]), int(output_cropping[1][1])),
            )
        unpacked_results = list(zip(*thresholded_match_results[::-1]))
        initial_matches = len(unpacked_results)
        for pt in unpacked_results:
            redundant = False
            match_score = match_result[pt[1], pt[0]]
            match_img_bgr = cv2.bitwise_and(screencap_im_bgr[pt[1]:pt[1] + h, pt[0]:pt[0] + w].copy(),
                                            screencap_outputmask_bgr)
            if output_cropping is not None:
                match_img_bgr = match_img_bgr[
                                    output_cropping[0][1]:output_cropping[1][1],
                                    output_cropping[0][0]:output_cropping[1][0]
                                ].copy()
            if match_score == np.inf:
                continue
            adjusted_pt_x = pt[0] * width_translation
            adjusted_pt_y = pt[1] * height_translation
            # script_logger.log('filtered matches : ', len(matches), pt)
            for match_index in range(0, len(matches)):
                match = matches[match_index]
                match_coord = match.point
                match_dist = dist(
                    match_coord[0],
                    match_coord[1],
                    adjusted_pt_x,
                    adjusted_pt_y
                )
                # script_logger.log('dist_comparison : ', match_coord, pt, match_dist, dist_threshold)
                # script_logger.log('dist ', match_dist)
                if match_dist < dist_threshold:
                    if match_score > match.score:
                        matches[match_index] = TemplateMatch(
                            point=(adjusted_pt_x, adjusted_pt_y),
                            score=match_score,
                            matched_area=match_img_bgr
                        )
                    redundant = True
                    break
            if redundant:
                continue
            else:
                matches.append(
                    TemplateMatch(
                        point=(adjusted_pt_x, adjusted_pt_y),
                        score=match_score,
                        matched_area=match_img_bgr
                    )
                )
                match_img_index += 1
        matches.sort(reverse=True, key=lambda match: match.score)
        initial_result_log = '{} initial matches meeting threshold. {} matches after pruning.\n'.format(
            initial_matches,
            len(matches)
        )

        script_logger.log(initial_result_log)
        script_logger.get_action_log().append_supporting_file(
            'text',
            'detect_result.txt',
            initial_result_log
        )
        return matches, match_result

    @staticmethod
    def adjust_box_to_bounds(pt, box_width, box_height, screen_width, screen_height, box_thickness):
        x_overshoot = pt[0] + box_width + box_thickness - screen_width
        y_overshoot = pt[1] + box_height + box_thickness - screen_height
        return (
            max(0, box_width - x_overshoot if x_overshoot > 0 else box_width),
            max(0, box_height - y_overshoot if y_overshoot > 0 else box_height)
        )

    @staticmethod
    def create_result_overlay(detectObject, screencap_im_bgr, input_expression_match_point_xy_absolute, screencap_search_bgr, matches, match_result):
        """The detectObject post image (matches over the input) as a log overlay.

        Layers are drawn in the input's own coordinates. When the input came
        from an input expression (fixed_scale), they are drawn in a frame placed
        at the input's match point inside the blurred full screenshot, so the
        match is shown in context. The pre image is always the input itself: the
        screenshot, or, when the input is an earlier action's output (a match,
        a transformed match), that output. meta records the best match for
        detect_result.txt.
        """
        input_x = int(input_expression_match_point_xy_absolute[0])
        input_y = int(input_expression_match_point_xy_absolute[1])
        input_h, input_w = screencap_im_bgr.shape[:2]
        h, w = screencap_search_bgr.shape[0:2]
        threshold = float(detectObject['actionData']['threshold'])
        detect_action_type = detectObject['actionData']['detectActionType']
        input_obj = detectObject['input_obj']
        fixed_scale = input_obj['fixed_scale']

        if fixed_scale:
            capture = input_obj.get('original_image')
            overlay = Overlay('detectObject', capture.shape[1], capture.shape[0], pre_image_key='input')
            overlay.images['capture'] = capture
            overlay.images['input'] = screencap_im_bgr
            input_key = 'input'
        else:
            overlay = Overlay('detectObject', input_w, input_h)
            overlay.images['capture'] = screencap_im_bgr
            input_key = 'capture'

        layers = [{'op': 'image', 'image': input_key, 'at': [0, 0]}]
        uses_template = False
        best_point_xy_absolute = None
        best_point_score = 0

        if detect_action_type == "floatingObject":
            if len(matches) > 0:
                best_point_xy_absolute = int_point(matches[0]['point'])
                best_point_score = float(matches[0]['score'])
            else:
                # Nothing met the threshold: show the template faintly at the
                # best scoring point, boxed in red scaled by the score.
                valid_matched_points = np.where(np.isinf(match_result) | np.isnan(match_result), -np.inf, match_result)
                max_valid_point = np.max(valid_matched_points)
                if max_valid_point != -np.inf:
                    best_point_yx_relative = np.unravel_index(np.argmax(valid_matched_points), valid_matched_points.shape)
                    best_point_score = float(match_result[best_point_yx_relative])
                    best_point_xy_relative = (int(best_point_yx_relative[1]), int(best_point_yx_relative[0]))
                    best_point_xy_absolute = [
                        best_point_xy_relative[0] + input_x,
                        best_point_xy_relative[1] + input_y
                    ]
                    box_w, box_h = ImageMatcher.adjust_box_to_bounds(best_point_xy_relative, w, h, input_w, input_h, 2)
                    uses_template = True
                    layers.append({'op': 'group', 'opacity': 0.3, 'layers': [{
                        'op': 'image', 'image': 'template',
                        'at': list(best_point_xy_relative), 'src': [0, 0, int(box_w), int(box_h)]
                    }]})
                    layers.append({
                        'op': 'rect',
                        'p1': list(best_point_xy_relative),
                        'p2': [int(best_point_xy_relative[0] + box_w), int(best_point_xy_relative[1] + box_h)],
                        'color': bgr_to_hex((0, 0, int((255 * best_point_score + 255) / 2))),
                        'thickness': 2
                    })

        # Precompute match geometry once per match
        match_data = []
        for match_obj in matches:
            if match_obj['score'] < threshold:
                continue
            match_point_xy_absolute = tuple(map(int, match_obj['point']))
            match_point_xy_relative = (
                int(match_point_xy_absolute[0] - input_x),
                int(match_point_xy_absolute[1] - input_y)
            )
            box_w, box_h = ImageMatcher.adjust_box_to_bounds(
                match_point_xy_relative,
                w, h,
                input_w, input_h, 2
            )
            match_data.append((match_point_xy_relative, int(box_w), int(box_h), float(match_obj['score'])))

        if 'maxMatches' in detectObject['actionData'] and str(detectObject['actionData']['maxMatches']).isdigit():
            max_matches = int(detectObject['actionData']['maxMatches'])
        else:
            max_matches = 1

        if len(match_data) > 0:
            # Templates at half strength (floatingObject only), then the match
            # areas washed red. The red boxes cover every pasted template, so
            # drawing them over the blended result matches blending both at once.
            if detect_action_type == "floatingObject":
                uses_template = True
                layers.append({'op': 'group', 'opacity': 0.5, 'layers': [
                    {'op': 'image', 'image': 'template', 'at': list(pt), 'src': [0, 0, box_w, box_h]}
                    for pt, box_w, box_h, score in match_data
                ]})
            layers.append({'op': 'group', 'opacity': 0.5, 'layers': [
                {
                    'op': 'rect', 'p1': list(pt), 'p2': [pt[0] + box_w, pt[1] + box_h],
                    'color': bgr_to_hex((0, 0, 255)), 'thickness': -1
                }
                for pt, box_w, box_h, score in match_data
            ]})

        # Blue outline around the first max_matches, brighter for higher scores.
        for pt, box_w, box_h, score in match_data[:max_matches]:
            layers.append({
                'op': 'rect', 'p1': list(pt), 'p2': [pt[0] + box_w, pt[1] + box_h],
                'color': bgr_to_hex((int((255 * score + 255) / 2), 0, 0)), 'thickness': 2
            })

        if uses_template:
            overlay.images['template'] = screencap_search_bgr

        if fixed_scale:
            overlay.layers.append({'op': 'image', 'image': 'capture', 'at': [0, 0]})
            # original_image_blurred is this same blur of the capture.
            if input_obj.get('original_image_blurred') is not None:
                overlay.layers.append({'op': 'blur', 'kernel': 31})
            overlay.layers.append({
                'op': 'frame', 'at': [input_x, input_y], 'width': input_w, 'height': input_h, 'layers': layers
            })
            overlay.layers.append({
                'op': 'rect', 'p1': [input_x, input_y], 'p2': [input_x + input_w, input_y + input_h],
                'color': bgr_to_hex((255, 0, 0)), 'thickness': 1
            })
        else:
            overlay.layers = layers

        overlay.meta = {
            'detectActionType': detect_action_type,
            'threshold': threshold,
            'best_point': best_point_xy_absolute,
            'best_score': best_point_score,
            'input_point': [input_x, input_y],
            'matches': [
                {'point': [pt[0] + input_x, pt[1] + input_y], 'width': box_w, 'height': box_h, 'score': score}
                for pt, box_w, box_h, score in match_data
            ],
            'max_matches': max_matches,
        }
        return overlay

    # def produce_logistic_matches(self, screencap_im, screencap_search, screencap_mask, logs_path, assets_folder, threshold=0.7):
    #     # https://towardsdatascience.com/logistic-regression-using-python-sklearn-numpy-mnist-handwriting-recognition-matplotlib-a6b31e2b166a
    #     # https://stackoverflow.com/questions/5953373/how-to-split-image-into-multiple-pieces-in-python#:~:text=Copy%20the%20image%20you%20want%20to%20slice%20into,an%20image%20split%20with%20two%20lines%20of%20code
    #
    #     logistic_model = LogisticRegression()
    #     grayscale_screencap = cv2.cvtColor(screencap_im.copy(), cv2.COLOR_RGB2GRAY)
    #     # script_logger.log(grayscale_screencap.shape)
    #     h,w = screencap_search.shape[:-1]
    #     imgs = []
    #     labels = []
    #     positive_examples = glob.glob(assets_folder + '/positiveExamples/*-img.png')
    #     negative_examples = glob.glob(assets_folder + '/negativeExamples/*-img.png')
    #     for positive_example in positive_examples:
    #         imgs.append(np.asarray(cv2.cvtColor(np.asarray(Image.open(positive_example)), cv2.COLOR_RGB2GRAY)).flatten())
    #         labels.append(1)
    #     for negative_example in negative_examples:
    #         imgs.append(np.asarray(cv2.cvtColor(np.asarray(Image.open(negative_example)), cv2.COLOR_RGB2GRAY)).flatten())
    #         labels.append(0)
    #     logistic_model.fit(imgs, labels)
    #     script_logger.log(screencap_im.shape)
    #     script_logger.log(h)
    #     script_logger.log(w)
    #     # script_logger.log(screencap_im[0:h, 0:w].shape)
    #     img_tiles = np.array([grayscale_screencap[y:y + h, x:x + w].flatten() for y in range(0, (grayscale_screencap.shape[0] - h)) for x in range(0, (grayscale_screencap.shape[1] - w))])
    #     script_logger.log(img_tiles.shape)
    #     # logistic_model.predict(img_tiles).reshape(screencap_im.shape[0] - h, screencap_im.shape[1] - w)
    #
    #     script_logger.log(screencap_search.shape)
    #     # script_logger.log(screen_tiles)
    #     # for tile in enumerate(tiles):
    #     exit(0)
    #     return None,None,None



    # @staticmethod
    # def preprocess_scaled_match_object(state, detectObject):
    #     def createScaleFunction(scaleAction):
    #         return lambda x,y : scaleAction["actionData"]["xCoefficient"] * x + scaleAction["actionData"]["yCoefficient"] * y + scaleAction["actionData"]["constantTerm"]
    #     heightScaleAction = state_eval(detectObject["actionData"]["heightScale"], {}, state)
    #     heightScale = createScaleFunction(heightScaleAction)
    #     widthScaleAction = state_eval(detectObject["actionData"]["widthScale"], {}, state)
    #     widthScale = createScaleFunction(widthScaleAction)
    #     source_width = heightScaleAction["actionData"]["sourceWidth"]
    #     source_height = heightScaleAction["actionData"]["sourceHeight"]
    #     scaled_template_heights = np.zeros((source_height, source_width))
    #     scaled_template_widths = np.zeros((source_height, source_width))
    #     scaled_templates = np.empty((source_height, source_width), dtype=object)
    #     scaled_template_masks = np.empty((source_height, source_width), dtype=object)
    #     scaled_template_mask_sizes = np.zeros((source_height, source_width))
    #     scaled_template_output_masks = np.empty((source_height, source_width), dtype=object)
    #     scaled_template_output_masks_single_channel = np.empty((source_height, source_width), dtype=object)
    #
    #
    #     for y_index in range(0, source_height):
    #         for x_index in range(0, source_width):
    #             template_height = heightScale(x_index,y_index)
    #             template_width = widthScale(x_index,y_index)
    #             template_height = template_height if (y_index + template_height < source_height) else 0
    #             template_width = template_width if (x_index + template_width < source_width) else 0
    #             scaled_template_heights[y_index, x_index] = template_height
    #             scaled_template_widths[y_index, x_index] = template_width
    #             if template_width != 0 and template_height != 0:
    #                 scaled_templates[y_index, x_index] = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["img"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
    #                 scaled_template_masks[y_index, x_index] = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["mask"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
    #                 scaled_template_mask_sizes[y_index, x_index] = np.count_nonzero(detectObject["actionData"]["positiveExamples"][0]["mask_single_channel"]) * 3 * 255
    #                 scaled_template_output_masks = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["outputMask"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
    #                 scaled_template_output_masks_single_channel = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["outputMask_single_channel"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
    #             else:
    #                 scaled_templates[y_index, x_index] = None
    #                 scaled_template_masks[y_index, x_index] = None
    #                 scaled_template_mask_sizes[y_index, x_index] = 0
    #                 scaled_template_output_masks = None
    #                 scaled_template_output_masks_single_channel = None
    #
    #     detectObject["actionData"]["scaled_templates"] = scaled_templates
    #     detectObject["actionData"]["scaled_template_heights"] = scaled_template_heights
    #     detectObject["actionData"]["scaled_template_widths"] = scaled_template_widths
    #     detectObject["actionData"]["scaled_template_masks"] = scaled_template_masks
    #     detectObject["actionData"]["scaled_template_mask_sizes"] = scaled_template_mask_sizes
    #     detectObject["actionData"]["scaled_template_output_masks"] = scaled_template_output_masks
    #     detectObject["actionData"]["scaled_template_output_masks_single_channel"] = scaled_template_output_masks_single_channel
    #     return detectObject




    # @staticmethod
    # def produce_scaled_template_matches(detectObject, screencap_im_bgr, screencap_search_bgr, screencap_outputmask_bgr,
    #                              logs_path, threshold=0.96, use_color=True, use_mask=True, script_mode='test'):
    #     for y_index in range(0, detectObject["actionData"]["scaled_template_heights"].shape[0]):
    #         for x_index in range(0, detectObject["actionData"]["scaled_template_heights"].shape[1]):
    #             scaled_template = detectObject["actionData"]["scaled_templates"][y_index, x_index]
    #             if scaled_template is not None:
    #                 template_height = detectObject["actionData"]["scaled_template_heights"][y_index, x_index]
    #                 template_width = detectObject["actionData"]["scaled_template_widths"][y_index, x_index]
    #                 template_mask = detectObject["actionData"]["scaled_template_masks"][y_index, x_index]
    #                 template_mask_size = detectObject["actionData"]["scaled_template_mask_sizes"][y_index, x_index]
    #                 screencap_masked = cv2.bitwise_and(
    #                     screencap_im_bgr[y_index:y_index+template_height, x_index:x_index+template_width],
    #                     template_mask
    #                 )
    #                 ssim_coeff = masked_mse(screencap_masked, screencap_search_bgr, template_mask_size)

