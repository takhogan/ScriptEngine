import random
import numpy as np
import cv2
from script_logger import ScriptLogger
script_logger = ScriptLogger()

class ClickActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_point_choice(action, var_name, state, context, screen_width, screen_height):
        point_choice = (None, None)
        if action["actionData"]["pointList"]:
            point_choice = random.choice(action["actionData"]["pointList"])
            input_params_valid = len(str(action["actionData"]["sourceScreenWidth"])) > 0 and\
                int(action["actionData"]["sourceScreenWidth"]) > 0 and\
                len(str(action["actionData"]["sourceScreenHeight"])) > 0 and\
                int(action["actionData"]["sourceScreenHeight"]) > 0

            if input_params_valid and (action["actionData"]["sourceScreenWidth"] != screen_width) and\
                    (action["actionData"]["sourceScreenHeight"] != screen_height):

                script_logger.log('clickaction rescaling: ', screen_width, action["actionData"]["sourceScreenWidth"], screen_height, action["actionData"]["sourceScreenHeight"])
                point_choice = (
                    int(((screen_width / float(action["actionData"]["sourceScreenWidth"]))) * point_choice[0]),
                    int(((screen_height / float(action["actionData"]["sourceScreenHeight"])) * point_choice[1]))
                )
        if var_name is not None and len(var_name) > 0:
            script_logger.log('clickaction-' + str(action["actionGroup"]), ' reading from ', var_name)
            input_point = eval(var_name, state.copy())

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
                    # script_logger.log('point_choice : ', shape_xs, ', ', shape_ys, ', ', point_choice_index, ', ', point_choice)
        # script_logger.log('point_choice : ', point_choice)
        return point_choice, state, context

    @staticmethod
    def draw_click(screenshot_bgr, point_choice, logs_path, log_level='info'):
        # script_logger.log(type(point_choice[0]), type(point_choice[1]), type(point_choice))
        cv2.circle(screenshot_bgr, list(map(int,point_choice)), radius=5, color=(0, 0, 255), thickness=-1)
        if log_level == 'info':
            cv2.imwrite(logs_path + 'click_location-' + str(point_choice[0]) + '-' + str(point_choice[1]) + '.png', screenshot_bgr)