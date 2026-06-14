import numpy as np
import cv2

from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.types import ScreenPlanImage, is_screenplan_image_result
from ScriptEngine.common.script_engine_utils import state_eval
from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()


def _match_merge_bbox(obj):
    """Absolute ``(x0, y0, x1, y1)`` bounding box of a detectObject result."""
    x0 = float(obj["point"][0])
    y0 = float(obj["point"][1])
    x1 = x0 + float(obj["width"])
    y1 = y0 + float(obj["height"])
    return x0, y0, x1, y1


def _match_merge_join_point(bbox, anchor, toward):
    """Return the ``(x, y)`` join point on ``bbox`` for the named anchor.

    ``angle`` returns the point where the ray from the box center toward
    ``toward`` (the other match's center) exits the box; every other anchor is a
    fixed position on the box.
    """
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    fixed_anchors = {
        'center': (cx, cy),
        'topLeft': (x0, y0),
        'top': (cx, y0),
        'topRight': (x1, y0),
        'right': (x1, cy),
        'bottomRight': (x1, y1),
        'bottom': (cx, y1),
        'bottomLeft': (x0, y1),
        'left': (x0, cy),
    }
    if anchor in fixed_anchors:
        return fixed_anchors[anchor]
    if anchor == 'angle':
        dx = float(toward[0]) - cx
        dy = float(toward[1]) - cy
        if dx == 0.0 and dy == 0.0:
            return (cx, cy)
        half_w = (x1 - x0) / 2.0
        half_h = (y1 - y0) / 2.0
        scales = []
        if dx != 0.0 and half_w > 0.0:
            scales.append(half_w / abs(dx))
        if dy != 0.0 and half_h > 0.0:
            scales.append(half_h / abs(dy))
        t = min(scales) if scales else 0.0
        return (cx + dx * t, cy + dy * t)
    raise ValueError('matchMergeAction: invalid join anchor "{}"'.format(anchor))


def _match_merge_segment_polygon(point_left, point_right, left_bbox, right_bbox):
    """Quadrilateral for a ``segment`` join.

    A band running along ``point_left`` -> ``point_right`` whose width is the
    perpendicular overlap of the two match boxes (as wide as possible while still
    intersecting both). Returns ``[point_left]`` when the join points coincide.
    """
    dx = point_right[0] - point_left[0]
    dy = point_right[1] - point_left[1]
    length = float(np.hypot(dx, dy))
    if length == 0.0:
        return [point_left]
    # Unit vector perpendicular to the segment direction.
    nx, ny = -dy / length, dx / length

    def _proj_range(bbox):
        x0, y0, x1, y1 = bbox
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        projections = [px * nx + py * ny for px, py in corners]
        return min(projections), max(projections)

    left_min, left_max = _proj_range(left_bbox)
    right_min, right_max = _proj_range(right_bbox)
    t_lo = max(left_min, right_min)
    t_hi = min(left_max, right_max)
    # point_left and point_right share this projection since n is perpendicular to the segment.
    tp = point_left[0] * nx + point_left[1] * ny
    if t_hi < t_lo:
        # No perpendicular overlap: collapse the band onto the bare segment line.
        t_lo = t_hi = tp
    return [
        (point_left[0] + (t_lo - tp) * nx, point_left[1] + (t_lo - tp) * ny),
        (point_left[0] + (t_hi - tp) * nx, point_left[1] + (t_hi - tp) * ny),
        (point_right[0] + (t_hi - tp) * nx, point_right[1] + (t_hi - tp) * ny),
        (point_right[0] + (t_lo - tp) * nx, point_right[1] + (t_lo - tp) * ny),
    ]


