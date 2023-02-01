import random
import numpy as np
import cv2
from script_run_obj import ScriptRun

class ClickActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_point_choice(action, var_name, state, context, screen_width, screen_height):
        point_choice = (None, None)
        if action["actionData"]["pointList"]:
            point_choice = random.choice(action["actionData"]["pointList"])
            input_params_valid = len(str(action["actionData"]["sourceScreenWidth"])) > 0 and\
                action["actionData"]["sourceScreenWidth"] > 0 and\
                len(str(action["actionData"]["sourceScreenHeight"])) > 0 and\
                action["actionData"]["sourceScreenHeight"] > 0

            if input_params_valid and (action["actionData"]["sourceScreenWidth"] != screen_width) and\
                    (action["actionData"]["sourceScreenHeight"] != screen_height):
                print('clickaction rescaling: ', screen_width, action["actionData"]["sourceScreenWidth"], screen_height, action["actionData"]["sourceScreenHeight"])
                point_choice = (
                    ((screen_width / action["actionData"]["sourceScreenWidth"])) * point_choice[0],
                    ((screen_height / action["actionData"]["sourceScreenHeight"]) * point_choice[1])
                )
        if var_name is not None and len(var_name) > 0:
            print('clickaction-' + str(action["actionGroup"]), ' reading from ', var_name)
            input_points = eval(var_name, state)
            # print('input_points: ', input_points, var_name, state)
            if len(input_points) > 0:
                # potentially for loop here
                next_input_points = input_points[1:]
                input_point = input_points[0]
                # if len(next_input_points) > 0:
                #     context["run_queue"].append(
                #         ScriptRun(state, context, {
                #
                #         }, action)
                #     )
                state[var_name] = next_input_points
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
            else:
                print('clickaction-' + str(action["actionGroup"]), ' no points in input')
                    # print('point_choice : ', shape_xs, ', ', shape_ys, ', ', point_choice_index, ', ', point_choice)
        # print('point_choice : ', point_choice)
        return point_choice, state, context

    @staticmethod
    def draw_click(screenshot_bgr, point_choice, logs_path):
        # print(type(point_choice[0]), type(point_choice[1]), type(point_choice))
        cv2.circle(screenshot_bgr, list(map(int,point_choice)), radius=5, color=(0, 0, 255), thickness=-1)
        cv2.imwrite(logs_path + 'click_location-' + str(point_choice[0]) + '-' + str(point_choice[1]) + '.png', screenshot_bgr)