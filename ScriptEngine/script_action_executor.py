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

import cv2
import time
import datetime


from ScriptEngine.common.logging.script_logger import ScriptLogger,thread_local_storage
from ScriptEngine.common.script_engine_utils import state_eval
from ScriptEngine.common.enums import ScriptExecutionState
from typing import Tuple, Callable, List, Dict
script_logger = ScriptLogger()

from .helpers.detect_object_helper import DetectObjectHelper
from .helpers.click_action_helper import ClickActionHelper
from .helpers.color_compare_helper import ColorCompareHelper
from .helpers.device_action_interpreter import DeviceActionInterpreter
from .helpers.random_variable_helper import RandomVariableHelper
from .device_controller import DeviceController
from .custom_thread_pool import CustomThreadPool

class ScriptActionExecutor:
    def __init__(self, device_controller : DeviceController, io_executor : CustomThreadPool, props : Dict, screen_plan_server_attached : bool):
        self.device_controller = device_controller
        self.io_executor = io_executor
        self.props = props
        self.system_host_controller = None
        self.screen_plan_server_attached = screen_plan_server_attached
    def execute_action(self, action, state, context, run_queue, lazy_eval=False) -> Tuple[Dict, ScriptExecutionState, Dict, Dict, List, List] | Tuple[Callable, Tuple]:
        if action["actionData"]["targetSystem"] == "none":
            if self.system_host_controller is None:
                from .system_script_action_executor import SystemScriptActionExecutor
                self.system_host_controller = SystemScriptActionExecutor(self.props['script_name'], self.props, self.io_executor, self.screen_plan_server_attached)
            return self.system_host_controller.handle_action(action, state, context, run_queue)
        update_queue = []
        if action["actionName"] == "detectObject":
            if not lazy_eval:
                input_obj = DetectObjectHelper.get_detect_area(action, state)
                if input_obj['screencap_im_bgr'] is None:
                    script_logger.log('No cached screenshot or input expression, taking screenshot')
                    screencap_im_bgr = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'screenshot')()
                    script_logger.log('Storing original image')

                    input_obj['screencap_im_bgr'] = screencap_im_bgr
                    original_image = cv2.copyMakeBorder(screencap_im_bgr.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
                    original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                    input_obj["original_image"] = original_image[15:-15, 15:-15]

                    input_obj['original_height'] = screencap_im_bgr.shape[0]
                    input_obj['original_width'] = screencap_im_bgr.shape[1]
                    input_obj['fixed_scale'] = False
                action["input_obj"] = input_obj
            script_mode = self.props["scriptMode"]
            if lazy_eval:
                return DetectObjectHelper.handle_detect_object, (
                    action,
                    script_mode
                )
            else:
                handle_action_result = DetectObjectHelper.handle_detect_object(
                    action,
                    script_mode=script_mode
                )
                action, status, state, context, run_queue = DetectObjectHelper.handle_detect_action_result(
                    self.io_executor, handle_action_result, state, context, run_queue
                )


        elif action["actionName"] == "mouseInteractionAction":
            self.device_controller.ensure_device_initialized(action['actionData']['targetSystem'])
            point_choice, log_point_choice, point_list, log_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["sourceDetectTypeData"],
                action["actionData"]["sourceDetectTypeData"]["inputExpression"],
                action["actionData"]["sourcePointList"],
                state,
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'width'),
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'height'),
                1
            )
            script_logger.log('ADB CONTROLLER: starting draw click thread')
            thread_script_logger = script_logger.copy()
            self.io_executor.submit(
                self.draw_click,
                action,
                thread_script_logger,
                log_point_choice,
                log_point_list
            )

            if action["actionData"]["mouseActionType"] == "click":
                click_counts = int(action["actionData"]["clickCount"])
                if click_counts > 1 and action["actionData"]["betweenClickDelay"]:
                    delays = RandomVariableHelper.get_rv_val(
                        action["actionData"]["randomVariableTypeData"],
                        click_counts
                    )
                else:
                    delays = [0]
                click_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'click')
                for click_count in range(0, click_counts):
                    click_func(*point_choice, action["actionData"]["mouseButton"])
                    time.sleep(delays[click_count])

            elif action["actionData"]["mouseActionType"] == "mouseUp":
                if not context["mouse_down"]:
                    script_logger.log("mouseUp selected but no mouseDown to release")
                else:
                    mouse_up_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'mouse_up')
                    mouse_up_func(context["last_mouse_position"][0], context["last_mouse_position"][1])
                    context["mouse_down"] = False
            elif action["actionData"]["mouseActionType"] == "mouseDown":
                context["mouse_down"] = True
                context["last_mouse_position"] = point_choice
                mouse_down_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'mouse_down')
                mouse_down_func(*point_choice)
            elif action["actionData"]["mouseActionType"] == "scroll":
                scroll_distance = action["actionData"]["scrollDistance"]
                scroll_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'scroll')
                scroll_func(*point_choice, scroll_distance)
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "mouseMoveAction":
            self.device_controller.ensure_device_initialized(action['actionData']['targetSystem'])
            source_point, log_source_point_choice, point_list, log_source_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["sourceDetectTypeData"],
                action["actionData"]["sourceDetectTypeData"]["inputExpression"],
                action["actionData"]["sourcePointList"],
                state,
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'width'),
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'height'),
                1
            )

            target_point, log_target_point_choice, point_list, log_target_point_list = ClickActionHelper.get_point_choice(
                action["actionData"]["targetDetectTypeData"],
                action["actionData"]["targetDetectTypeData"]["inputExpression"],
                action["actionData"]["targetPointList"],
                state,
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'width'),
                self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'height'),
                2
            )

            if action["actionData"]["dragMouse"]:
                drag_log = 'Dragging from {} to {}'.format(
                    str(source_point),
                    str(target_point)
                )

                script_logger.log(drag_log)
                click_and_drag_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'click_and_drag')
                delta_x, delta_y = click_and_drag_func(
                    source_point[0],
                    source_point[1],
                    target_point[0],
                    target_point[1],
                    mouse_up=action["actionData"]["releaseMouseOnCompletion"]
                )

                thread_script_logger = script_logger.copy()
                # def catch_exc():
                #     try:
                #         self.draw_click_and_drag(
                #             action,
                #             thread_script_logger,
                #             log_source_point_choice,
                #             log_source_point_list,
                #             log_target_point_choice,
                #             log_target_point_list,
                #             delta_x,
                #             delta_y
                #         )
                #     except Exception as e:
                #         import traceback
                #         traceback.print_exc()
                #         script_logger.log(f'Error in draw_click_and_drag: {e}')
                # self.io_executor.submit(catch_exc)

                self.io_executor.submit(
                    self.draw_click_and_drag,
                    action,
                    thread_script_logger,
                    log_source_point_choice,
                    log_source_point_list,
                    log_target_point_choice,
                    log_target_point_list,
                    delta_x,
                    delta_y
                )
            else:
                if context["mouse_down"]:
                    drag_log = 'Moving from {} to {} with mouse down'.format(
                        str(source_point),
                        str(target_point)
                    )

                    script_logger.log(drag_log)
                    click_and_drag_func = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'click_and_drag')
                    delta_x, delta_y = click_and_drag_func(
                        source_point[0],
                        source_point[1],
                        target_point[0],
                        target_point[1],
                        mouse_up=action["actionData"]["releaseMouseOnCompletion"]
                    )

                    thread_script_logger = script_logger.copy()
                    self.io_executor.submit(
                        self.draw_click_and_drag,
                        action,
                        thread_script_logger,
                        log_source_point_choice,
                        log_source_point_list,
                        log_target_point_choice,
                        log_target_point_list,
                        delta_x,
                        delta_y
                    )
                else:
                    drag_log = 'Moving from {} to {} with mouse up. Note mouse movement on Android has no effect'.format(
                        str(source_point),
                        str(target_point)
                    )
                    script_logger.log(drag_log)
                    context["last_mouse_position"] = target_point
            script_logger.get_action_log().add_supporting_file(
                'text',
                'drag-log.txt',
                drag_log
            )

            status = ScriptExecutionState.SUCCESS
        
        elif action["actionName"] == "keyboardAction":
            status, state, context = DeviceActionInterpreter.parse_keyboard_action(
                self.device_controller, action, state, context
            )
        elif action["actionName"] == "colorCompareAction":
            input_obj = DetectObjectHelper.get_detect_area(
                action, state, output_type='matched_pixels'
            )
            if input_obj['screencap_im_bgr'] is None:
                script_logger.log('No cached screenshot or input expression, taking screenshot')
                screencap_im_bgr = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'screenshot')()
                input_obj['screencap_im_bgr'] = screencap_im_bgr
                original_image = cv2.copyMakeBorder(screencap_im_bgr.copy(), 15, 15, 15, 15, cv2.BORDER_REPLICATE)
                original_image = cv2.GaussianBlur(original_image, (31, 31), 0)
                input_obj["original_image"] = original_image[15:-15, 15:-15]

                input_obj['original_height'] = screencap_im_bgr.shape[0]
                input_obj['original_width'] = screencap_im_bgr.shape[1]
                input_obj['fixed_scale'] = False
            action["input_obj"] = input_obj

            color_score = ColorCompareHelper.handle_color_compare(action)
            if color_score > float(action['actionData']['threshold']):
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction successful. Color Score of {} was above threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                status = ScriptExecutionState.SUCCESS
            else:
                script_logger.get_action_log().append_supporting_file(
                    'text',
                    'compare-result.txt',
                    '\nAction failed. Color Score of {} was below threshold of {}'.format(
                        color_score,
                        float(action['actionData']['threshold'])
                    )
                )
                status = ScriptExecutionState.FAILURE
        elif action["actionName"] == "logAction":
            if action["actionData"]["logType"] == "logImage":
                log_image = self.device_controller.get_device_action(action['actionData']['targetSystem'], 'screenshot')()
                cv2.imwrite(script_logger.get_log_path_prefix() + '-logImage.png', log_image)
                status = ScriptExecutionState.SUCCESS
            else:
                exception_text = 'log type unimplemented ' + action["actionData"]["logType"]
                script_logger.log(exception_text)
                raise Exception(exception_text)
        # TODO: deprecated
        elif action["actionName"] == "timeAction":
            time_val = None
            if action["actionData"]["timezone"] == "local":
                time_val = datetime.datetime.now()
            elif action["actionData"]["timezone"] == "utc":
                time_val = datetime.datetime.utcnow()
            state[action["actionData"]["outputVarName"]] = time_val
            status = ScriptExecutionState.SUCCESS
        elif action["actionName"] == "interactApplicationAction":
            actionType = action["actionData"]["actionType"].strip()
            applicationName = action["actionData"]["applicationName"].strip()
            actionPayload = action["actionData"].get("actionPayload", "").strip()
            targetSystem = action["actionData"]["targetSystem"]

            pre_log = 'InteractApplicationAction: actionType={}, applicationName={}, actionPayload={}, targetSystem={}'.format(
                actionType, applicationName, actionPayload, targetSystem
            )
            script_logger.log(pre_log)

            try:
                if actionType == "start":
                    # Call start_application with applicationName and actionPayload
                    # For Android, combine as package/activity format if actionPayload is provided
                    start_app_func = self.device_controller.get_device_action(targetSystem, 'start_application')
                    if actionPayload:
                        # Combine applicationName and actionPayload for the application path (package/activity)
                        application_path = applicationName + "/" + actionPayload
                    else:
                        application_path = applicationName
                    start_app_func(application_path)
                    post_log = 'Successfully started application: {}'.format(application_path)
                    script_logger.log(post_log)
                    status = ScriptExecutionState.SUCCESS
                elif actionType == "stop":
                    # Call stop_application with applicationName (actionPayload not used for stop)
                    stop_app_func = self.device_controller.get_device_action(targetSystem, 'stop_application')
                    stop_app_func(applicationName)
                    post_log = 'Successfully stopped application: {}'.format(applicationName)
                    script_logger.log(post_log)
                    status = ScriptExecutionState.SUCCESS
                else:
                    exception_text = 'Unsupported actionType: {}'.format(actionType)
                    script_logger.log(exception_text)
                    raise Exception(exception_text)
            except Exception as e:
                error_log = 'Error in interactApplicationAction: {}'.format(str(e))
                script_logger.log(error_log)
                status = ScriptExecutionState.FAILURE
                post_log = error_log

            script_logger.get_action_log().add_post_file(
                'text',
                'interactApplicationAction-log.txt',
                pre_log + '\n' + post_log
            )
        # TODO: to be reintroduced in another form
        # elif action["actionName"] == "searchPatternStartAction":
            # context = self.search_pattern_helper.generate_pattern(action, context, log_folder, self.props['dir_path'])
            # script_logger.log(state)
        #     status = ScriptExecutionState.SUCCESS
        # elif action["actionName"] == "searchPatternContinueAction":
            # search_pattern_id = action["actionData"]["searchPatternID"]
            # raw_source_pt, raw_target_pt, displacement, context = self.search_pattern_helper.execute_pattern(search_pattern_id, context)
            # search_pattern_obj = context["search_patterns"][search_pattern_id]
            # step_index = search_pattern_obj["step_index"]
            # fitted_patterns = self.search_pattern_helper.fit_pattern_to_frame(self.width, self.height, search_pattern_obj["draggable_area"], [(raw_source_pt, raw_target_pt)])
            #
            # def apply_draggable_area_mask(img):
            #     return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))
            #
            # def create_and_save_screencap(self_ref, savename):
            #     img_unmasked_bgr = self.screenshot()
            #     img_masked_bgr = apply_draggable_area_mask(img_unmasked_bgr)
            #     cv2.imwrite(
            #         savename,
            #         img_masked_bgr
            #     )
            #     return img_masked_bgr
            #
            # def read_and_apply_mask(img_path):
            #     return apply_draggable_area_mask(cv2.imread(img_path))
            #
            # log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1)
            # def get_longest_path(search_string):
            #     search_result = remove_forward_slashes(glob.glob(search_string))
            #     if len(search_result) > 1:
            #         search_path_lens = list(map(len, search_result))
            #         max_search_path_len = max(search_path_lens)
            #         max_search_path = search_result[search_path_lens.index(max_search_path_len)]
            #     else:
            #         max_search_path = search_result[0]
            #     return max_search_path
            #
            # def record_movement(search_pattern_obj, x_displacement, y_displacement):
            #     curr_x,curr_y = search_pattern_obj["actual_current_point"]
            #     base_displacement_is_x = x_displacement > y_displacement
            #     slope = y_displacement / x_displacement
            #     if base_displacement_is_x:
            #         base_5_curr_x = curr_x // 5
            #         base_5_displaced_x = (curr_x + x_displacement) // 5
            #         displacement_range = range(base_5_curr_x, base_5_displaced_x, int(math.copysign(1, base_5_displaced_x - base_5_curr_x)))
            #         displacement_func = lambda displacement_leg: (slope * (displacement_leg - x_displacement) + y_displacement) // 5
            #     else:
            #         base_5_curr_y = curr_y // 5
            #         base_5_displaced_y = (curr_y + y_displacement) // 5
            #         displacement_range = range(base_5_curr_y, base_5_displaced_y,
            #                                    int(math.copysign(1, base_5_displaced_y - base_5_curr_y)))
            #         displacement_func = lambda displacement_leg: (((displacement_leg - y_displacement) / slope) + x_displacement) // 5
            #     for displacement_leg in displacement_range:
            #         displacement_leg_dependant = displacement_func(displacement_leg)
            #         locations = [
            #             (displacement_leg * 5, displacement_leg_dependant * 5),
            #             (displacement_leg * 5, displacement_leg_dependant * 5 + 1),
            #             (displacement_leg * 5, displacement_leg_dependant * 5 - 1)
            #         ] if base_displacement_is_x else [
            #             (displacement_leg_dependant * 5, displacement_leg * 5),
            #             (displacement_leg_dependant * 5 + 1, displacement_leg * 5),
            #             (displacement_leg_dependant * 5 - 1, displacement_leg * 5),
            #         ]
            #         for location in locations:
            #             if location not in search_pattern_obj["area_map"]:
            #                 search_pattern_obj["area_map"][
            #                     location
            #                 ] = {
            #                     "x": location[0],
            #                     "y": location[1],
            #                     "val": 255
            #                 }
            #             else:
            #                 search_pattern_obj["area_map"][
            #                     location
            #                 ]["val"] = max(
            #                     search_pattern_obj["area_map"][
            #                         location
            #                     ]["val"] - 60, 60)
            # def remove_forward_slashes(slash_list):
            #     return list(map(lambda slash_path: slash_path.replace('\\', '/'), list(slash_list)))
            # if search_pattern_obj["stitcher_status"] != "STITCHER_OK" and step_index > 0:
            #     prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-*complete.png'.format(step_index - 1))
            #     prev_post_img_path_split = prev_post_img_path.split('/')
            #     pre_img_name = prev_post_img_path_split[-1]
            #     pre_img_path = prev_post_img_path
            #     pre_img = read_and_apply_mask(pre_img_path)
            # else:
            #     pre_img_name = str(step_index) + \
            #         '-' + str(raw_source_pt[0]) + '-' + str(raw_source_pt[1]) + '-search-step-init.png'
            #     pre_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + pre_img_name
            #     script_logger.log('pre_path', pre_img_name, ':', raw_source_pt, ':', step_index)
            #     pre_img = create_and_save_screencap(
            #         self, pre_img_path
            #     )
            #
            # for fitted_pattern in fitted_patterns:
            #     (fitted_source_pt, fitted_target_pt) = fitted_pattern
            #     if self.width > self.height:
            #         search_unit_scale = self.height
            #     else:
            #         search_unit_scale = self.width
            #     src_x = fitted_source_pt[0] * search_unit_scale
            #     src_y = fitted_source_pt[1] * search_unit_scale
            #     tgt_x = fitted_target_pt[0] * search_unit_scale
            #     tgt_y = fitted_target_pt[1] * search_unit_scale
            #     script_logger.log('desired move: (', tgt_x - src_x,',', tgt_y - src_y, ')')
            #     self.click_and_drag(src_x, src_y, tgt_x, tgt_y)
            #     time.sleep(0.25)
            # post_img_name = str(step_index) + '-' +\
            #     str(raw_target_pt[0]) + '-' + str(raw_target_pt[1]) + '-search-step-complete.png'
            # post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + post_img_name
            # script_logger.log('post_img_path', post_img_path, ':', raw_target_pt, ':', step_index)
            # post_img = create_and_save_screencap(
            #     self, post_img_path
            # )
            # stitch_attempts = 0
            # stitch_imgs = [pre_img, post_img]
            # stitching_complete = False
            # retaken_post_img_name = None
            # retaken_post_img_path = None
            # while not stitching_complete:
            #     script_logger.log('len : stitch imgs', len(stitch_imgs), pre_img.shape, post_img.shape)
            #     err_code, result_im = search_pattern_obj["stitcher"].stitch(stitch_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
            #     draggable_area_path = search_pattern_obj["draggable_area_path"]
            #
            #     if err_code == cv2.STITCHER_OK:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_OK"
            #         search_pattern_obj["stitch"] = result_im
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/' + str(step_index) + '-pano.png', result_im)
            #         # script_logger.log(subprocess.run([self.image_stitch_calculator_path,
            #         #                       pre_img_path, post_img_path, '-m',
            #         #                       draggable_area_path, draggable_area_path],
            #         #                       capture_output=True,shell=False).stdout)
            #         break
            #     elif err_code == cv2.STITCHER_ERR_NEED_MORE_IMGS:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_ERR_NEED_MORE_IMGS"
            #         retaken_post_img_name = str(step_index) + '-' + \
            #                                 str(raw_target_pt[0]) + '-' + str(
            #             raw_target_pt[1]) + '-retaken-search-step-complete.png'
            #         retaken_post_img_path = log_folder + 'search_patterns/' + search_pattern_id + '/' + retaken_post_img_name
            #         if stitch_attempts > 1:
            #             script_logger.log('need more imgs: ', len(stitch_imgs))
            #             search_pattern_obj["step_index"] -= 1
            #             shutil.move(pre_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
            #             shutil.move(post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
            #             shutil.move(retaken_post_img_path, log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
            #             break
            #         retaken_post_img = create_and_save_screencap(
            #             self, retaken_post_img_path
            #         )
            #
            #         stop_index = max(0, step_index - 1)
            #         start_index = max(0, step_index - 4)
            #         glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
            #         script_logger.log('glob_patterns', glob_patterns)
            #         stitch_imgs = remove_forward_slashes(
            #             itertools.chain.from_iterable(
            #                 (glob.glob(
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                         glob_pattern) + '*-complete.png'
            #                 ) + glob.glob(
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                         glob_pattern
            #                     ) + '*-init.png'
            #                 )) for glob_pattern in glob_patterns
            #             )
            #         )
            #         script_logger.log('stitch_ims ', stitch_imgs)
            #         if step_index > 0:
            #             prev_post_img_path = get_longest_path(log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(stop_index) + '*-complete.png')
            #             script_logger.log('prev_post_img_path', prev_post_img_path)
            #             stitch_imgs.remove(prev_post_img_path)
            #             new_step_imgs = [pre_img, read_and_apply_mask(prev_post_img_path), retaken_post_img]
            #         else:
            #             new_step_imgs = [pre_img, retaken_post_img]
            #         stitch_imgs = new_step_imgs + (list(map(read_and_apply_mask, stitch_imgs)) if stop_index > 0 else [])
            #         # script_logger.log('post stitch_ims: ', stitch_imgs)
            #         stitch_attempts += 1
            #     else:
            #         search_pattern_obj["stitcher_status"] = "STITCHER_ERR"
            #         search_pattern_obj["step_index"] -= 1
            #         shutil.move(pre_img_path,
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + pre_img_name)
            #         shutil.move(post_img_path,
            #                     log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + post_img_name)
            #         if retaken_post_img_path is not None and retaken_post_img_name is not None:
            #             shutil.move(retaken_post_img_path,
            #                         log_folder + 'search_patterns/' + search_pattern_id + '/errors/' + retaken_post_img_name)
            #         script_logger.log('special error! ' + err_code)
            #         break
            #
            # context["search_patterns"][search_pattern_id] = search_pattern_obj
        #     status = ScriptExecutionState.SUCCESS
        # elif action["actionName"] == "searchPatternEndAction":
            # search_pattern_id = action["actionData"]["searchPatternID"]
            # if context["parent_action"] is not None and \
            #     context["parent_action"]["actionName"] == "searchPatternContinueAction" and \
            #     context["parent_action"]["actionData"]["searchPatternID"] == search_pattern_id and \
            #     not context["search_patterns"][search_pattern_id]["stitcher_status"] == "stitching_finished":
            #     # TODO haven't decided what the stiching_finished status should be yet (ie should always just return)
            #     return ScriptExecutionState.RETURN, state, context
            #
            # step_index = context["search_patterns"][search_pattern_id]["step_index"]
            # search_pattern_obj = context["search_patterns"][search_pattern_id]
            # def apply_draggable_area_mask(img):
            #     return cv2.bitwise_and(img, cv2.cvtColor(search_pattern_obj["draggable_area"], cv2.COLOR_GRAY2BGR))
            # def read_and_apply_mask(img_path):
            #     return apply_draggable_area_mask(cv2.imread(img_path))
            # def generate_greater_pano(start_index, stop_index):
            #     glob_patterns = get_glob_digit_regex_string(start_index, stop_index)
            #     greater_pano_paths = remove_forward_slashes(
            #         itertools.chain.from_iterable(
            #             glob.glob(
            #                 log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                     glob_pattern
            #                 ) + '*-complete.png'
            #             ) + glob.glob(
            #                 log_folder + 'search_patterns/' + search_pattern_id + '/{}-'.format(
            #                     glob_pattern
            #                 ) + '*-init.png'
            #             ) for glob_pattern in glob_patterns
            #         )
            #     )
            #     greater_pano_imgs = list(map(read_and_apply_mask, greater_pano_paths))
            #     err_code, result_im = search_pattern_obj["stitcher"].stitch(greater_pano_imgs, [search_pattern_obj["draggable_area"]] * len(stitch_imgs))
            #     if err_code == cv2.STITCHER_OK:
            #         script_logger.log('generating full panorama...')
            #         cv2.imwrite(log_folder + 'search_patterns/' + search_pattern_id + '/full-pano.png', result_im)
            #         # script_logger.log(subprocess.run([self.image_stitch_calculator_path] + \
            #         #                      greater_pano_paths + ['-m'] + \
            #         #                      [draggable_area_path] * len(greater_pano_paths),
            #         #                      capture_output=True, shell=False).stdout)
            #         pass
            #     else:
            #         script_logger.log('failed to greater pano: ', err_code)
            # generate_greater_pano(0, step_index)
            #
            # del context["search_patterns"][action["actionData"]["searchPatternID"]]
            # status = ScriptExecutionState.SUCCESS
        else:
            exception_text = "action unimplemented" + action["actionName"]
            script_logger.log(exception_text)
            raise Exception(exception_text)
        return action, status, state, context, run_queue, update_queue
    
    def draw_click(self, action,thread_script_logger, point_choice, point_list):
        thread_local_storage.script_logger = thread_script_logger
        thread_script_logger.log('started draw click thread')
        ClickActionHelper.draw_click(
            self.device_controller.get_device_action(action['actionData']['targetSystem'], 'screenshot')(), point_choice, point_list
        )
    
    def draw_click_and_drag(self, action,
                            thread_script_logger,
                            source_point, source_point_list,
                            target_point, target_point_list,
                            delta_x, delta_y):
        thread_local_storage.script_logger = thread_script_logger
        thread_script_logger.log('started draw click thread')
        xmax = self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'xmax')
        ymax = self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'ymax')
        width = self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'width')
        height = self.device_controller.get_device_attribute(action['actionData']['targetSystem'], 'height')

        delta_x = list(map(lambda x: (x / xmax) * width, delta_x))
        delta_y = list(map(lambda y: (y / ymax) * height, delta_y))

        ClickActionHelper.draw_click_and_drag(
            self.device_controller.get_device_action(action['actionData']['targetSystem'], 'screenshot')(),
            source_point, source_point_list,
            target_point, target_point_list,
            zip(delta_x, delta_y)
        )
