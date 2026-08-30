import random

from ScriptEngine.helpers.click_path_generator import ClickPathGenerator

# The geometry DesktopDeviceManager builds for a 1512x944 host: a 2px x-increment
# and a 3px y-increment.
SCREEN_WIDTH, SCREEN_HEIGHT = 1512, 944


def build_generator():
    return ClickPathGenerator(2, 3, SCREEN_WIDTH, SCREEN_HEIGHT, 45, 0.4)


def test_zero_length_move_returns_an_empty_path():
    # generate_raw_path scales its gravity term by the source-to-target distance,
    # which is still zero after a first step that had nowhere to go.
    generator = build_generator()

    assert generator.generate_click_path(0.5, 0.5, 0.5, 0.5) == ([], [])


def test_short_moves_never_raise():
    # A click landing within a few pixels of the cursor used to fail outright:
    # every zero-length move, and roughly one in ten of one to seven pixels,
    # left generate_raw_path with nothing appended and refit_delta_path
    # averaging over an empty list.
    generator = build_generator()
    rng = random.Random(20260830)

    for _ in range(5000):
        source_x = rng.randint(1, SCREEN_WIDTH - 8)
        source_y = rng.randint(1, SCREEN_HEIGHT - 8)
        target_x = source_x + rng.randint(-7, 7)
        target_y = source_y + rng.randint(-7, 7)
        generator.generate_click_path(
            source_x / SCREEN_WIDTH, source_y / SCREEN_HEIGHT,
            target_x / SCREEN_WIDTH, target_y / SCREEN_HEIGHT
        )


def test_a_move_too_short_to_path_lands_on_the_target():
    # The fallback is one step covering the whole residual, so the caller's
    # traverse loop still finishes where it was asked to go.
    generator = build_generator()
    rng = random.Random(20260830)
    degenerate_moves = 0

    for _ in range(5000):
        source_x = rng.randint(1, SCREEN_WIDTH - 8)
        source_y = rng.randint(1, SCREEN_HEIGHT - 8)
        target_x = source_x + rng.randint(-7, 7)
        target_y = source_y + rng.randint(-7, 7)
        if (source_x, source_y) == (target_x, target_y):
            continue
        raw_path_x, _ = generator.generate_raw_path(
            source_x / SCREEN_WIDTH, source_y / SCREEN_HEIGHT,
            target_x / SCREEN_WIDTH, target_y / SCREEN_HEIGHT, 45, 0.4
        )
        if raw_path_x:
            continue
        degenerate_moves += 1
        delta_x, delta_y = generator.direct_path(
            source_x / SCREEN_WIDTH, source_y / SCREEN_HEIGHT,
            target_x / SCREEN_WIDTH, target_y / SCREEN_HEIGHT
        )
        assert (source_x + sum(delta_x), source_y + sum(delta_y)) == (target_x, target_y)

    # Guard the guard: if the walk stops producing empty paths this test would
    # pass without exercising anything.
    assert degenerate_moves > 0


def test_a_normal_move_still_takes_a_generated_path():
    generator = build_generator()

    delta_x, delta_y = generator.generate_click_path(0.1, 0.1, 0.9, 0.9)

    assert len(delta_x) > 1
    assert len(delta_x) == len(delta_y)
