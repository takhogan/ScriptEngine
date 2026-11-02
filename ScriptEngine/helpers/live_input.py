"""The editor's live drag: what `click_and_drag x1 y1 x2 y2 live <durationMs>`
asks for, and the short path every device type follows for it.

A script's drag (click_and_drag without `live`) takes a ClickPathGenerator
path, many small humanized steps over a random 0.5-3 s; on BlueStacks each
step is three `sendevent` calls on the device, and a drag took 6-7 s
(DESKTOP-C6GDVNF, 2026-11-02). Someone dragging in the editor wants the
device to follow their gesture instead, so a live drag is a few eased steps
over about the time the gesture took.

An older engine reads only the four coordinates and does its humanized drag,
so the editor can send `live` to any engine.
"""

LIVE_DRAG_MIN_MS = 100
LIVE_DRAG_MAX_MS = 3000
LIVE_DRAG_DEFAULT_MS = 300
# Enough to look continuous to Android's gesture detection, few enough that a
# BlueStacks drag stays a few dozen sendevents.
LIVE_DRAG_STEPS = 10


def clamp_live_duration_ms(duration_ms):
    return int(min(LIVE_DRAG_MAX_MS, max(LIVE_DRAG_MIN_MS, duration_ms)))


def parse_live_drag_args(extra_args):
    """The live drag's duration in ms from the arguments after the four
    coordinates, or None for a script drag: no `live`, an unreadable duration
    falls back to the default."""
    if not extra_args or extra_args[0] != 'live':
        return None
    if len(extra_args) < 2:
        return LIVE_DRAG_DEFAULT_MS
    try:
        return clamp_live_duration_ms(float(extra_args[1]))
    except ValueError:
        return LIVE_DRAG_DEFAULT_MS


def live_drag_points(source_x, source_y, target_x, target_y, steps=LIVE_DRAG_STEPS):
    """The points after the start, ending exactly on the target, eased in and
    out (smoothstep) so the gesture starts and ends slowly, as a finger does."""
    points = []
    for step in range(1, steps + 1):
        t = step / steps
        eased = t * t * (3 - 2 * t)
        points.append((
            int(round(source_x + (target_x - source_x) * eased)),
            int(round(source_y + (target_y - source_y) * eased))
        ))
    return points
