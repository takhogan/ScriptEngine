import numpy as np
import cv2

from ScriptEngine.common.logging.script_logger import ScriptLogger, thread_local_storage
script_logger = ScriptLogger()


class ColorCompareHelper:
    def __init__(self):
        pass

    @staticmethod
    def write_input_image_log(thread_script_logger, screencap_im_bgr, input_image_relative_path):
        thread_local_storage.script_logger = thread_script_logger
        thread_logger = ScriptLogger.get_logger()
        cv2.imwrite(thread_logger.get_log_path_prefix() + input_image_relative_path, screencap_im_bgr)
        thread_logger.get_action_log().set_pre_file(
            'image',
            input_image_relative_path
        )

    @staticmethod
    def create_color_compare_post_image(
        thread_script_logger, matched_area_bgr, original_image, original_image_blurred,
        match_point, img_colors, input_color_relative_path
    ):
        thread_local_storage.script_logger = thread_script_logger
        thread_logger = ScriptLogger.get_logger()

        # Use the precomputed blurred full original image as the backdrop so the
        # matched area is tied back to the original image (matches detectObject's
        # post-image format). Fall back to the unblurred original, then to the
        # matched area itself, if the blurred original is unavailable.
        base_image = original_image_blurred
        if base_image is None:
            base_image = original_image
        if base_image is None:
            base_image = matched_area_bgr
        post_image = base_image.copy()

        # Place the sharp matched area back into the blurred original at its
        # original location, clamped to the backdrop bounds.
        match_x = int(match_point[0])
        match_y = int(match_point[1])
        match_height, match_width = matched_area_bgr.shape[:2]
        end_y = min(match_y + match_height, post_image.shape[0])
        end_x = min(match_x + match_width, post_image.shape[1])
        slice_h = end_y - match_y
        slice_w = end_x - match_x
        post_image[match_y:end_y, match_x:end_x] = matched_area_bgr[:slice_h, :slice_w]

        # Border around the matched area (blue, matching detectObject).
        cv2.rectangle(
            post_image,
            (match_x, match_y),
            (match_x + match_width, match_y + match_height),
            (255, 0, 0),
            1
        )

        # Overlay the input color as a small square in the top left corner of
        # the matched area, clamped so it never overflows the matched region.
        square_size = max(12, min(match_height, match_width) // 3)
        square_size = min(square_size, slice_h, slice_w)
        color_bgr = np.array([img_colors[2], img_colors[1], img_colors[0]], dtype=np.uint8)
        post_image[match_y:match_y + square_size, match_x:match_x + square_size] = color_bgr

        # Outline around the input color swatch (green, distinct from the
        # blue match-area border).
        cv2.rectangle(
            post_image,
            (match_x, match_y),
            (match_x + square_size, match_y + square_size),
            (0, 255, 0),
            1
        )

        cv2.imwrite(thread_logger.get_log_path_prefix() + input_color_relative_path, post_image)
        thread_logger.get_action_log().set_post_file('image', input_color_relative_path)

    @staticmethod
    def create_color_compare_logs(thread_script_logger, img_colors, ref_color_ints, compare_mode, color_score):
        thread_local_storage.script_logger = thread_script_logger
        thread_logger = ScriptLogger.get_logger()

        reference_color_relative_path = 'reference_color.png'
        ColorCompareHelper.create_color_image(
            ref_color_ints, thread_logger.get_log_path_prefix() + reference_color_relative_path
        )
        thread_logger.get_action_log().add_supporting_file_reference('image', reference_color_relative_path)

        results_text = (
            'Compare Mode: {}\n'.format(compare_mode) +
            'Input Color: {}\n'.format(img_colors) +
            'Reference Color: {}\n'.format(ref_color_ints) +
            'Similarity Score: {}'.format(color_score)
        )
        thread_logger.get_action_log().add_supporting_file('text', 'results.txt', results_text)

    @staticmethod
    def handle_color_compare(action, io_executor):

        screencap_im_bgr = action['input_obj']['screencap_im_bgr'].copy()
        if script_logger.get_log_level() == 'info':
            input_image_relative_path = 'colorCompareAction-inputImage.png'
            thread_script_logger = script_logger.copy()
            io_executor.submit(
                ColorCompareHelper.write_input_image_log,
                thread_script_logger,
                screencap_im_bgr,
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

        # Get the mask if available, otherwise use the entire image
        screencap_mask = action['input_obj'].get('screencap_mask')
        if screencap_mask is not None:
            masked_screencap_im_bgr_pixels = screencap_im_bgr[np.where(screencap_mask > 1)]
        else:
            # If no mask is provided, use all pixels from the image
            masked_screencap_im_bgr_pixels = screencap_im_bgr.reshape(-1, 3)

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
        post_image_script_logger = script_logger.copy()
        io_executor.submit(
            ColorCompareHelper.create_color_compare_post_image,
            post_image_script_logger,
            screencap_im_bgr,
            action['input_obj'].get('original_image'),
            action['input_obj'].get('original_image_blurred'),
            action['input_obj'].get('match_point', (0, 0)),
            img_colors,
            input_color_relative_path
        )

        compare_logs_script_logger = script_logger.copy()
        io_executor.submit(
            ColorCompareHelper.create_color_compare_logs,
            compare_logs_script_logger,
            img_colors,
            ref_color_ints,
            action["actionData"]["compareMode"],
            color_score
        )

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