class DetectObjectHelper:
    def __init__(self):
        pass

    @staticmethod
    def get_detect_area(action, state):
        screencap_im_bgr = None
        match_point = None
        var_name = action["actionData"]["inputExpression"]
        if var_name is not None and len(var_name) > 0:
            input_area = eval(var_name, state)
            if len(input_area) > 0:
                # potentially for loop here
                # next_input_points = input_area[1:]
                input_area = input_area[0]
                # if len(next_input_points) > 0:
                #     context["replay_stack"].append(action)
                # state[var_name] = next_input_points
                if action["actionData"]["targetContext"] == "detectResult":
                    if input_area["input_type"] == "rectangle":
                        pass
                        # point_choice = (input_area["point"][0] + width_coord, input_area["point"][1] + height_coord)
                    elif input_area["input_type"] == "shape":
                        screencap_im_bgr = input_area["matched_area"]
                        match_point = (
                            input_area["point"][0],
                            input_area["point"][1]
                        )
        return screencap_im_bgr, match_point
