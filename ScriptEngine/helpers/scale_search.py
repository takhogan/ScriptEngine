"""Matching a template at other sizes (docs/multiscale-template-matching.md).

A scale (sx, sy) resizes the template, so its matches are in the searched
image's own pixels. `search` tries the likely scales and a uniform grid at
half resolution, matches the best few at full size, then refines x and y
around the best one.
"""
import math
from typing import NamedTuple, Optional

import cv2
import numpy as np

MIN_TEMPLATE_SIDE = 8        # px: a smaller scaled template is not tried
COARSE_MIN_SIDE = 12         # px at half resolution: smaller ones are scored at full size
DUPLICATE_TOLERANCE = 0.01   # a scale this close to one already tried is skipped
SCALE_RANGE = (0.5, 2.0)
GRID_STEP = 1.06
COARSE_KEEP = 3              # best coarse scales matched at full size
REFINE_STEPS = (0.02, 0.01)
REFINE_FROM = 0.15           # refine only when the best is within this of the threshold
AMBIGUOUS_SPAN = 1.3
SNAP_TOLERANCE = 0.025      # a found scale this close to a likely one is learned as the likely one
# Ratios between the usual display scalings (100, 125, 150, 175, 200 %).
DISPLAY_SCALING_RATIOS = (1.25, 0.8, 1.5, 2 / 3, 2.0, 0.5, 1.2, 5 / 6, 4 / 3, 0.75, 1.75, 4 / 7)


def scaled_size(width, height, scale):
    return max(1, int(round(width * scale[0]))), max(1, int(round(height * scale[1])))


def scale_template(image, scale, interpolation=None):
    """`image` resized by scale: area for shrinking, linear for growing, or `interpolation`."""
    h, w = image.shape[:2]
    size = scaled_size(w, h, scale)
    if size == (w, h):
        return image
    if interpolation is None:
        interpolation = cv2.INTER_AREA if scale[0] * scale[1] < 1 else cv2.INTER_LINEAR
    return cv2.resize(image, size, interpolation=interpolation)


def scale_mask_location(mask_location, scale):
    """maskLocation [[left, top], [right, bottom]] (inclusive) at the scaled template's size."""
    if mask_location is None:
        return None
    (left, top), (right, bottom) = mask_location
    return [
        [int(math.floor(float(left) * scale[0])), int(math.floor(float(top) * scale[1]))],
        [int(math.ceil((float(right) + 1) * scale[0])) - 1, int(math.ceil((float(bottom) + 1) * scale[1])) - 1],
    ]


def best_score(match_result):
    if match_result is None or match_result.size == 0:
        return -1.0
    finite = match_result[np.isfinite(match_result)]
    return float(finite.max()) if finite.size else -1.0


def _close(a, b):
    return abs(a[0] / b[0] - 1) <= DUPLICATE_TOLERANCE and abs(a[1] / b[1] - 1) <= DUPLICATE_TOLERANCE


def likely_scales(rx, ry):
    """The stretch to the capture, the uniform resolution ratios, and the
    display scaling ratios from the stored size and from the uniform
    resolution ratio, most likely first."""
    g = math.sqrt(rx * ry)
    scales = [(rx, ry), (g, g), (rx, rx), (ry, ry)]
    for base in (1.0, g):
        scales.extend((base * k, base * k) for k in DISPLAY_SCALING_RATIOS)
    return scales


def grid_scales():
    scales = []
    s = SCALE_RANGE[0]
    while s <= SCALE_RANGE[1] + 1e-9:
        scales.append((s, s))
        s *= GRID_STEP
    return scales


class Tried(NamedTuple):
    scale: tuple
    score: float
    match_result: Optional[np.ndarray]   # None for a coarse (half resolution) score


class SearchResult(NamedTuple):
    scale: Optional[tuple]
    score: float
    match_result: Optional[np.ndarray]
    tried: list
    ambiguous: bool
    # The scale to learn: a likely scale that gives the same template size
    # within a pixel, else `scale`. A small template's best size is noisy
    # (whole pixels), so the device's real ratio is a better thing to learn.
    learn_scale: Optional[tuple] = None


