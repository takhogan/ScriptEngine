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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple, TypedDict

import numpy as np

from ScriptEngine.common.constants.script_engine_constants import DETECT_OBJECT_RESULT_MARKER


class TemplateMatch(NamedTuple):
    """A single template match: (x, y) point, correlation score, and matched image region (BGR)."""
    point: tuple[float, float]
    score: float
    matched_area: np.ndarray


class _ScreenPlanImageDict(TypedDict, total=False):
    """Structural typing for legacy dict-shaped detect-object results."""

    input_type: str
    point: tuple[float, float]
    output_mask: np.ndarray
    matched_area: np.ndarray
    height: int
    width: int
    original_image: np.ndarray | None
    original_height: int
    original_width: int
    score: float
    n_matches: int


_STR_KEYS = frozenset({
    'input_type',
    'point',
    'output_mask',
    'matched_area',
    'height',
    'width',
    'original_image',
    'original_height',
    'original_width',
    'score',
    'n_matches',
    DETECT_OBJECT_RESULT_MARKER,
})


def _str_to_attr(key: str) -> str:
    if key == DETECT_OBJECT_RESULT_MARKER:
        return 'detect_object_result'
    return key


def _output_mask_key_for_index(ma: np.ndarray, output_mask: np.ndarray, key: Any) -> Any:
    if output_mask.ndim == ma.ndim:
        return key
    if output_mask.ndim == 2 and ma.ndim == 3 and isinstance(key, tuple) and len(key) > 2:
        return key[:2]
    return key


def _screenplan_index_to_new_image(spi: ScreenPlanImage, key: Any) -> ScreenPlanImage:
    """Build a new ScreenPlanImage from numpy-style indexing on ``matched_area`` (used by ``__getitem__``)."""
    ma = spi.matched_area
    om = spi.output_mask
    om_key = _output_mask_key_for_index(ma, om, key)
    try:
        new_matched = ma[key].copy()
        new_output_mask = om[om_key].copy()
    except (IndexError, TypeError, ValueError) as e:
        raise TypeError(
            f'Invalid index for ScreenPlanImage (expected numpy-style indexing on matched_area): {key!r}'
        ) from e

    h_sp, w_sp = int(ma.shape[0]), int(ma.shape[1])
    row_idx, col_idx = np.indices((h_sp, w_sp))
    offset_key = key
    if ma.ndim == 3 and isinstance(key, tuple) and len(key) > 2:
        offset_key = (key[0], key[1])
    try:
        sub_row = row_idx[offset_key]
        sub_col = col_idx[offset_key]
    except (IndexError, TypeError, ValueError) as e:
        raise TypeError(f'Unsupported index for ScreenPlanImage: {key!r}') from e
    if sub_col.size == 0 or sub_row.size == 0:
        raise IndexError('empty slice')
    x0 = int(np.min(sub_col))
    y0 = int(np.min(sub_row))
    px, py = float(spi.point[0]), float(spi.point[1])
    new_point = (px + x0, py + y0)

    new_h, new_w = new_matched.shape[0], new_matched.shape[1]
    return ScreenPlanImage(
        input_type=spi.input_type,
        point=new_point,
        output_mask=new_output_mask,
        matched_area=new_matched,
        height=new_h,
        width=new_w,
        original_image=spi.original_image,
        original_height=spi.original_height,
        original_width=spi.original_width,
        score=spi.score,
        n_matches=spi.n_matches,
        detect_object_result=spi.detect_object_result,
    )


def _transpose_output_mask_for_match(
    om: np.ndarray, ma: np.ndarray, axes: tuple[int, ...]
) -> np.ndarray:
    if om.ndim == ma.ndim:
        return np.transpose(om, axes)
    if om.ndim == 2 and ma.ndim == 3 and len(axes) == 3:
        if axes[0] == 1 and axes[1] == 0:
            return np.transpose(om, (1, 0))
        return om.copy()
    if om.ndim == 2 and ma.ndim == 2 and len(axes) == 2:
        return np.transpose(om, axes)
    return om.copy()


def _default_transpose_axes(ma: np.ndarray) -> tuple[int, ...]:
    if ma.ndim == 2:
        return (1, 0)
    if ma.ndim == 3:
        return (1, 0, 2)
    if ma.ndim <= 1:
        return tuple(range(ma.ndim))
    return tuple(range(ma.ndim - 1, -1, -1))


def _spatial_hw_swapped(axes: tuple[int, ...]) -> bool:
    return len(axes) >= 2 and axes[0] == 1 and axes[1] == 0


