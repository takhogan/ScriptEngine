import numpy as np

from skimage.color import rgb2lab
from skimage import io
from script_logger import ScriptLogger
script_logger = ScriptLogger()


class ColorCompareHelper:
    def __init__(self):
        pass

    @staticmethod
    def handle_color_compare(screencap_im_bgr, action, state):

        script_logger.log('colorCompareAction-' + str(action["actionGroup"]) + ' compareMode: ' + action["actionData"][
            "compareMode"] + ' reference color: ' + str(action['actionData']['referenceColor']))
        if action["actionData"]["compareMode"] == 'mean':
            img_colors = np.mean(screencap_im_bgr, axis=0)
            img_colors = [img_colors[2], img_colors[1], img_colors[0]]
            script_logger.log('colorCompareAction-' + str(action["actionGroup"]), 'mean color', img_colors)
        elif action["actionData"]["compareMode"] == 'mode':
            color_counts = {}
            # Iterate over each pixel
            for pixel_index in range(0, screencap_im_bgr.shape[0]):
                pixel = screencap_im_bgr[pixel_index]
                # Quantize the color values
                r, g, b = pixel // 4
                color_key = f"{b},{g},{r}"

                # Count occurrences of the color
                if color_key in color_counts:
                    color_counts[color_key] += 1
                else:
                    color_counts[color_key] = 1

            # Determine the mode color
            mode_color_key = None
            max_count = 0
            for key, count in color_counts.items():
                if count > max_count:
                    mode_color_key = key
                    max_count = count

            # Convert the mode color back to RGB and multiply by 4
            if mode_color_key:
                img_colors = [int(val) * 4 for val in mode_color_key.split(',')]
            else:
                img_colors = [0, 0, 0]  # Default/fallback values in case there's no mode color key
            script_logger.log('colorCompareAction-' + str(action["actionGroup"]), 'mode color:', str(img_colors))

        color_score = (100 - ColorCompareHelper.compare_colors(img_colors, [int(val) for val in action['actionData'][
            'referenceColor']])) / 100
        script_logger.log('colorCompareAction-' + str(action["actionGroup"]), 'color score', color_score)
        return color_score

    @staticmethod
    def compare_colors(left_color, right_color):

        color1_rgb = np.array([[left_color]], dtype=np.uint8) / 255.0
        color2_rgb = np.array([[right_color]], dtype=np.uint8) / 255.0
        # Convert from RGB to LAB
        color1_lab = rgb2lab(color1_rgb)
        color2_lab = rgb2lab(color2_rgb)
        # Calculate the Euclidean distance between the two LAB colors (Delta E)
        delta_e = np.sqrt(np.sum((color1_lab - color2_lab) ** 2))
        return delta_e