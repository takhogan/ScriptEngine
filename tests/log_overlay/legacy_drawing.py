"""The log-image drawing code as it was before overlays, kept as the parity reference.

Copied from ImageMatcher.create_result_im, ClickActionHelper.draw_point_choice /
draw_click_and_drag and ColorCompareHelper.create_color_compare_post_image, with
only the logging and file writes removed. The overlay builders must render to
exactly these pixels. Do not change the drawing here to match new behaviour:
change the test's expectations instead, so every divergence is deliberate.
"""
import cv2
import numpy as np


def adjust_box_to_bounds(pt, box_width, box_height, screen_width, screen_height, box_thickness):
    x_overshoot = pt[0] + box_width + box_thickness - screen_width
    y_overshoot = pt[1] + box_height + box_thickness - screen_height
    return (
        max(0, box_width - x_overshoot if x_overshoot > 0 else box_width),
        max(0, box_height - y_overshoot if y_overshoot > 0 else box_height)
    )


def create_result_im(detectObject, screencap_im_bgr, input_expression_match_point_xy_absolute, screencap_search_bgr, matches, match_result):
    result_im_bgr = screencap_im_bgr.copy()
    h, w = screencap_search_bgr.shape[0:2]
    if len(screencap_search_bgr.shape) < 3:
        screencap_search_bgr = cv2.cvtColor(screencap_search_bgr, cv2.COLOR_GRAY2BGR)
    threshold = float(detectObject['actionData']['threshold'])
    if detectObject['actionData']['detectActionType'] == "floatingObject":
        if len(matches) == 0:
            valid_matched_points = np.where(np.isinf(match_result) | np.isnan(match_result), -np.inf, match_result)
            max_valid_point = np.max(valid_matched_points)
            if max_valid_point != -np.inf:
                best_point_yx_relative = np.unravel_index(np.argmax(valid_matched_points), valid_matched_points.shape)
                best_point_score = float(match_result[best_point_yx_relative])
                best_point_xy_relative = (best_point_yx_relative[1], best_point_yx_relative[0])
                box_w, box_h = adjust_box_to_bounds(best_point_xy_relative, w, h, screencap_im_bgr.shape[1], screencap_im_bgr.shape[0], 2)
                end_y = min(best_point_xy_relative[1] + box_h, result_im_bgr.shape[0])
                end_x = min(best_point_xy_relative[0] + box_w, result_im_bgr.shape[1])
                slice_h = end_y - best_point_xy_relative[1]
                slice_w = end_x - best_point_xy_relative[0]
                result_im_bgr[
                    best_point_xy_relative[1]:best_point_xy_relative[1] + box_h,
                    best_point_xy_relative[0]:best_point_xy_relative[0] + box_w
                ] = screencap_search_bgr[:slice_h, :slice_w]
                result_im_bgr = cv2.addWeighted(result_im_bgr, 0.3, screencap_im_bgr, 0.7, 0)
                top_left = (int(best_point_xy_relative[0]), int(best_point_xy_relative[1]))
                bottom_right = (int(best_point_xy_relative[0] + box_w), int(best_point_xy_relative[1] + box_h))
                cv2.rectangle(result_im_bgr, top_left, bottom_right, (0, 0, int((255 * best_point_score + 255) / 2)), 2)
    else:
        top_left = (
            int(matches[0]['point'][0] - input_expression_match_point_xy_absolute[0]),
            int(matches[0]['point'][1] - input_expression_match_point_xy_absolute[1]),
        )
        bottom_right = (
            int(matches[0]['point'][0] + w - input_expression_match_point_xy_absolute[0]),
            int(matches[0]['point'][1] + h - input_expression_match_point_xy_absolute[1]),
        )
        cv2.rectangle(screencap_im_bgr, top_left, bottom_right, (0, 0, int(255 * matches[0]['score'])), 2)

    overlay = result_im_bgr.copy()
    alpha = 0.5
    match_data = []
    for match_obj in matches:
        if match_obj['score'] < threshold:
            continue
        match_point_xy_absolute = tuple(map(int, match_obj['point']))
        match_point_xy_relative = (
            int(match_point_xy_absolute[0] - input_expression_match_point_xy_absolute[0]),
            int(match_point_xy_absolute[1] - input_expression_match_point_xy_absolute[1])
        )
        box_w, box_h = adjust_box_to_bounds(
            match_point_xy_relative, w, h, screencap_im_bgr.shape[1], screencap_im_bgr.shape[0], 2
        )
        match_data.append((match_point_xy_relative, box_w, box_h, match_obj['score']))

    if 'maxMatches' in detectObject['actionData'] and str(detectObject['actionData']['maxMatches']).isdigit():
        max_matches = int(detectObject['actionData']['maxMatches'])
    else:
        max_matches = 1

    if detectObject['actionData']['detectActionType'] == "floatingObject":
        for pt, box_w, box_h, score in match_data:
            end_y = min(pt[1] + box_h, result_im_bgr.shape[0])
            end_x = min(pt[0] + box_w, result_im_bgr.shape[1])
            slice_h = end_y - pt[1]
            slice_w = end_x - pt[0]
            result_im_bgr[pt[1]:pt[1] + box_h, pt[0]:pt[0] + box_w] = screencap_search_bgr[:slice_h, :slice_w]
        result_im_bgr = cv2.addWeighted(overlay, alpha, result_im_bgr, 1 - alpha, 0)

    for pt, box_w, box_h, score in match_data:
        cv2.rectangle(overlay, pt, (int(pt[0] + box_w), int(pt[1] + box_h)), (0, 0, 255), thickness=-1)
    result_im_bgr = cv2.addWeighted(overlay, alpha, result_im_bgr, 1 - alpha, 0)

    for match_index, (pt, box_w, box_h, score) in enumerate(match_data):
        if match_index >= max_matches:
            break
        cv2.rectangle(result_im_bgr, pt, (int(pt[0] + box_w), int(pt[1] + box_h)), (int((255 * score + 255) / 2), 0, 0), 2)

    if detectObject['input_obj']['fixed_scale']:
        rescaled_base = detectObject['input_obj'].get('original_image_blurred')
        if rescaled_base is None:
            rescaled_base = detectObject['input_obj']['original_image']
        rescaled_result_im_bgr = rescaled_base.copy()
        ix = int(input_expression_match_point_xy_absolute[0])
        iy = int(input_expression_match_point_xy_absolute[1])
        h0, w0 = int(screencap_im_bgr.shape[0]), int(screencap_im_bgr.shape[1])
        rescaled_result_im_bgr[iy: iy + h0, ix: ix + w0] = result_im_bgr
        top_left = (int(input_expression_match_point_xy_absolute[0]), int(input_expression_match_point_xy_absolute[1]))
        bottom_right = (
            int(input_expression_match_point_xy_absolute[0] + screencap_im_bgr.shape[1]),
            int(input_expression_match_point_xy_absolute[1] + screencap_im_bgr.shape[0])
        )
        cv2.rectangle(rescaled_result_im_bgr, top_left, bottom_right, (255, 0, 0), 1)
    else:
        rescaled_result_im_bgr = result_im_bgr
    return rescaled_result_im_bgr


