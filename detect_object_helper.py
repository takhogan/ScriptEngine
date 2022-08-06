from script_engine_utils import generate_context_switch_action

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

    @staticmethod
    def append_to_run_queue(action, state, context, matches):
        state_copy = state.copy()
        context_copy = context.copy()
        for match in matches[1:action["actionData"]["maxMatches"]]:
            context["run_queue"].append(
                generate_context_switch_action(action["childGroups"], state_copy, context_copy, {
                    "state": {
                        action['actionData']['outputVarName']: [match]
                    }
                })
            )
        state[action['actionData']['outputVarName']] = [matches[0]]
        return state, context
