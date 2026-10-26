# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import random
import numpy as np
import cv2
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.common.logging.log_overlay import Overlay, bgr_to_hex, int_point, log_overlay, mask_image
from ScriptEngine.common.script_engine_utils import state_eval
from ScriptEngine.common.types import ScreenPlanImage
from typing import Tuple, Callable, List
script_logger = ScriptLogger()

class ClickActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def _calculate_interior_weights(point_list):
        points_arr = np.asarray(point_list, dtype=float)
        if points_arr.ndim != 2 or points_arr.shape[1] != 2:
            return None

        # We only work with integer coordinates inside the mask.
        int_points = np.round(points_arr).astype(int)
        min_x = np.min(int_points[:, 0])
        min_y = np.min(int_points[:, 1])
        max_x = np.max(int_points[:, 0])
        max_y = np.max(int_points[:, 1])

        # keep a 1px zero border for when the shape is a rectangle to ensure there are zeros
        width = max_x - min_x + 3 
        height = max_y - min_y + 3
        if width <= 2 or height <= 2:
            return None

        # Build occupancy mask for the point cloud.
        mask = np.zeros((height, width), dtype=np.uint8)
        shifted_x = int_points[:, 0] - min_x + 1
        shifted_y = int_points[:, 1] - min_y + 1
        mask[shifted_y, shifted_x] = 255

        distance_map = cv2.distanceTransform(mask, cv2.DIST_L2, 3)

        # max_distance = float(distance_map.max())
        # if max_distance > 0:
        #     visual_map = (distance_map / max_distance * 255).astype(np.uint8)
        # else:
        #     visual_map = distance_map.astype(np.uint8)
        # script_logger.log('visual_map', visual_map)
        # random_id = str(random.random() * 1000000)
        # cv2.imwrite(random_id + '_click_interior_weights.png', visual_map)
        
        # # Save the actual array data to a text file
        # np.savetxt(random_id + '_click_interior_weights_array.txt', visual_map, fmt='%d')


        interior_distances = distance_map[shifted_y, shifted_x]
        thin_threshold = 1.0
        interior_distances = np.maximum(interior_distances - thin_threshold, 0.0)
        if not np.isfinite(interior_distances).all() or np.all(interior_distances <= 0):
            return None

        return interior_distances

    @staticmethod
    def _choose_point_from_list(point_list, prefer_interior: bool):
        if len(point_list) == 0:
            return (None, None), 'none'
        if not prefer_interior or len(point_list) < 2:
            return random.choice(point_list), 'uniform'

        interior_weights = ClickActionHelper._calculate_interior_weights(point_list)
        if interior_weights is None:
            return random.choice(point_list), 'uniform'

        interior_weights = np.asarray(interior_weights, dtype=float)
        positive_indices = np.nonzero(interior_weights > 0)[0]
        if positive_indices.size == 0:
            return random.choice(point_list), 'boundary-only-fallback'

        filtered_weights = interior_weights[positive_indices]
        # Bias towards interior by squaring the distance-based weights.
        weights = np.square(filtered_weights)
        weight_sum = weights.sum()
        if not np.isfinite(weight_sum) or weight_sum == 0:
            return random.choice(point_list), 'boundary-only-fallback'

        probabilities = weights / weight_sum
        bias_index = int(np.random.choice(len(positive_indices), p=probabilities))
        return point_list[int(positive_indices[bias_index])], 'interior-distance'

    @staticmethod
    def get_remapping_function(source_screen_width, source_screen_height, screen_width, screen_height) -> Callable:
        def remapping_function(point):
            return (
                int(((screen_width / float(source_screen_width))) * point[0]),
                int(((screen_height / float(source_screen_height)) * point[1]))
            )
        return remapping_function

    @staticmethod
    def remap_points_to_screen(
        input_params_valid : bool, source_screen_width : int, source_screen_height : int,
        screen_width : int, screen_height : int, point_list : List[int], point_choice : Tuple[int, int]
    ):
        remap_log = ''
        if input_params_valid and (source_screen_width != screen_width) and \
                (source_screen_height != screen_height):
            rescaling_log = 'difference in device window size detected.' + \
                            ' Remapping point choice from screen (wxh) ({}x{}) to screen ({}x{})'.format(
                                str(source_screen_width),
                                str(source_screen_height),
                                str(screen_width),
                                str(screen_height)
                            )
            remap_log += '\n' + rescaling_log
            script_logger.log(rescaling_log, level='debug')
            remapping_function = ClickActionHelper.get_remapping_function(
                source_screen_width,
                source_screen_height,
                screen_width,
                screen_height
            )
            point_choice = remapping_function(point_choice)
            new_point_choice_log = 'New point chosen: {}'.format(str(point_choice))
            remap_log += '\n' + new_point_choice_log
            script_logger.log(new_point_choice_log, level='debug')
            point_list = point_list.copy()
            remapping_log = 'Remapping {} point list points'.format(len(point_list))
            remap_log += '\n' + remapping_log
            script_logger.log(remapping_log, level='debug')
            point_list = list(map(remapping_function, point_list))

        return point_list, point_choice, remap_log

    @staticmethod
    def get_point_choice(detectTypeData, var_name, point_list, state, screen_width, screen_height, point_index, prefer_interior=True):
        point_choice = (None, None)
        log_point_choice = (None, None)
        pre_log = ''

        if var_name is not None and len(var_name) > 0:
            input_expression_log = 'inputExpression {} was not null or blank, reading from inputExpression'.format(
                var_name
            )
            pre_log += '\n' + input_expression_log
            script_logger.log(input_expression_log, level='debug')
            input_point = state_eval(var_name, {}, state)

            input_expression_type = 'unknown'

            if input_point["input_type"] == "rectangle":
                width_coord = random.random() * input_point["width"]
                height_coord = random.random() * input_point['height']
                point_choice = (input_point["point"][0] + width_coord, input_point["point"][1] + height_coord)
                input_expression_type = 'rectangle'
            elif input_point["input_type"] == "shape":
                shape_ys, shape_xs = np.where(input_point["output_mask"] > 1)
                relative_points = list(zip(shape_xs.tolist(), shape_ys.tolist()))
                if len(relative_points) == 0:
                    assert False, 'attempted to fetch point from input shape, but input shape was empty'
                else:
                    relative_choice, selection_strategy = ClickActionHelper._choose_point_from_list(
                        relative_points,
                        prefer_interior
                    )
                    if relative_choice == (None, None):
                        relative_choice = random.choice(relative_points)
                        selection_strategy = 'fallback-uniform'
                    point_choice = (
                        input_point["point"][0] + int(relative_choice[0]),
                        input_point["point"][1] + int(relative_choice[1])
                    )
                input_expression_type = 'shape ({})'.format(selection_strategy)
            source_screen_width = input_point["original_width"]
            source_screen_height = input_point["original_height"]
            log_point_choice = point_choice
            [], point_choice, remap_log = ClickActionHelper.remap_points_to_screen(
                True, source_screen_width, source_screen_height,
                screen_width, screen_height, [], point_choice
            )
            pre_log += '\n' + remap_log
            input_expression_point_choice_log = 'point chosen from input_expression of type {} : {}'.format(
                input_expression_type,
                str(point_choice)
            )
            pre_log += '\n' + input_expression_point_choice_log
            script_logger.log(input_expression_point_choice_log, level='debug')
            log_point_list = point_list = input_point
        elif len(point_list) > 0:
            pre_log = 'pointList in actionData, choosing point from pointlist'
            point_choice, selection_strategy = ClickActionHelper._choose_point_from_list(point_list, prefer_interior)
            log_point_choice = point_choice
            # positiveExamples are in pair format (normalized in script_loader)
            positive_examples = detectTypeData["positiveExamples"]
            first = positive_examples[0] if positive_examples else {}
            fixed_detect_obj = first.get("fixedObject")
            floating_detect_obj = first.get("floatingObject")
            obj = fixed_detect_obj if detectTypeData["detectActionType"] == "fixedObject" else floating_detect_obj
            source_screen_width = obj["sourceScreenWidth"] if obj is not None and "sourceScreenWidth" in obj else 0
            source_screen_height = obj["sourceScreenHeight"] if obj is not None and "sourceScreenHeight" in obj else 0



            input_params_valid = len(str(source_screen_width)) > 0 and\
                int(source_screen_width) > 0 and\
                len(str(source_screen_height)) > 0 and\
                int(source_screen_height) > 0
            script_logger.log(pre_log, level='debug')
            point_choice_log = 'Point chosen ({}): {}'.format(selection_strategy, str(point_choice))
            pre_log += '\n' + point_choice_log
            script_logger.log(point_choice_log, level='debug')
            log_point_list = {
                'input_type': 'point_list',
                'point_list': point_list
            }

            point_list, point_choice, remap_log = ClickActionHelper.remap_points_to_screen(
                input_params_valid, source_screen_width, source_screen_height,
                screen_width, screen_height, point_list, point_choice
            )
            point_list = {
                'input_type': 'point_list',
                'point_list': point_list
            }
            pre_log += '\n' + remap_log

        else:
            log_point_list = []
            pre_log = 'pointList not in actionData and inputExpression is None'
            script_logger.log(pre_log, level='debug')
        script_logger.get_action_log().add_supporting_file(
            'text',
            'clickActionPointChoice-{}-log.txt'.format(str(point_index)),
            pre_log
        )
        return point_choice, log_point_choice, point_list, log_point_list

    @staticmethod
    def input_screenshot(log_point_list):
        """The screenshot a click target was chosen from, or None.

        A target from an input expression is a match (or a transformed or
        nested match) that carries the screenshot it was found in, and its
        point and mask are in that screenshot's coordinates. Targets from the
        action's own point list have no screenshot behind them.
        """
        if isinstance(log_point_list, (dict, ScreenPlanImage)):
            if log_point_list.get('input_type') in ('shape', 'rectangle'):
                return log_point_list.get('original_image')
        return None

    @staticmethod
    def scale_point(point, scale_x, scale_y):
        return (point[0] * scale_x, point[1] * scale_y)

    @staticmethod
    def log_target(base_bgr, screen_width, screen_height,
                   point_choice, point_list, log_point_choice, log_point_list):
        """(point_choice, point_list) to draw one click target on `base_bgr`.

        A target chosen from `base_bgr` itself is drawn in its own coordinates,
        exactly where it was found. Anything else is in device coordinates
        (after the remap to the device's screen) and is scaled to the base:
        the action's point list keeps its candidate points, while a target from
        a different screenshot shows only the chosen point, since its candidate
        area belongs to that other image.
        """
        if base_bgr is ClickActionHelper.input_screenshot(log_point_list):
            return log_point_choice, log_point_list
        scale_x = base_bgr.shape[1] / float(screen_width)
        scale_y = base_bgr.shape[0] / float(screen_height)
        candidates = {'input_type': 'none'}
        if ClickActionHelper.input_screenshot(log_point_list) is None and \
                isinstance(point_list, dict) and point_list.get('input_type') == 'point_list':
            candidates = {
                'input_type': 'point_list',
                'point_list': [
                    tuple(map(int, ClickActionHelper.scale_point(point, scale_x, scale_y)))
                    for point in point_list['point_list']
                ]
            }
        return ClickActionHelper.scale_point(point_choice, scale_x, scale_y), candidates

    @staticmethod
    def has_point(point_choice):
        return point_choice is not None and None not in tuple(point_choice)

    @staticmethod
    def point_choice_layers(overlay, point_choice, point_list, mask_key='mask'):
        """Layers marking a click: the candidate area washed red, the chosen point in blue."""
        candidates = []
        if point_list['input_type'] == 'point_list':
            for point in point_list['point_list']:
                candidates.append({
                    'op': 'circle', 'center': int_point(point), 'radius': 1,
                    'color': bgr_to_hex((0, 0, 255)), 'thickness': -1
                })
        elif point_list['input_type'] == 'rectangle':
            candidates.append({
                'op': 'rect',
                'p1': int_point(point_list["point"]),
                'p2': [int(point_list["point"][0] + point_list["width"]),
                       int(point_list["point"][1] + point_list["height"])],
                'color': bgr_to_hex((0, 0, 255)), 'thickness': -1
            })
        elif point_list['input_type'] == 'shape':
            overlay.images[mask_key] = mask_image(point_list["output_mask"])
            candidates.append({
                'op': 'mask', 'image': mask_key, 'at': int_point(point_list["point"]),
                'color': bgr_to_hex((0, 0, 255))
            })

        layers = []
        if candidates:
            layers.append({'op': 'group', 'opacity': 0.5, 'layers': candidates})
        layers.append({
            'op': 'circle', 'center': int_point(point_choice), 'radius': 5,
            'color': bgr_to_hex((255, 0, 0)), 'thickness': -1
        })
        return layers

    @staticmethod
    def create_click_overlay(screenshot_bgr, point_choice, point_list):
        overlay = Overlay('mouseInteractionAction', screenshot_bgr.shape[1], screenshot_bgr.shape[0])
        overlay.images['capture'] = screenshot_bgr
        overlay.layers = [{'op': 'image', 'image': 'capture', 'at': [0, 0]}] + \
            ClickActionHelper.point_choice_layers(overlay, point_choice, point_list)
        overlay.meta = {'point_choice': int_point(point_choice), 'input_type': point_list['input_type']}
        return overlay

    @staticmethod
    def create_click_and_drag_overlay(screenshot_bgr,
                                      source_point_choice, source_point_list,
                                      target_point_choice, target_point_list,
                                      deltas):
        overlay = Overlay('mouseMoveAction', screenshot_bgr.shape[1], screenshot_bgr.shape[0])
        overlay.images['capture'] = screenshot_bgr
        overlay.layers = [{'op': 'image', 'image': 'capture', 'at': [0, 0]}] + \
            ClickActionHelper.point_choice_layers(overlay, source_point_choice, source_point_list, 'source_mask') + \
            ClickActionHelper.point_choice_layers(overlay, target_point_choice, target_point_list, 'target_mask')

        # The drag path: each delta is one segment from where the last one ended.
        traverse_x = source_point_choice[0]
        traverse_y = source_point_choice[1]
        path = [[int(traverse_x), int(traverse_y)]]
        for delta_pair in deltas:
            traverse_x += delta_pair[0]
            traverse_y += delta_pair[1]
            path.append([int(traverse_x), int(traverse_y)])
        overlay.layers.append({'op': 'polyline', 'points': path, 'color': bgr_to_hex((255, 0, 0)), 'thickness': 3})
        overlay.meta = {
            'source_point': int_point(source_point_choice),
            'target_point': int_point(target_point_choice),
            'path': path
        }
        return overlay

    @staticmethod
    def draw_click(screenshot_bgr, point_choice, point_list):
        script_logger = ScriptLogger.get_logger()

        # The screenshot (pre) and the clickLocation overlay (post) are kept at
        # info and debug; the overlay feeds the log video. Only the error level
        # (text-only, no images) skips them.
        if script_logger.get_log_level() == 'error':
            return

        log_overlay(
            ClickActionHelper.create_click_overlay(screenshot_bgr, point_choice, point_list),
            'clickLocation'
        )

    @staticmethod
    def draw_click_and_drag(screenshot_bgr,
                            source_point_choice, source_point_list,
                            target_point_choice, target_point_list,
                            deltas):
        script_logger = ScriptLogger.get_logger()

        # The screenshot (pre) and the dragPath overlay (post) are kept at info
        # and debug; the overlay feeds the log video. Only the error level
        # (text-only, no images) skips them.
        if script_logger.get_log_level() == 'error':
            return

        script_logger.log('Saving dragPath overlay', level='debug')
        log_overlay(
            ClickActionHelper.create_click_and_drag_overlay(
                screenshot_bgr,
                source_point_choice, source_point_list,
                target_point_choice, target_point_list,
                deltas
            ),
            'dragPath'
        )