def draw_point_choice(screenshot_bgr, point_choice, point_list):
    overlay = screenshot_bgr.copy()
    if point_list['input_type'] == 'point_list':
        for point in point_list['point_list']:
            cv2.circle(overlay, point, radius=1, color=(0, 0, 255), thickness=-1)
    elif point_list['input_type'] == 'rectangle':
        cv2.rectangle(
            overlay,
            point_list["point"],
            (int(point_list["point"][0] + point_list["width"]),
             int(point_list["point"][1] + point_list["height"])),
            color=(0, 0, 255),
            thickness=-1
        )
    elif point_list['input_type'] == 'shape':
        shape_ys, shape_xs = np.where(point_list["output_mask"] > 1)
        for point in zip(shape_xs, shape_ys):
            cv2.circle(
                overlay,
                (int(point_list["point"][0] + point[0]), int(point_list["point"][1] + point[1])),
                radius=1, color=(0, 0, 255), thickness=-1
            )
    alpha = 0.5
    screenshot_bgr = cv2.addWeighted(overlay, alpha, screenshot_bgr, 1 - alpha, 0)
    cv2.circle(screenshot_bgr, list(map(int, point_choice)), radius=5, color=(255, 0, 0), thickness=-1)
    return screenshot_bgr


def draw_click_and_drag(screenshot_bgr, source_point_choice, source_point_list, target_point_choice, target_point_list, deltas):
    screenshot_bgr = draw_point_choice(screenshot_bgr, source_point_choice, source_point_list)
    screenshot_bgr = draw_point_choice(screenshot_bgr, target_point_choice, target_point_list)
    traverse_x = source_point_choice[0]
    traverse_y = source_point_choice[1]
    for delta_pair in deltas:
        cv2.line(
            screenshot_bgr,
            (int(traverse_x), int(traverse_y)),
            (int(traverse_x + delta_pair[0]), int(traverse_y + delta_pair[1])),
            (255, 0, 0),
            3
        )
        traverse_x += delta_pair[0]
        traverse_y += delta_pair[1]
    return screenshot_bgr


def create_color_compare_post_image(matched_area_bgr, original_image, original_image_blurred, match_point, img_colors):
    base_image = original_image_blurred
    if base_image is None:
        base_image = original_image
    if base_image is None:
        base_image = matched_area_bgr
    post_image = base_image.copy()
    match_x = int(match_point[0])
    match_y = int(match_point[1])
    match_height, match_width = matched_area_bgr.shape[:2]
    end_y = min(match_y + match_height, post_image.shape[0])
    end_x = min(match_x + match_width, post_image.shape[1])
    slice_h = end_y - match_y
    slice_w = end_x - match_x
    post_image[match_y:end_y, match_x:end_x] = matched_area_bgr[:slice_h, :slice_w]
    cv2.rectangle(post_image, (match_x, match_y), (match_x + match_width, match_y + match_height), (255, 0, 0), 1)
    square_size = max(12, min(match_height, match_width) // 3)
    square_size = min(square_size, slice_h, slice_w)
    color_bgr = np.array([img_colors[2], img_colors[1], img_colors[0]], dtype=np.uint8)
    post_image[match_y:match_y + square_size, match_x:match_x + square_size] = color_bgr
    cv2.rectangle(post_image, (match_x, match_y), (match_x + square_size, match_y + square_size), (0, 255, 0), 1)
    return post_image


def blur_like_executor(image):
    """original_image_blurred as script_action_executor computes it."""
    blurred = cv2.copyMakeBorder(image.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
    blurred = cv2.GaussianBlur(blurred, (31, 31), 0)
    return blurred[15:-15, 15:-15]
