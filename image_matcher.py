import cv2
import numpy as np
import pandas as pd
from script_engine_utils import dist

class ImageMatcher:
    def __init__(self):
        pass

    @staticmethod
    def template_match(screencap_im, screencap_mask, screencap_search, detector_name, logs_path, script_mode, threshold=0.96, use_color=True, use_mask=True,):

        # print(screencap_search.shape)
        if detector_name == "pixelDifference":
            matches, match_result, result_im = ImageMatcher.produce_template_matches(screencap_im.copy(),
                                                                                  screencap_search, screencap_mask,
                                                                                  logs_path, threshold=threshold, use_color=use_color, use_mask=use_mask)
        elif detector_name == "logisticClassifier":
            print("logistic detector unimplemented ")
            exit(0)
            # assets_folder = '/'.join((self.props['dir_path'] + '/' + action["actionData"]["positiveExamples"][0]["mask"]).split('/')[:-2])
            # matches,match_result,result_im = self.produce_logistic_matches(screencap_im.copy(), screencap_search, screencap_mask, logs_path, assets_folder)
        else:
            print("detector unimplemented! ")
            exit(0)
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_result)
        # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
        # if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
        # print(screencap_search.shape)

        h, w = screencap_search.shape[0:2]
        # plt.imshow(match_result, cmap='gray')
        # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
        cv2.imwrite(logs_path + 'matching_overlay.png', cv2.cvtColor(result_im, cv2.COLOR_BGR2RGB))
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
        return [{
                'input_type': 'rectangle',
                'point': match,
                'height': h,
                'width': w,
                'score': score
        } for match, score in matches]


    @staticmethod
    def produce_template_matches(screencap_im, screencap_search, screencap_mask, logs_path, threshold=0.96, use_color=True, use_mask=True, script_mode='test'):
        # https://docs.opencv.org/3.4/de/da9/tutorial_template_matching.html
        h, w = screencap_search.shape[0:2]
        # print(screencap_search.shape)
        # print(screencap_mask.shape)
        # exit(0)
        # print(.shape)
        # exit(0)
        # print('match threshold: ', threshold)
        screencap_mask = np.uint8(cv2.cvtColor(screencap_mask.copy(),cv2.COLOR_BGR2GRAY))
        # exit(0)
        # cv2.imshow('screencap_im', screencap_im)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_search', screencap_search)
        # cv2.waitKey(0)
        # cv2.imshow('screencap_mask', screencap_mask)
        # cv2.waitKey(0)
        match_result = cv2.matchTemplate(
            cv2.cvtColor(screencap_im.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_im.copy(),
            cv2.cvtColor(screencap_search.copy(), cv2.COLOR_BGR2GRAY) if not use_color else screencap_search.copy(),
            cv2.TM_CCOEFF_NORMED,result=None,
            mask=screencap_mask if use_mask else None)
        # match_result = 1 - match_result

        # cv2.normalize(match_result, match_result, 0, 1, cv2.NORM_MINMAX, -1)
        # minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(match_result, None)
        # match_result = cv2.matchTemplate(screencap_im, screencap_search, cv2.TM_CCOEFF_NORMED)
        dist_threshold = (w + h) * 0.1
        # print(dist_threshold)
        loc = np.where((np.inf > match_result) & (match_result >= threshold))
        matches = []
        match_imgs = []
        match_img_index = 1

        for pt in zip(*loc[::-1]):
            redundant = False
            match_score = match_result[pt[1], pt[0]]
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
                        matches[match_index] = (pt, match_score)
                    redundant = True
                    break
            if redundant:
                continue
            else:
                matches.append((pt, match_score))
                # print('{:f}'.format(match_result[pt[1], pt[0]]))
                match_img = screencap_im[pt[1]:pt[1] + h, pt[0]:pt[0] + w].copy()
                match_imgs.append(match_img)
                if script_mode == "train":
                    # change name to fit image format
                    cv2.imwrite(logs_path + '-matched-' + str(match_img_index) + '-{:f}'.format(match_result[pt[1], pt[0]]) + '-img.png', cv2.cvtColor(match_img, cv2.COLOR_BGR2RGB))
                match_img_index += 1

        for pt in zip(*loc[::-1]):
            cv2.rectangle(screencap_im, pt, (pt[0] + w, pt[1] + h), (0, 0, 255), 2)
        return matches, match_result, screencap_im

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