import math

import numpy as np
import random
import os
import cv2
from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()

class SearchPatternHelper:
    def __init__(self):
        pass

    def generate_pattern(self, pattern_action, context, log_folder, dir_path):
        # input_object = eval(patternAction["actionData"]["inputExpression"], {}, state)[0]
        # if input_object["input_type"] == "rectangle":
        #     width_coord = random.random() * input_object["width"]
        #     height_coord = random.random() * input_object['height']
        #     origin_point = (input_object["point"][0] + width_coord, input_object["point"][1] + height_coord)
        # elif input_object["input_type"] == "point_list":
        #     origin_point = random.choice(input_object["pointList"])
        # else:
        #     script_logger.log("input not recognized " + input_object)
        #     exit(0)
        from scipy.stats import truncnorm
        origin_point = (0,0)
        search_pattern = np.random.choice(pattern_action["actionData"]["searchPatterns"],
                         p=pattern_action["actionData"]["searchPatternProbabilities"])
        search_pattern = 'spiral'
        draggable_area_path = dir_path + '/' + pattern_action["actionData"]["draggableArea"]
        draggable_area = np.uint8(cv2.imread(draggable_area_path, cv2.IMREAD_GRAYSCALE))
        os.mkdir(log_folder + '/search_patterns/' + pattern_action["actionData"]["searchPatternID"])
        os.mkdir(log_folder + '/search_patterns/' + pattern_action["actionData"]["searchPatternID"] + '/errors')
        if search_pattern == 'spiral':
            spiral_width = truncnorm.rvs(0.9, 1, loc=0.95, scale=0.03)

            def spiral_func(displacement, a, direction):
                max_displacement = 0.8
                delta_displacement = truncnorm.rvs(0.05, max_displacement, loc=max_displacement/2, scale=max_displacement/3)
                new_theta = (math.sqrt(2) * math.sqrt(
                    2 * math.pi * (displacement + delta_displacement) - 1)) / math.sqrt(a)
                script_logger.log('new_theta ', new_theta)
                new_r = direction * a * new_theta / (2 * math.pi)
                return new_r * math.cos(new_theta), new_r * math.sin(new_theta), displacement + delta_displacement

            context["search_patterns"][pattern_action["actionData"]["searchPatternID"]] = {
                'last_point': origin_point,
                'current_point': origin_point,
                'step_index': -1,
                'displacement': 0,
                'spiral_modifier': spiral_width,
                'spiral_direction': random.randint(0, 1) * 2 - 1,
                'pattern_type': search_pattern,
                'draggable_area' : draggable_area,
                'draggable_area_path' : draggable_area_path,
                'search_function': spiral_func,
                'stitcher': cv2.Stitcher_create(cv2.STITCHER_SCANS),
                'stitch': None,
                'stitch_mask' : None,
                'stitcher_status' : None,
                'actual_current_point': (0, 0),
                'area_map': {}
            }
            return context
        elif search_pattern == 'grid':
            # pick an angle from 0 to 90, do a grid search, randomize movement length
            # need to figure out when you've hit the edge, set a threshold for change in image, don't do it with pure pixel values, use keypoint displacement or something, use stitching!
            #once you hit an edge need to go in another direction
            script_logger.log('search pattern not implemented ' + search_pattern)
            exit(0)
        else:
            script_logger.log('search pattern not implemented ' + search_pattern)
            exit(0)


        # patternAction["actionData"]["gridMode"]

    def execute_pattern(self, patternID, context):
        pattern_obj = context["search_patterns"][patternID]
        if pattern_obj["pattern_type"] == 'spiral':
            new_pos_x, new_pos_y, new_displacment = pattern_obj["search_function"](
                pattern_obj["displacement"],
                pattern_obj["spiral_modifier"],
                pattern_obj["spiral_direction"]
            )
            pattern_obj["last_point"] = pattern_obj["current_point"]
            pattern_obj["current_point"] = (new_pos_x, new_pos_y)
            pattern_obj["displacement"] = new_displacment
            pattern_obj["step_index"] += 1
            context["search_patterns"][patternID] = pattern_obj
            return pattern_obj["last_point"], (new_pos_x, new_pos_y), new_displacment, context
        elif pattern_obj["pattern_type"] == 'grid':
            pass
        else:
            script_logger.log('search pattern not implemented ' + pattern_obj["pattern_type"])
            exit(0)
        # delays = truncnorm.rvs(mins, maxes, loc=mean, scale=stddev) if action["actionData"]["clickCount"] > 1 else [
            # truncnorm.rvs(mins, maxes, loc=mean, scale=stddev)]
        pass

    def remap_search_pattern_points(self, width, height, source_pt, target_pt):
        x_min = min(source_pt[0], target_pt[0])
        y_min = min(source_pt[1], target_pt[1])
        source_pt_fit = (source_pt[0] - x_min, source_pt[1] - y_min)
        target_pt_fit = (target_pt[0] - x_min, target_pt[1] - y_min)
        x_diff = abs(source_pt[0] - target_pt[0])
        y_diff = abs(source_pt[1] - target_pt[1])

        if width > height:
            xy_ratio = width / height
            x_edge = 1 - x_diff / xy_ratio
            y_edge = 1 - y_diff
            # script_logger.log('1', width, height, xy_ratio)
        else:
            xy_ratio = height / width
            x_edge = 1 - x_diff
            y_edge = 1 - y_diff / xy_ratio
            # script_logger.log('1', width, height, xy_ratio)

        # script_logger.log('2', x_edge, y_edge, x_diff, y_diff)
        return source_pt_fit,target_pt_fit,x_edge,y_edge

    def fit_to_frame(self, source_pt_fit, target_pt_fit, x_edge, y_edge):
        x_edge_val = truncnorm.rvs(0, x_edge, loc=x_edge / 2, scale=x_edge / 4)
        y_edge_val = truncnorm.rvs(0, y_edge, loc=y_edge / 2, scale=y_edge / 4)
        new_source_pt, new_target_pt = (source_pt_fit[0] + x_edge_val, source_pt_fit[1] + y_edge_val), (
        target_pt_fit[0] + x_edge_val, target_pt_fit[1] + y_edge_val)
        # script_logger.log('3', source_pt_fit, target_pt_fit, x_edge_val, y_edge_val)
        return new_source_pt, new_target_pt


    def fit_pattern_to_frame(self, width, height, draggable_area, patterns):
        fitted_patterns = []
        for pattern in patterns:
            (source_pt, target_pt) = pattern
            source_pt_fit,target_pt_fit,x_edge,y_edge = self.remap_search_pattern_points(width, height, source_pt, target_pt)
            new_source_pt, new_target_pt = self.fit_to_frame(source_pt_fit, target_pt_fit, x_edge, y_edge)
            # if choice is inside of draggable_area, reroll up to 5 times, on the fifth try, break it into a smaller pieces
            for edge_reroll_index in range(0, 5):
                new_source_pt_loc = int(new_source_pt[0] * draggable_area.shape[1]), int(new_source_pt[1] * draggable_area.shape[1])

                if draggable_area[new_source_pt_loc[1], new_source_pt_loc[0]] == 0:
                    new_source_pt, new_target_pt = self.fit_to_frame(source_pt_fit, target_pt_fit, x_edge, y_edge)
                else:
                    break
            new_source_pt_loc = int(new_source_pt[0] * draggable_area.shape[1]), int(
                new_source_pt[1] * draggable_area.shape[1])
            if draggable_area[new_source_pt_loc[1], new_source_pt_loc[0]] == 0:
                halved_patterns = []
                for pattern in patterns:
                    (unfit_source_pt, unfit_target_pt) = pattern
                    halved_patterns += [
                        ((unfit_source_pt[0], unfit_source_pt[1]),((unfit_source_pt[0] + unfit_target_pt[0]) / 2, (unfit_source_pt[1] + unfit_target_pt[1]) / 2)),
                        (((unfit_source_pt[0] + unfit_target_pt[0]) / 2, (unfit_source_pt[1] + unfit_target_pt[1]) / 2), (unfit_target_pt[0], unfit_target_pt[1]))
                    ]
                return self.fit_pattern_to_frame(width, height, draggable_area, halved_patterns)
            else:
                fitted_patterns.append((new_source_pt, new_target_pt))
            #also your coordinates are in ratio form but prob should be actual coordinates
        return fitted_patterns

