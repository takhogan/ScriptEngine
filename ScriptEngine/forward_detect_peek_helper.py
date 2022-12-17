class ForwardDetectPeekHelper:
    def __init__(self):
        pass

    @staticmethod
    def load_forward_peek_result(action, state, context):
        if 'results_precalculated' in action['actionData'] and action['actionData']['results_precalculated']:
            if 'state' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["state"].items():
                    state[key] = value
            if 'context' in action["actionData"]["update_dict"]:
                for key, value in action["actionData"]["update_dict"]["context"].items():
                    context[key] = value
            return_tuple = (action['actionData']['action_result'], state, context)
            action['actionData']['screencap_im_bgr'] = None
            action['actionData']['results_precalculated'] = False
            action['actionData']['update_dict'] = None
            return return_tuple
        return None

    @staticmethod
    def save_forward_peek_results(action, update_dict, action_result, context):
        if 'detect_run_type' in action['actionData'] and \
                action['actionData']['detect_run_type'] == 'result_precalculation':
            action['actionData']['results_precalculated'] = True
            action['actionData']['update_dict'] = update_dict
            action['actionData']['action_result'] = action_result
            action['actionData']['detect_run_type'] = None
            context['action'] = action
        return action, context

    @staticmethod
    def load_screencap_im_bgr(action, screencap_im_bgr):
        if screencap_im_bgr is not None:
            return screencap_im_bgr
        if 'screencap_im_bgr' in action['actionData'] and action['actionData']['screencap_im_bgr'] is not None:
            screencap_im_bgr = action['actionData']['screencap_im_bgr']
        else:
            screencap_im_bgr = None
        return screencap_im_bgr