@dataclass
class ScreenPlanImage:
    """Detect-object result: string keys like a dict; index with ``img[:5]``, ``img[:, 10:20]``, etc. on ``matched_area``.

    ``shape``, ``size``, ``ndim``, and ``ndims`` mirror ``matched_area``. Reductions ``min``/``max``/``mean``/``sum``,
    ``clip``, ``copy``, ``transpose``/``T`` apply to ``matched_area`` (with ``transpose``/``T`` also updating
    ``output_mask``, ``point``, ``height``, and ``width`` when spatial axes swap).
    """

    input_type: str
    point: tuple[float, float]
    output_mask: np.ndarray
    matched_area: np.ndarray
    height: int
    width: int
    original_image: np.ndarray | None = None
    original_height: int = 0
    original_width: int = 0
    score: float = 0.0
    n_matches: int = 1
    detect_object_result: bool = field(default=True)

    @property
    def shape(self) -> tuple[int, ...]:
        return self.matched_area.shape

    @property
    def size(self) -> int:
        return int(self.matched_area.size)

    @property
    def ndim(self) -> int:
        return int(self.matched_area.ndim)

    @property
    def ndims(self) -> int:
        return self.ndim

    @property
    def T(self) -> ScreenPlanImage:
        """Swap spatial height and width (same as ``transpose()`` with default axes)."""
        return self.transpose()

    def copy(self) -> ScreenPlanImage:
        """Return a deep copy like ``numpy.copy`` on ``matched_area`` and ``output_mask``."""
        return ScreenPlanImage(
            input_type=self.input_type,
            point=self.point,
            output_mask=self.output_mask.copy(),
            matched_area=self.matched_area.copy(),
            height=self.height,
            width=self.width,
            original_image=None if self.original_image is None else self.original_image.copy(),
            original_height=self.original_height,
            original_width=self.original_width,
            score=self.score,
            n_matches=self.n_matches,
            detect_object_result=self.detect_object_result,
        )

    def __copy__(self) -> ScreenPlanImage:
        return self.copy()

    def __deepcopy__(self, memo: Any) -> ScreenPlanImage:
        return self.copy()

    def min(self, *args: Any, **kwargs: Any) -> Any:
        return self.matched_area.min(*args, **kwargs)

    def max(self, *args: Any, **kwargs: Any) -> Any:
        return self.matched_area.max(*args, **kwargs)

    def mean(self, *args: Any, **kwargs: Any) -> Any:
        return self.matched_area.mean(*args, **kwargs)

    def sum(self, *args: Any, **kwargs: Any) -> Any:
        return self.matched_area.sum(*args, **kwargs)

    def clip(
        self,
        a_min: Any = None,
        a_max: Any = None,
        *,
        out: Any = None,
    ) -> ScreenPlanImage:
        """``numpy.clip`` on ``matched_area``; returns a new ``ScreenPlanImage`` (``output_mask`` unchanged)."""
        if out is not None:
            raise TypeError(
                'ScreenPlanImage.clip does not support out=; use spi.matched_area.clip(..., out=out)'
            )
        clipped = np.clip(self.matched_area, a_min, a_max)
        return ScreenPlanImage(
            input_type=self.input_type,
            point=self.point,
            output_mask=self.output_mask.copy(),
            matched_area=clipped,
            height=self.height,
            width=self.width,
            original_image=self.original_image,
            original_height=self.original_height,
            original_width=self.original_width,
            score=self.score,
            n_matches=self.n_matches,
            detect_object_result=self.detect_object_result,
        )

    def transpose(self, *axes: int) -> ScreenPlanImage:
        """``numpy.transpose`` on ``matched_area`` and ``output_mask``; swaps ``point`` x/y and height/width when H/W swap."""
        ma = self.matched_area
        om = self.output_mask
        if axes:
            ax = tuple(axes)
        else:
            ax = _default_transpose_axes(ma)
        new_ma = np.transpose(ma, ax)
        new_om = _transpose_output_mask_for_match(om, ma, ax)
        if _spatial_hw_swapped(ax):
            new_point = (float(self.point[1]), float(self.point[0]))
        else:
            new_point = (float(self.point[0]), float(self.point[1]))
        nh, nw = int(new_ma.shape[0]), int(new_ma.shape[1])
        return ScreenPlanImage(
            input_type=self.input_type,
            point=new_point,
            output_mask=new_om,
            matched_area=new_ma,
            height=nh,
            width=nw,
            original_image=self.original_image,
            original_height=self.original_height,
            original_width=self.original_width,
            score=self.score,
            n_matches=self.n_matches,
            detect_object_result=self.detect_object_result,
        )

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key == DETECT_OBJECT_RESULT_MARKER:
                return self.detect_object_result
            if key in _STR_KEYS:
                return getattr(self, _str_to_attr(key))
            raise KeyError(key)
        return _screenplan_index_to_new_image(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if not isinstance(key, str):
            raise TypeError('ScreenPlanImage only supports string keys for assignment')
        if key == DETECT_OBJECT_RESULT_MARKER:
            self.detect_object_result = bool(value)
        elif key == 'matched_area':
            self.matched_area = value
        elif key == 'height':
            self.height = int(value)
        elif key == 'width':
            self.width = int(value)
        elif key == 'output_mask':
            self.output_mask = value
        elif key == 'point':
            self.point = value
        elif key == 'score':
            self.score = value
        elif key == 'n_matches':
            self.n_matches = value
        elif key == 'input_type':
            self.input_type = value
        elif key in ('original_image', 'original_height', 'original_width'):
            setattr(self, key, value)
        else:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def is_screenplan_image_result(obj: Any) -> bool:
    """True if obj is a detect-object result (dict legacy or ScreenPlanImage)."""
    if isinstance(obj, ScreenPlanImage):
        return True
    return isinstance(obj, dict) and bool(obj.get(DETECT_OBJECT_RESULT_MARKER))
