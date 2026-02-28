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

from typing import NamedTuple, TypedDict

import numpy as np


class TemplateMatch(NamedTuple):
    """A single template match: (x, y) point, correlation score, and matched image region (BGR)."""
    point: tuple[float, float]
    score: float
    matched_area: np.ndarray


class ScreenPlanImage(TypedDict):
    """Structured result for one detected image from template_match (detect-object output)."""
    input_type: str
    point: tuple[float, float]
    shape: np.ndarray
    matched_area: np.ndarray
    height: int
    width: int
    original_image: np.ndarray
    original_height: int
    original_width: int
    score: float
    n_matches: int
    X_Screenplan_DetectObject_Result: bool  # DETECT_OBJECT_RESULT_MARKER
