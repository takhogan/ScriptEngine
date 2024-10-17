import random
import numpy as np
import cv2
from script_logger import ScriptLogger
from script_engine_utils import state_eval
from script_action_log import ScriptActionLog
from typing import Tuple, Callable
script_logger = ScriptLogger()

class ClickActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_remapping_function(action, screen_width, screen_height) -> Callable:
        def remapping_function(point):
            return (
                int(((screen_width / float(action["actionData"]["sourceScreenWidth"]))) * point[0]),
                int(((screen_height / float(action["actionData"]["sourceScreenHeight"])) * point[1]))
            )
        return remapping_function

    @staticmethod
    def get_point_choice(action, var_name, state, context, screen_width, screen_height):
        point_choice = (None, None)
        point_list = []
        if "pointList" in action["actionData"] and len(action["actionData"]["pointList"]) > 0:
            pre_log = 'pointList in actionData, choosing point from pointlist'
            point_choice = random.choice(action["actionData"]["pointList"])
            input_params_valid = len(str(action["actionData"]["sourceScreenWidth"])) > 0 and\
                int(action["actionData"]["sourceScreenWidth"]) > 0 and\
                len(str(action["actionData"]["sourceScreenHeight"])) > 0 and\
                int(action["actionData"]["sourceScreenHeight"]) > 0
            script_logger.log(pre_log)
            point_choice_log = 'Point chosen: {}'.format(str(point_choice))
            pre_log += '\n' + point_choice_log
            script_logger.log(point_choice_log)
            point_list = action["actionData"]["pointList"]
            if input_params_valid and (action["actionData"]["sourceScreenWidth"] != screen_width) and\
                    (action["actionData"]["sourceScreenHeight"] != screen_height):
                rescaling_log = 'difference in device window size detected.' +\
                                ' Remapping point choice from screen (wxh) ({}x{}) to screen ({}x{})'.format(
                                    str(action["actionData"]["sourceScreenWidth"]),
                                    str(action["actionData"]["sourceScreenHeight"]),
                                    str(screen_width),
                                    str(screen_height)
                                )
                pre_log += '\n' + rescaling_log
                script_logger.log(rescaling_log)
                remapping_function = ClickActionHelper.get_remapping_function(action, screen_width, screen_height)
                point_choice = remapping_function(point_choice)
                new_point_choice_log = 'New point chosen: {}'.format(str(point_choice))
                pre_log += '\n' + new_point_choice_log
                script_logger.log(new_point_choice_log)
                point_list = point_list.copy()
                remapping_log = 'Remapping {} point list points'.format(len(point_list))
                pre_log += '\n' + remapping_log
                script_logger.log(remapping_log)
                point_list = list(map(remapping_function, point_list))
            point_list = {
                'input_type' : 'point_list',
                'point_list' : point_list
            }
        else:
            pre_log = 'pointList not in actionData'
            script_logger.log(pre_log)

        if var_name is not None and len(var_name) > 0:
            input_expression_log = 'inputExpression {} was not null or blank, reading from inputExpression'.format(
                var_name
            )
            pre_log += '\n' + input_expression_log
            script_logger.log(input_expression_log)
            input_point = state_eval(var_name, {}, state)

            if input_point["input_type"] == "rectangle":
                width_coord = random.random() * input_point["width"]
                height_coord = random.random() * input_point['height']
                point_choice = (input_point["point"][0] + width_coord, input_point["point"][1] + height_coord)
            elif input_point["input_type"] == "shape":
                shape_ys, shape_xs = np.where(input_point["shape"] > 1)
                point_choice_index = np.random.randint(0, shape_xs.shape[0])
                point_choice = (
                    input_point["point"][0] + shape_xs[point_choice_index],
                    input_point["point"][1] + shape_ys[point_choice_index]
                )
            input_expression_point_choice_log = 'point chosen from input_expression: {}'.format(str(point_choice))
            pre_log += '\n' + input_expression_point_choice_log
            script_logger.log(input_expression_point_choice_log)
            point_list = input_point
        script_logger.get_action_log().add_pre_file(
            'text',
            'clickActionPointChoice-log.txt',
            pre_log
        )
        return point_choice, point_list, state, context

    @staticmethod
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
            shape_ys, shape_xs = np.where(point_list["shape"] > 1)
            for point in zip(shape_xs, shape_ys):
                cv2.circle(
                    overlay,
                    (
                        int(point_list["point"][0] + point[0]),
                        int(point_list["point"][1] + point[1])
                    ),
                    radius=1,
                    color=(0, 0, 255),
                    thickness=-1
                )

        alpha = 0.5  # 0.0 fully transparent, 1.0 fully opaque
        screenshot_bgr = cv2.addWeighted(overlay, alpha, screenshot_bgr, 1 - alpha, 0)
        cv2.circle(screenshot_bgr, list(map(int, point_choice)), radius=5, color=(255, 0, 0), thickness=-1)
        return screenshot_bgr

    @staticmethod
    def draw_click(screenshot_bgr, point_choice, point_list):
        script_logger = ScriptLogger.get_logger()
        script_logger.log('logging with the new threaded script logger')

        ClickActionHelper.draw_point_choice(screenshot_bgr, point_choice, point_list)
        output_image_relative_path = 'clickLocation.png'
        cv2.imwrite(script_logger.get_log_path_prefix() + output_image_relative_path, screenshot_bgr)
        # script_logger.log()
        script_logger.get_action_log().set_post_file(
            'image',
            output_image_relative_path
        )

    @staticmethod
    def draw_click_and_drag(screenshot_bgr,
                            source_point_choice, source_point_list,
                            target_point_choice, target_point_list,
                            deltas):
        ClickActionHelper.draw_point_choice(screenshot_bgr, source_point_choice, source_point_list)
        ClickActionHelper.draw_point_choice(screenshot_bgr, target_point_choice, target_point_list)
        traverse_x = source_point_choice[0]
        traverse_y = source_point_choice[1]
        for delta_pair in deltas:
            cv2.line(
                screenshot_bgr,
                (traverse_x, traverse_y),
                (traverse_x + delta_pair[0], traverse_y + delta_pair[1]),
                (255, 0, 0),
                1
            )
            traverse_x += delta_pair[0]
            traverse_y += delta_pair[1]

        output_image_relative_path = 'dragPath.png'
        cv2.imwrite(script_logger.get_log_path_prefix() + output_image_relative_path, screenshot_bgr)
        script_logger.log('Saving dragPath.png')
        script_logger.get_action_log().set_post_file(
            'image',
            output_image_relative_path
        )