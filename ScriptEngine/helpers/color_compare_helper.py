import numpy as np

from ScriptEngine.common.logging.script_logger import ScriptLogger, thread_local_storage
from ScriptEngine.common.logging import action_result
from ScriptEngine.common.logging.log_overlay import Overlay, bgr_to_hex, log_overlay
script_logger = ScriptLogger()


class ColorCompareHelper:
    def __init__(self):
        pass

    @staticmethod
    def create_color_compare_overlay(matched_area_bgr, original_image, original_image_blurred, match_point, img_colors):
        """The colorCompare post image as a log overlay.

        The sharp matched area sits in the blurred full screenshot (matching
        detectObject's post image), with the measured color as a swatch in its
        top left corner. Without a screenshot, the matched area is the canvas.
        The pre image is the matched area, which is the screenshot itself when
        there is no input expression (the log store then writes it once).
        """
        match_x = int(match_point[0])
        match_y = int(match_point[1])
        match_height, match_width = matched_area_bgr.shape[:2]

        capture = original_image if original_image is not None else matched_area_bgr
        if original_image is None and original_image_blurred is not None:
            # Only the blurred screenshot was kept; it has to be stored as is.
            capture = original_image_blurred
        overlay = Overlay('colorCompareAction', capture.shape[1], capture.shape[0], pre_image_key='input')
        overlay.images['capture'] = capture
        overlay.layers.append({'op': 'image', 'image': 'capture', 'at': [0, 0]})
        if original_image is not None and original_image_blurred is not None:
            # original_image_blurred is this same blur of the screenshot.
            overlay.layers.append({'op': 'blur', 'kernel': 31})
        overlay.images['input'] = matched_area_bgr
        overlay.layers.append({'op': 'image', 'image': 'input', 'at': [match_x, match_y]})

        # Border around the matched area (blue, matching detectObject).
        overlay.layers.append({
            'op': 'rect', 'p1': [match_x, match_y], 'p2': [match_x + match_width, match_y + match_height],
            'color': bgr_to_hex((255, 0, 0)), 'thickness': 1
        })

        # The input color as a square in the top left corner of the matched
        # area, clamped so it never overflows the matched region or the canvas,
        # outlined in green (distinct from the blue match-area border).
        slice_h = min(match_y + match_height, overlay.height) - match_y
        slice_w = min(match_x + match_width, overlay.width) - match_x
        square_size = max(12, min(match_height, match_width) // 3)
        square_size = min(square_size, slice_h, slice_w)
        color_bgr = np.array([img_colors[2], img_colors[1], img_colors[0]], dtype=np.uint8)
        if square_size > 0:
            overlay.layers.append({
                'op': 'rect', 'p1': [match_x, match_y],
                'p2': [match_x + square_size - 1, match_y + square_size - 1],
                'color': bgr_to_hex(color_bgr), 'thickness': -1
            })
        overlay.layers.append({
            'op': 'rect', 'p1': [match_x, match_y], 'p2': [match_x + square_size, match_y + square_size],
            'color': bgr_to_hex((0, 255, 0)), 'thickness': 1
        })
        return overlay

    @staticmethod
    def create_color_compare_post_image(
        thread_script_logger, matched_area_bgr, original_image, original_image_blurred,
        match_point, img_colors, overlay_name
    ):
        thread_local_storage.script_logger = thread_script_logger
        log_overlay(
            ColorCompareHelper.create_color_compare_overlay(
                matched_area_bgr, original_image, original_image_blurred, match_point, img_colors
            ),
            overlay_name
        )

    @staticmethod
    def handle_color_compare(action, io_executor):

        screencap_im_bgr = action['input_obj']['screencap_im_bgr']

        pre_log_1 = 'Compare Mode: {}'.format(
            action["actionData"]["compareMode"]
        )
        script_logger.log(pre_log_1, level='debug')

        pre_log_2 = 'Reference Color: {}'.format(
            str(action['actionData']['referenceColor'])
        )
        script_logger.log(pre_log_2, level='debug')

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
        script_logger.log(pre_log_3, level='debug')

        ref_color_ints = list(map(int, action['actionData']['referenceColor']))
        color_score = (100 - ColorCompareHelper.compare_colors(img_colors, ref_color_ints)) / 100

        script_logger.log('Color Score: {}'.format(color_score), level='debug')
        match_point = action['input_obj'].get('match_point', (0, 0))
        script_logger.get_action_log().update_result({
            'compare_mode': action["actionData"]["compareMode"],
            'reference_color': ref_color_ints,
            'measured_color': img_colors,
            'score': color_score,
            'area': action_result.box(
                match_point[0], match_point[1], screencap_im_bgr.shape[1], screencap_im_bgr.shape[0]
            ),
        })

        # The screenshot (pre) and the input_color overlay (post, which feeds
        # the log video) are captured at info+ but skipped at error (no images
        # at error level).
        if script_logger.should_log('info'):
            post_image_script_logger = script_logger.copy()
            io_executor.submit(
                ColorCompareHelper.create_color_compare_post_image,
                post_image_script_logger,
                screencap_im_bgr,
                action['input_obj'].get('original_image'),
                action['input_obj'].get('original_image_blurred'),
                match_point,
                img_colors,
                'input_color'
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
