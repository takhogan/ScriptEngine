import random
import numpy as np

class ClickActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_point_choice(action, var_name, state, context):
        point_choice = random.choice(action["actionData"]["pointList"]) if action["actionData"]["pointList"] else (None, None)
        if var_name is not None and len(var_name) > 0:
            input_points = eval(var_name, state)
            if len(input_points) > 0:
                # potentially for loop here
                next_input_points = input_points[1:]
                input_point = input_points[0]
                if len(next_input_points) > 0:
                    context["replay_stack"].append(action)
                state[var_name] = next_input_points
                if input_point["input_type"] == "rectangle":
                    width_coord = random.random() * input_point["width"]
                    height_coord = random.random() * input_point['height']
                    point_choice = (input_point["point"][0] + width_coord, input_point["point"][1] + height_coord)
                elif input_point["input_type"] == "shape":
                    shape_xs, shape_ys = np.where(input_point["shape"] > 1)
                    point_choice_index = np.random.randint(0, shape_xs.shape[0])
                    point_choice = (
                        input_point["point"][0] + shape_xs[point_choice_index],
                        input_point["point"][1] + shape_ys[point_choice_index]
                    )
        return point_choice, state, context