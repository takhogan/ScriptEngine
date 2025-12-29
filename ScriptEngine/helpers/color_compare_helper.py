import numpy as np
import cv2

from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()


class ColorCompareHelper:
    def __init__(self):
        pass

    @staticmethod
    def handle_color_compare(action):

        screencap_im_bgr = action['input_obj']['screencap_im_bgr'].copy()
        if script_logger.get_log_level() == 'info':
            input_image_relative_path = script_logger.get_log_header() + '-colorCompareAction-inputImage.png'
            cv2.imwrite(script_logger.get_log_folder() + input_image_relative_path, screencap_im_bgr)
            script_logger.get_action_log().set_pre_file(
                'image',
                input_image_relative_path
            )

        pre_log_1 = 'Compare Mode: {}'.format(
            action["actionData"]["compareMode"]
        )
        script_logger.log(pre_log_1)

        pre_log_2 = 'Reference Color: {}'.format(
            str(action['actionData']['referenceColor'])
        )
        script_logger.log(pre_log_2)

        masked_screencap_im_bgr_pixels = screencap_im_bgr[np.where(action['input_obj']['screencap_mask'] > 1)]

        pre_log_3 = ''
        if action["actionData"]["compareMode"] == 'mean':
            img_colors = np.mean(masked_screencap_im_bgr_pixels, axis=0)
            img_colors = [img_colors[2], img_colors[1], img_colors[0]]
            pre_log_3 = 'Mean Color: {}'.format(img_colors)
        elif action["actionData"]["compareMode"] == 'mode':
            color_counts = {}
            # Iterate over each pixel
            for pixel_index in range(0, masked_screencap_im_bgr_pixels.shape[0]):
                pixel = masked_screencap_im_bgr_pixels[pixel_index]
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
            pre_log_3 = 'Mode Color: {}'.format(img_colors)
        script_logger.log(pre_log_3)

        ref_color_ints = list(map(int, action['actionData']['referenceColor']))
        color_score = (100 - ColorCompareHelper.compare_colors(img_colors, ref_color_ints)) / 100

        post_log = 'Color Score: {}'.format(color_score)

        script_logger.get_action_log().add_supporting_file(
            'text',
            'compare-result.txt',
            pre_log_1 + '\n' + pre_log_2 + '\n' + pre_log_3 + '\n' + post_log
        )

        input_color_relative_path = 'input_color.png'
        ColorCompareHelper.create_color_image(
            img_colors, script_logger.get_log_path_prefix() + input_color_relative_path
        )
        script_logger.get_action_log().set_post_file('image', input_color_relative_path)

        reference_color_relative_path = 'reference_color.png'
        ColorCompareHelper.create_color_image(
            ref_color_ints, script_logger.get_log_path_prefix() + reference_color_relative_path
        )
        script_logger.get_action_log().set_post_file('image', reference_color_relative_path)

        return color_score

    @staticmethod
    def compare_colors(left_color, right_color):
        from skimage.color import rgb2lab
        color1_rgb = np.array([[left_color]], dtype=np.uint8) / 255.0
        color2_rgb = np.array([[right_color]], dtype=np.uint8) / 255.0
        # Convert from RGB to LAB
        color1_lab = rgb2lab(color1_rgb)
        color2_lab = rgb2lab(color2_rgb)
        # Calculate the Euclidean distance between the two LAB colors (Delta E)
        delta_e = np.sqrt(np.sum((color1_lab - color2_lab) ** 2))
        return delta_e

    @staticmethod
    def create_color_image(rgb, filename):
        # Create a 64x64x3 array of the specified color
        # Note: OpenCV uses BGR format instead of RGB
        color = np.array([rgb[2], rgb[1], rgb[0]])  # Convert RGB to BGR
        image = np.full((64, 64, 3), color, dtype=np.uint8)

        # Write the image to a file
        cv2.imwrite(filename, image)