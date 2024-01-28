import argparse

import cv2
import numpy as np

from script_logger import ScriptLogger
script_logger = ScriptLogger()

class FeatureMatcher:
    def __init__(self):
        pass

    # https://blog.francium.tech/feature-detection-and-matching-with-opencv-5fd2394a590
    @staticmethod
    def get_corrected_img(img1, img2):
        MIN_MATCHES = 10

        orb = cv2.SIFT_create(nfeatures=500)
        kp1, des1 = orb.detectAndCompute(img1, None)
        kp2, des2 = orb.detectAndCompute(img2, None)

        script_logger.log('kp1 : ', kp1, ' des1 : ', des1, ' kp2 : ', kp2, ' des2 : ', des2)

        index_params = dict(algorithm=6,
                            table_number=6,
                            key_size=12,
                            multi_probe_level=2)
        search_params = {}
        bf = cv2.BFMatcher()
        # script_logger.log(des2.dtype)
        # exit(0)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)
        # script_logger.log(matches)
        # exit(0)
        # script_logger.log(' matches : ', list(map(len, matches)))
        # As per Lowe's ratio test to filter good matches
        good_matches = []
        for match_pair in matches:
            # if len(match_pair) == 2:
            #     if match_pair[0].distance < 1 * match_pair[1].distance:
                    good_matches.append(match_pair)
        # script_logger.log(len(good_matches))
        start_red = 255
        for good_match in good_matches[:10]:
            screencap_img_idx = kp1[good_match.queryIdx].pt
            search_img_idx = kp2[good_match.trainIdx].pt
            cv2.circle(img1, list(map(int, screencap_img_idx)), radius=5, color=(0, 0, start_red), thickness=-1)
            cv2.circle(img2, list(map(int, search_img_idx)), radius=5, color=(0, 0, start_red), thickness=-1)
            start_red -= 10

        cv2.imshow('img2 : ', img2)
        cv2.waitKey(0)
        cv2.imshow('img1 : ', img1)
        cv2.waitKey(0)

        exit(0)
        if len(good_matches) > MIN_MATCHES:
            src_points = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_points = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            m, mask = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 5.0)
            corrected_img = cv2.warpPerspective(img1, m, (img2.shape[1], img2.shape[0]))

            return corrected_img
        return img2

    if __name__ == "__main__":

        im1 = cv2.imread(r'C:\Users\takho\ScriptEngine\scripts\lvl30Castle\actions\0-row\0-detectObject\assets\positiveExamples\0-img.png')
        im1 = np.uint8(cv2.cvtColor(im1, cv2.COLOR_BGR2GRAY))
        im1[im1 == 0] = 255
        im2 = cv2.imread(r'C:\Users\takho\ScriptEngine\logs\realmScanner-2022-07-02 11-22-11\detectCastleHandler-2022-07-02 11-22-32\5-matching_overlay.png')
        im2 = np.uint8(cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY))

        template_height,template_width = im1.shape
        input_squares = [[[98.125,192],
        [102.75, 105]],
        [[394.125, 346.5],
        [116.25,118.125]],
        [[145.875, 467.25],
        [127.5, 132.75]]]

        source_pts = []
        dest_pts = []
        sizes = []
        x_coords = []
        widths = []
        y_coords = []
        heights = []
        for input_square in input_squares:
            [[x, y],[w,h]] = input_square

            source_pts.append([0,0])
            source_pts.append([0, template_height])
            source_pts.append([template_width, 0])
            source_pts.append([template_width, template_height])

            dest_pts.append([x, y - h])
            dest_pts.append([x, y])
            dest_pts.append([x + w, y - h])
            dest_pts.append([x + w, y])
            x_coords.append(x)
            # x_coords.append(x + w)
            widths.append(w)
            # widths.append(w)

            y_coords.append(y)
            heights.append(h)
            # y_coords.append(y - h)
            sizes.append(w)

        script_logger.log(source_pts)
        script_logger.log(dest_pts)

        source_pts = np.array(source_pts)
        dest_pts = np.array(dest_pts)

        h, status = cv2.findHomography(source_pts, dest_pts)
        script_logger.log(np.dot(h, np.array([0,0,1])))
        script_logger.log(x_coords)
        script_logger.log(y_coords)
        script_logger.log(widths)
        script_logger.log(heights)
        # plt.plot(y_coords, widths)
        # plt.show()
        # cv2.waitKey(0)
        # plt.plot(y_coords, heights)
        # plt.show()

        # img = get_corrected_img(im2, im1)
        # cv2.imshow('Corrected image', img)
        # cv2.waitKey(0)