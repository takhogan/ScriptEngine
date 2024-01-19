import cv2
import numpy as np
from script_engine_utils import dist
from script_engine_utils import masked_mse

MINIMUM_MATCH_PIXEL_SPACING = 15

class ImageMatcher:
    def __init__(self):
        pass

    @staticmethod
    def template_match(detectObject,
                       screencap_im_bgr, screencap_search_bgr, screencap_mask_gray, screencap_outputmask_bgr, screencap_outputmask_gray,
                       detector_name, logs_path, script_mode, match_point,
                       log_level='info',
                       check_image_scale=True,
                       output_cropping=None,
                       threshold=0.96, use_color=True, use_mask=True):
        if detector_name == "pixelDifference":
            matches, match_result, result_im_bgr = ImageMatcher.produce_template_matches(
                detectObject,
                screencap_im_bgr,
                screencap_search_bgr,
                screencap_mask_gray,
                screencap_outputmask_bgr,
                logs_path,
                int(detectObject['actionData']['sourceScreenHeight']),
                int(detectObject['actionData']['sourceScreenWidth']),
                log_level=log_level,
                check_image_scale=check_image_scale,
                output_cropping=output_cropping,
                threshold=threshold,
                use_color=use_color,
                use_mask=use_mask
            )
        elif detector_name == "scaledPixelDifference":
            pass
        elif detector_name == "logisticClassifier":
            print("logistic detector unimplemented ")
            exit(0)
        else:
            print("detector unimplemented! ")
            exit(0)

        h, w = screencap_outputmask_gray.shape[0:2]
        if log_level == 'info':
            cv2.imwrite(logs_path + 'matching_overlay.png', result_im_bgr)
            cv2.imwrite(logs_path + 'match_result.png', match_result * 255)
            cv2.imwrite(logs_path + 'output_mask.png', screencap_outputmask_gray)
        n_matches = len(matches)
        return [{
                'input_type': 'shape',
                'point': (match[0] + match_point[0], match[1] + match_point[1]) if match_point is not None else match,
                'shape': screencap_outputmask_gray,
                'matched_area': match_area,
                'height': h,
                'width': w,
                'score': score,
                'n_matches': n_matches
        } for match, score, match_area in matches]


    @staticmethod
    def produce_template_matches(
            detectObject,
            screencap_im_bgr,
            screencap_search_bgr,
            screencap_mask_gray,
            screencap_outputmask_bgr,
            logs_path,
            source_screen_height,
            source_screen_width,
            check_image_scale,
            log_level='info',
            output_cropping=None,
            threshold=0.96, use_color=True, use_mask=True, script_mode='test'):
        # https://docs.opencv.org/3.4/de/da9/tutorial_template_matching.html
        capture_height = screencap_im_bgr.shape[0]
        capture_width = screencap_im_bgr.shape[1]
        is_dims_mismatch = check_image_scale and (capture_width != source_screen_width or capture_height != source_screen_height)
        height_translation = 1
        width_translation = 1
        match_result = None
        thresholded_match_results = None
        is_match_error = False
        threshold_match_results = lambda match_results: np.where((np.inf > match_results) & (match_results >= threshold))
        use_resized_im_only = detectObject["actionData"]["useImageRescaledToScreenOnly"] == "true" or detectObject["actionData"]["useImageRescaledToScreenOnly"]
        if not use_resized_im_only:
            try:
                match_result = cv2.matchTemplate(
                    cv2.cvtColor(screencap_im_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im_bgr,
                    cv2.cvtColor(screencap_search_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_search_bgr,
                    cv2.TM_CCOEFF_NORMED,result=None,
                    mask=screencap_mask_gray if use_mask else None)
            except cv2.error as e:
                is_match_error = True

            if match_result is not None:
                thresholded_match_results = threshold_match_results(match_result)

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
                print('resize : ', screencap_im_bgr_resized.shape, screencap_im_bgr.shape, source_screen_width, source_screen_height)
                match_result_resized = cv2.matchTemplate(
                    cv2.cvtColor(screencap_im_bgr_resized.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im_bgr_resized,
                    cv2.cvtColor(screencap_search_bgr.copy(),
                                 cv2.COLOR_BGR2GRAY) if not use_color else screencap_search_bgr,
                    cv2.TM_CCOEFF_NORMED, result=None,
                    mask=screencap_mask_gray if use_mask else None)
                # print('match_result_resize ', threshold_match_results(match_result_resized))
                # exit(0)
            except cv2.error as e:
                if is_match_error:
                    print('error in resized match template : ', e)
                    exit(1)
                else:
                    parse_resized_img = False
            if parse_resized_img:
                screencap_im_bgr = screencap_im_bgr_resized
                match_result = match_result_resized
                thresholded_match_results = threshold_match_results(match_result)
                height_translation = capture_height/source_screen_height
                width_translation = capture_width/source_screen_width
                print('translation : ', height_translation, capture_height,source_screen_height, width_translation, capture_width, source_screen_width)

        # if there is an erorr resize image to original dims, pass translation factor to filter_matches

        return ImageMatcher.filter_matches_and_get_result_im(
            detectObject,
            match_result,
            thresholded_match_results,
            screencap_im_bgr,
            screencap_search_bgr,
            screencap_outputmask_bgr,
            logs_path,
            log_level=log_level,
            height_translation=height_translation,
            width_translation=width_translation,
            script_mode=script_mode,
            output_cropping=output_cropping
        )

    @staticmethod
    def filter_matches_and_get_result_im(
            detectObject,
            match_result,
            thresholded_match_results,
            screencap_im_bgr,
            screencap_search_bgr,
            screencap_outputmask_bgr,
            logs_path,
            log_level='info',
            height_translation=1,
            width_translation=1,
            script_mode='test', output_cropping=None):
        h, w = screencap_search_bgr.shape[0:2]
        dist_threshold = max((w + h) * 0.1, MINIMUM_MATCH_PIXEL_SPACING)
        matches = []
        match_img_index = 1

        for pt in zip(*thresholded_match_results[::-1]):
            redundant = False
            match_score = match_result[pt[1], pt[0]]
            match_img_bgr = cv2.bitwise_and(screencap_im_bgr[pt[1]:pt[1] + h, pt[0]:pt[0] + w].copy(),
                                            screencap_outputmask_bgr)
            if output_cropping is not None:
                match_img_bgr = match_img_bgr[output_cropping[0][1]:output_cropping[1][1],
                                output_cropping[0][0]:output_cropping[1][0]].copy()
            if match_score == np.inf:
                continue
            adjusted_pt_x = pt[0] * width_translation
            adjusted_pt_y = pt[1] * height_translation
            # print('filtered matches : ', len(matches), pt)
            for match_index in range(0, len(matches)):
                match = matches[match_index]
                match_coord = match[0]
                match_dist = dist(
                    match_coord[0],
                    match_coord[1],
                    adjusted_pt_x,
                    adjusted_pt_y
                )
                # print('dist_comparison : ', match_coord, pt, match_dist, dist_threshold)
                # print('dist ', match_dist)
                if match_dist < dist_threshold:
                    if match_score > match[1]:
                        matches[match_index] = (
                            (adjusted_pt_x, adjusted_pt_y),
                            match_score,
                            match_img_bgr
                        )
                    redundant = True
                    break
            if redundant:
                continue
            else:
                # print('{:f}'.format(match_result[pt[1], pt[0]]))
                matches.append(
                    (
                        (adjusted_pt_x, adjusted_pt_y),
                        match_score,
                        match_img_bgr
                    )
                )
                # exit(0)
                if script_mode == "train" and log_level == 'info':
                    # change name to fit image format
                    cv2.imwrite(logs_path + '-matched-' + str(match_img_index) + '-{:f}'.format(
                        match_result[pt[1], pt[0]]) + '-img.png', match_img_bgr)
                match_img_index += 1
        best_match = 'none'
        best_match_pt = None
        if match_result[np.where(np.inf > match_result)].size > 0:
            best_match_pt = np.unravel_index(np.argmax(match_result[np.where(np.inf > match_result)]), match_result.shape)
            best_match = str(np.max(match_result[np.where(np.inf > match_result)]))
        else:
            print('a not valid')
        best_match_str = str(best_match)
        print('n matches : ', len(matches), ' best match : ', best_match_pt, best_match_str)

        with open(logs_path + '-best-' + best_match_str + '.txt', 'w') as log_file:
            log_file.write('n matches : ' + str(len(matches)))
        result_im_bgr = screencap_im_bgr.copy()
        matches.sort(reverse=True, key=lambda match: match[1])
        def adjust_box_to_bounds(pt, box_width, box_height, screen_width, screen_height, box_thickness):
            x_overshoot = pt[0] + box_width + box_thickness - screen_width
            y_overshoot = pt[1] + box_height + box_thickness - screen_height
            return (
                max(0, box_width - x_overshoot if x_overshoot > 0 else box_width),
                max(0, box_height - y_overshoot if y_overshoot > 0 else box_height)
            )
        box_w = box_h = -1
        for pt in zip(*thresholded_match_results[::-1]):
            box_w, box_h = adjust_box_to_bounds(pt, w, h, screencap_im_bgr.shape[1], screencap_im_bgr.shape[0], 2)
            cv2.rectangle(result_im_bgr, pt, (pt[0] + box_w, pt[1] + box_h), (0, 0, 255), 2)
        if thresholded_match_results[0].size == 0 and best_match_pt is not None:
            box_w, box_h = adjust_box_to_bounds(best_match_pt, w, h, screencap_im_bgr.shape[1], screencap_im_bgr.shape[0], 2)
            cv2.rectangle(result_im_bgr, best_match_pt, (best_match_pt[0] + box_w, best_match_pt[1] + box_h), (0, 0, 128), 2)
        return matches, match_result, result_im_bgr

    # def produce_logistic_matches(self, screencap_im, screencap_search, screencap_mask, logs_path, assets_folder, threshold=0.7):
    #     # https://towardsdatascience.com/logistic-regression-using-python-sklearn-numpy-mnist-handwriting-recognition-matplotlib-a6b31e2b166a
    #     # https://stackoverflow.com/questions/5953373/how-to-split-image-into-multiple-pieces-in-python#:~:text=Copy%20the%20image%20you%20want%20to%20slice%20into,an%20image%20split%20with%20two%20lines%20of%20code
    #
    #     logistic_model = LogisticRegression()
    #     grayscale_screencap = cv2.cvtColor(screencap_im.copy(), cv2.COLOR_RGB2GRAY)
    #     # print(grayscale_screencap.shape)
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
    #     print(screencap_im.shape)
    #     print(h)
    #     print(w)
    #     # print(screencap_im[0:h, 0:w].shape)
    #     img_tiles = np.array([grayscale_screencap[y:y + h, x:x + w].flatten() for y in range(0, (grayscale_screencap.shape[0] - h)) for x in range(0, (grayscale_screencap.shape[1] - w))])
    #     print(img_tiles.shape)
    #     # logistic_model.predict(img_tiles).reshape(screencap_im.shape[0] - h, screencap_im.shape[1] - w)
    #
    #     print(screencap_search.shape)
    #     # print(screen_tiles)
    #     # for tile in enumerate(tiles):
    #     exit(0)
    #     return None,None,None

    @staticmethod
    def preprocess_scaled_match_object(state, detectObject):
        def createScaleFunction(scaleAction):
            return lambda x,y : scaleAction["actionData"]["xCoefficient"] * x + scaleAction["actionData"]["yCoefficient"] * y + scaleAction["actionData"]["constantTerm"]
        heightScaleAction = eval(detectObject["actionData"]["heightScale"], state.copy())
        heightScale = createScaleFunction(heightScaleAction)
        widthScaleAction = eval(detectObject["actionData"]["widthScale"], state.copy())
        widthScale = createScaleFunction(widthScaleAction)
        source_width = heightScaleAction["actionData"]["sourceWidth"]
        source_height = heightScaleAction["actionData"]["sourceHeight"]
        scaled_template_heights = np.zeros((source_height, source_width))
        scaled_template_widths = np.zeros((source_height, source_width))
        scaled_templates = np.empty((source_height, source_width), dtype=object)
        scaled_template_masks = np.empty((source_height, source_width), dtype=object)
        scaled_template_mask_sizes = np.zeros((source_height, source_width))
        scaled_template_output_masks = np.empty((source_height, source_width), dtype=object)
        scaled_template_output_masks_single_channel = np.empty((source_height, source_width), dtype=object)


        for y_index in range(0, source_height):
            for x_index in range(0, source_width):
                template_height = heightScale(x_index,y_index)
                template_width = widthScale(x_index,y_index)
                template_height = template_height if (y_index + template_height < source_height) else 0
                template_width = template_width if (x_index + template_width < source_width) else 0
                scaled_template_heights[y_index, x_index] = template_height
                scaled_template_widths[y_index, x_index] = template_width
                if template_width != 0 and template_height != 0:
                    scaled_templates[y_index, x_index] = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["img"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
                    scaled_template_masks[y_index, x_index] = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["mask"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
                    scaled_template_mask_sizes[y_index, x_index] = np.count_nonzero(detectObject["actionData"]["positiveExamples"][0]["mask_single_channel"]) * 3 * 255
                    scaled_template_output_masks = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["outputMask"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
                    scaled_template_output_masks_single_channel = cv2.resize(detectObject["actionData"]["positiveExamples"][0]["outputMask_single_channel"], (template_height, template_width), interpolation=cv2.INTER_LINEAR)
                else:
                    scaled_templates[y_index, x_index] = None
                    scaled_template_masks[y_index, x_index] = None
                    scaled_template_mask_sizes[y_index, x_index] = 0
                    scaled_template_output_masks = None
                    scaled_template_output_masks_single_channel = None

        detectObject["actionData"]["scaled_templates"] = scaled_templates
        detectObject["actionData"]["scaled_template_heights"] = scaled_template_heights
        detectObject["actionData"]["scaled_template_widths"] = scaled_template_widths
        detectObject["actionData"]["scaled_template_masks"] = scaled_template_masks
        detectObject["actionData"]["scaled_template_mask_sizes"] = scaled_template_mask_sizes
        detectObject["actionData"]["scaled_template_output_masks"] = scaled_template_output_masks
        detectObject["actionData"]["scaled_template_output_masks_single_channel"] = scaled_template_output_masks_single_channel
        return detectObject




    @staticmethod
    def produce_scaled_template_matches(detectObject, screencap_im_bgr, screencap_search_bgr, screencap_outputmask_bgr,
                                 logs_path, threshold=0.96, use_color=True, use_mask=True, script_mode='test'):
        for y_index in range(0, detectObject["actionData"]["scaled_template_heights"].shape[0]):
            for x_index in range(0, detectObject["actionData"]["scaled_template_heights"].shape[1]):
                scaled_template = detectObject["actionData"]["scaled_templates"][y_index, x_index]
                if scaled_template is not None:
                    template_height = detectObject["actionData"]["scaled_template_heights"][y_index, x_index]
                    template_width = detectObject["actionData"]["scaled_template_widths"][y_index, x_index]
                    template_mask = detectObject["actionData"]["scaled_template_masks"][y_index, x_index]
                    template_mask_size = detectObject["actionData"]["scaled_template_mask_sizes"][y_index, x_index]
                    screencap_masked = cv2.bitwise_and(
                        screencap_im_bgr[y_index:y_index+template_height, x_index:x_index+template_width],
                        template_mask
                    )
                    ssim_coeff = masked_mse(screencap_masked, screencap_search_bgr, template_mask_size)


