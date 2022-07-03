import argparse

import cv2
import numpy as np


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

        print('kp1 : ', kp1, ' des1 : ', des1, ' kp2 : ', kp2, ' des2 : ', des2)

        index_params = dict(algorithm=6,
                            table_number=6,
                            key_size=12,
                            multi_probe_level=2)
        search_params = {}
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.knnMatch(des1, des2, k=2)
        matches = sorted(matches, key=lambda x: x.distance)
        print(' matches : ', list(map(len, matches)))
        # As per Lowe's ratio test to filter good matches
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                if match_pair[0].distance < 1 * match_pair[1].distance:
                    good_matches.append(match_pair[0])
        print(len(good_matches))
        start_red = 255
        for good_match in good_matches:
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
        im2 = cv2.imread(r'C:\Users\takho\ScriptEngine\logs\realmScanner-2022-07-02 11-22-11\detectCastleHandler-2022-07-02 11-22-32\5-matching_overlay.png')

        img = get_corrected_img(im2, im1)
        cv2.imshow('Corrected image', img)
        cv2.waitKey(0)