class MatchMergeHelper:
    def __init__(self):
        pass

    def handle_action(self, action, state):
        # // leftInputExpression: string,
        # // rightInputExpression: string,
        # // joinLeftAt: 'angle' | 'center' | 'topLeft' | 'top' | 'topRight' | 'right' | 'bottomRight' | 'bottom' | 'bottomLeft' | 'left',
        # // joinRightAt: 'angle' | 'center' | 'topLeft' | 'top' | 'topRight' | 'right' | 'bottomRight' | 'bottom' | 'bottomLeft' | 'left',
        # // includeLeftMatch: boolean,
        # // includeRightMatch: boolean,
        # // joinTogetherAs: 'rectangle' | 'segment'
        # // outputVarName: string
        action_data = action["actionData"]
        pre_log = 'matchMergeAction parameters: joinLeftAt={}, joinRightAt={}, includeLeftMatch={}, includeRightMatch={}, joinTogetherAs={}'.format(
            action_data.get("joinLeftAt"),
            action_data.get("joinRightAt"),
            action_data.get("includeLeftMatch"),
            action_data.get("includeRightMatch"),
            action_data.get("joinTogetherAs", "rectangle"),
        )
        script_logger.log(pre_log, level='debug')
        script_logger.get_action_log().add_pre_file('text', 'matchMergeAction-params.txt', pre_log)
        left_obj = state_eval(action_data["leftInputExpression"], {}, state)
        right_obj = state_eval(action_data["rightInputExpression"], {}, state)
        for label, obj, expr in (
            ('left', left_obj, action_data["leftInputExpression"]),
            ('right', right_obj, action_data["rightInputExpression"]),
        ):
            if not is_screenplan_image_result(obj):
                script_logger.log(
                    'matchMergeAction {} input "{}" is not a detectObject result'.format(label, expr),
                    level='error'
                )
                raise ValueError(
                    'matchMergeAction {}InputExpression "{}" must evaluate to a detectObject result'.format(
                        label, expr
                    )
                )

        include_left = action_data.get("includeLeftMatch") in (True, "true", "True", 1)
        include_right = action_data.get("includeRightMatch") in (True, "true", "True", 1)
        join_together_as = action_data.get("joinTogetherAs", "rectangle")
        output_var_name = action_data["outputVarName"]

        left_bbox = _match_merge_bbox(left_obj)
        right_bbox = _match_merge_bbox(right_obj)
        left_center = ((left_bbox[0] + left_bbox[2]) / 2.0, (left_bbox[1] + left_bbox[3]) / 2.0)
        right_center = ((right_bbox[0] + right_bbox[2]) / 2.0, (right_bbox[1] + right_bbox[3]) / 2.0)
        point_left = _match_merge_join_point(left_bbox, action_data["joinLeftAt"], toward=right_center)
        point_right = _match_merge_join_point(right_bbox, action_data["joinRightAt"], toward=left_center)

        if join_together_as == "rectangle":
            jx0 = min(point_left[0], point_right[0])
            jx1 = max(point_left[0], point_right[0])
            jy0 = min(point_left[1], point_right[1])
            jy1 = max(point_left[1], point_right[1])
            join_poly = [(jx0, jy0), (jx1, jy0), (jx1, jy1), (jx0, jy1)]
        elif join_together_as == "segment":
            join_poly = _match_merge_segment_polygon(point_left, point_right, left_bbox, right_bbox)
        else:
            raise ValueError('matchMergeAction: invalid joinTogetherAs "{}"'.format(join_together_as))

        # Union bounding box (absolute) of the join geometry plus any included matches.
        all_points = list(join_poly)
        if include_left:
            lx0, ly0, lx1, ly1 = left_bbox
            all_points += [(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1)]
        if include_right:
            rx0, ry0, rx1, ry1 = right_bbox
            all_points += [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]

        original_image = left_obj.get("original_image")
        if original_image is None:
            original_image = right_obj.get("original_image")
        original_image_blurred = left_obj.get("original_image_blurred")
        if original_image_blurred is None:
            original_image_blurred = right_obj.get("original_image_blurred")
        original_height = int(left_obj.get("original_height", 0) or right_obj.get("original_height", 0) or 0)
        original_width = int(left_obj.get("original_width", 0) or right_obj.get("original_width", 0) or 0)

        bx0 = int(np.floor(min(xs)))
        by0 = int(np.floor(min(ys)))
        bx1 = int(np.ceil(max(xs)))
        by1 = int(np.ceil(max(ys)))
        if original_width > 0:
            bx0 = max(0, bx0)
            bx1 = min(original_width, bx1)
        else:
            bx0 = max(0, bx0)
        if original_height > 0:
            by0 = max(0, by0)
            by1 = min(original_height, by1)
        else:
            by0 = max(0, by0)
        out_w = max(1, bx1 - bx0)
        out_h = max(1, by1 - by0)

        combined_mask = np.zeros((out_h, out_w), dtype=np.uint8)

        def _to_local(px, py):
            return (int(round(px - bx0)), int(round(py - by0)))

        if len(join_poly) >= 3:
            poly_local = np.array([[_to_local(px, py) for px, py in join_poly]], dtype=np.int32)
            cv2.fillPoly(combined_mask, poly_local, 255)
        # Always connect the two join points so the merged mask stays a single piece.
        cv2.line(combined_mask, _to_local(*point_left), _to_local(*point_right), 255, 1)

        def _paste_mask(obj):
            obj_mask = obj.get("output_mask")
            if obj_mask is None:
                return
            if obj_mask.ndim == 3:
                obj_mask = cv2.cvtColor(obj_mask, cv2.COLOR_BGR2GRAY)
            mask_h, mask_w = obj_mask.shape[:2]
            px = int(round(float(obj["point"][0]) - bx0))
            py = int(round(float(obj["point"][1]) - by0))
            dst_x0 = max(0, px)
            dst_y0 = max(0, py)
            dst_x1 = min(out_w, px + mask_w)
            dst_y1 = min(out_h, py + mask_h)
            if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
                return
            src_x0 = dst_x0 - px
            src_y0 = dst_y0 - py
            region = obj_mask[src_y0:src_y0 + (dst_y1 - dst_y0), src_x0:src_x0 + (dst_x1 - dst_x0)]
            region_bin = np.where(region > 0, 255, 0).astype(np.uint8)
            combined_mask[dst_y0:dst_y1, dst_x0:dst_x1] = np.maximum(
                combined_mask[dst_y0:dst_y1, dst_x0:dst_x1], region_bin
            )

        if include_left:
            _paste_mask(left_obj)
        if include_right:
            _paste_mask(right_obj)

        if original_image is not None:
            crop = original_image[by0:by1, bx0:bx1].copy()
            if crop.shape[0] != out_h or crop.shape[1] != out_w:
                crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
            if crop.ndim == 3:
                mask_for_crop = cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR)
            else:
                mask_for_crop = combined_mask
            matched_area = cv2.bitwise_and(crop, mask_for_crop)
        else:
            # No source frame retained: rebuild the matched area from the included crops.
            matched_area = np.zeros((out_h, out_w, 3), dtype=np.uint8)

            def _paste_matched(obj):
                obj_match = obj.get("matched_area")
                if obj_match is None:
                    return
                if obj_match.ndim == 2:
                    obj_match = cv2.cvtColor(obj_match, cv2.COLOR_GRAY2BGR)
                match_h, match_w = obj_match.shape[:2]
                px = int(round(float(obj["point"][0]) - bx0))
                py = int(round(float(obj["point"][1]) - by0))
                dst_x0 = max(0, px)
                dst_y0 = max(0, py)
                dst_x1 = min(out_w, px + match_w)
                dst_y1 = min(out_h, py + match_h)
                if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
                    return
                src_x0 = dst_x0 - px
                src_y0 = dst_y0 - py
                region = obj_match[src_y0:src_y0 + (dst_y1 - dst_y0), src_x0:src_x0 + (dst_x1 - dst_x0)]
                matched_area[dst_y0:dst_y1, dst_x0:dst_x1] = np.maximum(
                    matched_area[dst_y0:dst_y1, dst_x0:dst_x1], region
                )

            if include_left:
                _paste_matched(left_obj)
            if include_right:
                _paste_matched(right_obj)

        output_obj = ScreenPlanImage(
            input_type='shape',
            point=(float(bx0), float(by0)),
            output_mask=combined_mask,
            matched_area=matched_area,
            height=out_h,
            width=out_w,
            original_image=original_image,
            original_image_blurred=original_image_blurred,
            original_height=original_height,
            original_width=original_width,
            score=min(float(left_obj.get("score", 0.0) or 0.0), float(right_obj.get("score", 0.0) or 0.0)),
            n_matches=1,
            detect_object_result=True,
        )
        state[output_var_name] = output_obj

        # post image feeds the log video (info+); skipped at error.
        if script_logger.should_log('info'):
            out_image_relative_path = 'matchMergeAction-output.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + out_image_relative_path, matched_area)
            script_logger.get_action_log().set_post_file('image', out_image_relative_path)
        script_logger.get_action_log().set_summary(
            'merged {} and {} as {} into {}'.format(
                action_data["leftInputExpression"],
                action_data["rightInputExpression"],
                join_together_as,
                output_var_name,
            )
        )
        status = ScriptExecutionState.SUCCESS
        return status, state