class ScaleMatcher:
    """One template against one image, at any scale. Scaled templates and
    full-size results are cached, so a scale is matched once."""

    def __init__(self, image, template, mask, use_color):
        self.image = image if use_color else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.template = template if use_color else cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        self.mask = mask
        self.full = {}
        self.coarse = {}
        self._half_image = None

    def fits(self, scale, factor=1.0):
        th, tw = self.template.shape[:2]
        h, w = self.image.shape[:2]
        sw, sh = scaled_size(tw, th, scale)
        return (min(sw, sh) * factor >= (COARSE_MIN_SIDE if factor < 1 else MIN_TEMPLATE_SIDE)
                and sw <= w and sh <= h)

    def _match(self, image, scale, factor):
        """TM_CCOEFF_NORMED of the template at `scale` x `factor` on `image`,
        in `image`'s positions. A template enlarged in both directions is
        matched by shrinking the image instead (the template's own pixels
        are sharper than enlarged ones: real captures scored 0.92 against
        0.84), and the result is mapped back to the image's positions."""
        ex, ey = scale[0] * factor, scale[1] * factor
        h, w = image.shape[:2]
        th, tw = self.template.shape[:2]
        sw, sh = scaled_size(tw, th, (ex, ey))
        if sw > w or sh > h:
            return None
        if ex > 1 and ey > 1:
            return self._match_resized_image(image, (ex, ey))
        template = scale_template(self.template, (ex, ey))
        mask = None
        if self.mask is not None:
            mask = scale_template(self.mask, (ex, ey), cv2.INTER_NEAREST)
            if mask.shape[:2] != template.shape[:2]:
                mask = cv2.resize(mask, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_NEAREST)
        try:
            return cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED, result=None, mask=mask)
        except cv2.error:
            return None

    def _match_resized_image(self, image, scale):
        """The template as cut, on `image` resized by 1 / scale, with the
        scores mapped back to `image`'s positions (each takes its nearest)."""
        h, w = image.shape[:2]
        th, tw = self.template.shape[:2]
        sw, sh = scaled_size(tw, th, scale)
        if sw > w or sh > h:
            return None
        resized = cv2.resize(image, (max(tw, int(round(w / scale[0]))), max(th, int(round(h / scale[1])))),
                             interpolation=cv2.INTER_AREA)
        try:
            result = cv2.matchTemplate(resized, self.template, cv2.TM_CCOEFF_NORMED, result=None, mask=self.mask)
        except cv2.error:
            return None
        return cv2.resize(result, (w - sw + 1, h - sh + 1), interpolation=cv2.INTER_NEAREST)

    def match_at_template_size(self, scale):
        """`scale` matched the other way round: the image resized to the
        template's screen (for a scale below 1, enlarged, as the old stretched
        retry did). Thin text and small icons can score higher at the
        template's own resolution than with the template shrunk."""
        key = ('image', round(scale[0], 5), round(scale[1], 5))
        if key not in self.full:
            self.full[key] = self._match_resized_image(self.image, scale) if self.fits(scale) else None
        return self.full[key]

    def match(self, scale):
        """The full-size match result at `scale` (None when it does not fit)."""
        key = (round(scale[0], 5), round(scale[1], 5))
        if key not in self.full:
            self.full[key] = self._match(self.image, scale, 1.0) if self.fits(scale) else None
        return self.full[key]

    def pixel_neighbors(self, scale):
        """The scales giving the other whole-pixel sizes next to `scale`'s: the
        best size of a template is the floor or the ceiling of width x sx (and
        height x sy), depending on where the element falls on the pixel grid."""
        th, tw = self.template.shape[:2]
        base = scaled_size(tw, th, scale)
        xs = sorted({max(1, math.floor(tw * scale[0])), max(1, math.ceil(tw * scale[0]))})
        ys = sorted({max(1, math.floor(th * scale[1])), max(1, math.ceil(th * scale[1]))})
        return [(x / tw, y / th) for x in xs for y in ys if (x, y) != base]

    def best_near(self, scale, threshold):
        """`scale` matched, and when it falls short of the threshold by less
        than REFINE_FROM, its whole-pixel neighbours too: the best Tried, and
        every Tried made."""
        made = []
        result = self.match(scale)
        best = Tried(tuple(scale), best_score(result), result)
        made.append(best)
        if threshold - REFINE_FROM <= best.score < threshold:
            for neighbor in self.pixel_neighbors(scale):
                result = self.match(neighbor)
                entry = Tried(neighbor, best_score(result), result)
                made.append(entry)
                if entry.score > best.score:
                    best = entry
            if best.score < threshold and scale[0] <= 1 and scale[1] <= 1 and tuple(scale) != (1.0, 1.0):
                result = self.match_at_template_size(scale)
                entry = Tried(tuple(scale), best_score(result), result)
                made.append(entry)
                if entry.score > best.score:
                    best = entry
        return best, made

    def same_size(self, a, b):
        """True when scales a and b size the template within a pixel (or
        SNAP_TOLERANCE of its size, for a large one) of each other."""
        th, tw = self.template.shape[:2]
        wa, ha = tw * a[0], th * a[1]
        wb, hb = tw * b[0], th * b[1]
        return (abs(wa - wb) <= max(1.0, SNAP_TOLERANCE * wb)
                and abs(ha - hb) <= max(1.0, SNAP_TOLERANCE * hb))

    def coarse_score(self, scale):
        key = (round(scale[0], 5), round(scale[1], 5))
        if key not in self.coarse:
            if self._half_image is None:
                h, w = self.image.shape[:2]
                self._half_image = cv2.resize(self.image, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
            self.coarse[key] = best_score(self._match(self._half_image, scale, 0.5))
        return self.coarse[key]


def search(matcher, rx, ry, threshold, seeds=(), grid=True):
    """The best scale for the template on the image.

    `seeds` are Tried entries already matched (the stored size, the learned
    scales), so they are not matched again and compete with the rest.
    Without `grid`, only the likely scales (an exploration).
    """
    tried = list(seeds)

    def seen(scale, full_only=False):
        return any(_close(scale, t.scale) for t in tried if not full_only or t.match_result is not None)

    def full(scale):
        if seen(scale, full_only=True) or not matcher.fits(scale):
            return None
        result = matcher.match(scale)
        entry = Tried(scale, best_score(result), result)
        tried.append(entry)
        return entry

    def best_full():
        full_entries = [t for t in tried if t.match_result is not None]
        return max(full_entries, key=lambda t: t.score) if full_entries else None

    def in_range(scale):
        lo, hi = SCALE_RANGE[0] * 0.9, SCALE_RANGE[1] * 1.1
        return lo <= scale[0] <= hi and lo <= scale[1] <= hi

    def coarse_pass(scales):
        """Scores at half resolution; returns the scales to match at full size."""
        ranked = []
        small = []
        for scale in scales:
            if not in_range(scale) or seen(scale) or any(_close(scale, s) for s, _ in ranked) or scale in small:
                continue
            if not matcher.fits(scale):
                continue
            if matcher.fits(scale, 0.5):
                score = matcher.coarse_score(scale)
                ranked.append((scale, score))
                tried.append(Tried(scale, score, None))
            else:
                small.append(scale)
        ranked.sort(key=lambda r: -r[1])
        return [s for s, _ in ranked[:COARSE_KEEP]] + small

    def refine():
        best = best_full()
        if best is None or best.score < threshold - REFINE_FROM:
            return
        for step in REFINE_STEPS + ('pixel',):
            if step == 'pixel':
                # The whole-pixel sizes around the best (only those not tried).
                for candidate in matcher.pixel_neighbors(best.scale):
                    entry = full(candidate)
                    if entry is not None and entry.score > best.score:
                        best = entry
                break
            improved = True
            while improved:
                improved = False
                for dx, dy in ((1 + step, 1), (1 - step, 1), (1, 1 + step), (1, 1 - step)):
                    candidate = (best.scale[0] * dx, best.scale[1] * dy)
                    entry = full(candidate)
                    if entry is not None and entry.score > best.score:
                        best = entry
                        improved = True
                        break

    for scale in coarse_pass(likely_scales(rx, ry)):
        full(scale)
    refine()
    best = best_full()
    if grid and (best is None or best.score < threshold):
        for scale in coarse_pass(grid_scales()):
            full(scale)
        refine()
        best = best_full()

    if best is None:
        return SearchResult(None, -1.0, None, tried, False)
    passing = [math.sqrt(t.scale[0] * t.scale[1]) for t in tried if t.match_result is not None and t.score >= threshold]
    ambiguous = len(passing) > 1 and max(passing) / min(passing) > AMBIGUOUS_SPAN
    learn_scale = best.scale
    for candidate in [(1.0, 1.0)] + likely_scales(rx, ry):
        if matcher.same_size(candidate, best.scale):
            learn_scale = (round(candidate[0], 4), round(candidate[1], 4))
            break
    return SearchResult(best.scale, best.score, best.match_result, tried, ambiguous, learn_scale)
