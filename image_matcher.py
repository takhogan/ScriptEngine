import cv2
import numpy as np
import pandas as pd
from script_engine_utils import dist
from script_engine_utils import masked_mse

class ImageMatcher:
    def __init__(self):
        pass

    @staticmethod
    def template_match(detectObject,
                       screencap_im_bgr, screencap_search_bgr, screencap_mask_gray, screencap_outputmask_bgr, screencap_outputmask_gray,
                       detector_name, logs_path, script_mode, match_point,
                       output_cropping=None,
                       threshold=0.96, use_color=True, use_mask=True):
        # print(screencap_search.shape)
        if detector_name == "pixelDifference":
            matches, match_result, result_im_bgr = ImageMatcher.produce_template_matches(
                screencap_im_bgr.copy(),
                screencap_search_bgr.copy(),
                screencap_mask_gray,
                screencap_outputmask_bgr,
                logs_path,
                output_cropping=output_cropping,
                threshold=threshold,
                use_color=use_color,
                use_mask=use_mask
            )
        elif detector_name == "scaledPixelDifference":
            pass
            # matches, match_result, result_im_bgr = ImageMatcher.produce_scaled_template_matches(
            #     detectObject,
            #     screencap_im_bgr.copy(),
            #     screencap_search_bgr.copy(),
            #     screencap_outputmask_bgr,
            #     logs_path,
            #     threshold=threshold,
            #     use_color=use_color,
            #     use_mask=use_mask
            # )
        elif detector_name == "logisticClassifier":
            print("logistic detector unimplemented ")
            exit(0)
            # assets_folder = '/'.join((self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"]).split('/')[:-2])
            # matches,match_result,result_im = self.produce_logistic_matches(screencap_im.copy(), screencap_search, screencap_mask, logs_path, assets_folder)
        else:
            print("detector unimplemented! ")
            exit(0)

        h, w = screencap_outputmask_gray.shape[0:2]
        # plt.imshow(match_result, cmap='gray')
        # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
        cv2.imwrite(logs_path + 'matching_overlay.png', result_im_bgr)
        cv2.imwrite(logs_path + 'match_result.png', match_result * 255)
        # if self.props["scriptMode"] == "train":
        #     threshold = 0.94
        #     train_matches = []
        #     while not len(train_matches) > 0 and threshold > 0.1:
        #         threshold -= 0.02
        #         train_matches, train_match_result, train_result_im = self.produce_matches(screencap_im.copy(), screencap_search,
        #                                                                 screencap_mask, logs_path,
        #                                                                 threshold=threshold)
        #     # print(train_matches[0])
        #     print('train_threshold: ', threshold)
        #     cv2.imwrite(logs_path + 'matching_overlay_train.png', cv2.cvtColor(train_result_im, cv2.COLOR_BGR2RGB))
        #     cv2.imwrite(logs_path + 'match_result_train.png', train_match_result * 255)
        # print('pre sort matches: ', matches)
        matches.sort(reverse=True, key=lambda match: match[1])
        # print('post sort matches: ', matches)
        return [{
                'input_type': 'shape',
                'point': (match[0] + match_point[0], match[1] + match_point[1]) if match_point is not None else match,
                'shape': screencap_outputmask_gray,
                'matched_area': match_area,
                'height': h,
                'width': w,
                'score': score
        } for match, score, match_area in matches]


    @staticmethod
    def produce_template_matches(screencap_im_bgr, screencap_search_bgr, screencap_mask_gray, screencap_outputmask_bgr,
                                 logs_path, output_cropping=None, threshold=0.96, use_color=True, use_mask=True, script_mode='test'):
        # https://docs.opencv.org/3.4/de/da9/tutorial_template_matching.html
        h, w = screencap_search_bgr.shape[0:2]
        # print(screencap_search.shape)
        # print(screencap_mask.shape)
        # exit(0)
        # print(.shape)
        # exit(0)
        # print('match threshold: ', threshold)
        # exit(0)
        # cv2.imshow('screencap_im', screencap_im)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_search', screencap_search)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_mask', screencap_mask)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_im', screencap_im_bgr)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_search', screencap_search_bgr)
        # cv2.waitKey(0)
        try:
            match_result = cv2.matchTemplate(
                cv2.cvtColor(screencap_im_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im_bgr,
                cv2.cvtColor(screencap_search_bgr.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_search_bgr,
                cv2.TM_CCOEFF_NORMED,result=None,
                mask=screencap_mask_gray if use_mask else None)
        except cv2.error as e:
            print(e)
            cv2.imshow('screencap_im', screencap_im_bgr)
            cv2.waitKey(0)
            cv2.imshow('screencap_search', screencap_search_bgr)
            cv2.waitKey(0)
            cv2.imshow('screencap_mask_gray', screencap_mask_gray)
            cv2.waitKey(0)
            print(screencap_im_bgr.shape, screencap_search_bgr.shape, screencap_mask_gray.shape)
            exit(1)
        # match_result = 1 - match_result

        # cv2.normalize(match_result, match_result, 0, 1, cv2.NORM_MINMAX, -1)
        # minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(match_result, None)
        # match_result = cv2.matchTemplate(screencap_im, screencap_search, cv2.TM_CCOEFF_NORMED)
        dist_threshold = (w + h) * 0.1
        # print(dist_threshold)
        # print(np.where(match_result >= threshold))
        loc = np.where((np.inf > match_result) & (match_result >= threshold))
        # print('loc : ', loc)
        matches = []
        match_img_index = 1

        for pt in zip(*loc[::-1]):
            redundant = False
            match_score = match_result[pt[1], pt[0]]
            match_img_bgr = cv2.bitwise_and(screencap_im_bgr[pt[1]:pt[1] + h, pt[0]:pt[0] + w].copy(), screencap_outputmask_bgr)
            if output_cropping is not None:
                match_img_bgr = match_img_bgr[output_cropping[0][1]:output_cropping[1][1], output_cropping[0][0]:output_cropping[1][0]].copy()
            if match_score == np.inf:
                print(pt)
                continue
            for match_index in range(0, len(matches)):
                match = matches[match_index]
                match_coord = match[0]
                match_dist = dist(match_coord[0], match_coord[1], pt[0], pt[1])
                # print('dist ', match_dist)
                if match_dist < dist_threshold:
                    if match_score > match[1]:
                        matches[match_index] = (pt, match_score, match_img_bgr)
                    redundant = True
                    break
            if redundant:
                continue
            else:
                # print('{:f}'.format(match_result[pt[1], pt[0]]))
                matches.append((pt, match_score, match_img_bgr))
                if script_mode == "train":
                    # change name to fit image format
                    cv2.imwrite(logs_path + '-matched-' + str(match_img_index) + '-{:f}'.format(match_result[pt[1], pt[0]]) + '-img.png', match_img_bgr)
                match_img_index += 1
        best_match = str(np.max(match_result[np.where(np.inf > match_result)])) if (match_result[np.where(np.inf > match_result)]).size > 0 else 'none'
        print('n matches : ', len(matches), ' best match : ', best_match)
        with open(logs_path + '-best-' + best_match + '.txt', 'w') as log_file:
            log_file.write('n matches : ' + str(len(matches)))
        result_im_bgr = screencap_im_bgr
        for pt in zip(*loc[::-1]):
            cv2.rectangle(result_im_bgr, pt, (pt[0] + w, pt[1] + h), (0, 0, 255), 2)
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


