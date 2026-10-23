import pytest

from citrusina import wheel

MID = (wheel.R_IN + wheel.R_OUT) / 2


def test_hub_and_far_outside():
    assert wheel.hit(0, 0, 4) == wheel.HUB
    assert wheel.hit(0, -(wheel.R_HUB + 2), 4) == wheel.HUB
    assert wheel.hit(0, -(wheel.R_OUT + wheel.REACH + 1), 4) is None
    assert wheel.hit(0, -MID, 0) is None


def test_first_petal_is_on_top_and_they_run_clockwise():
    assert wheel.hit(0, -MID, 4) == 0
    assert wheel.hit(MID, 0, 4) == 1
    assert wheel.hit(0, MID, 4) == 2
    assert wheel.hit(-MID, 0, 4) == 3


def test_just_past_the_rim_still_counts():
    assert wheel.hit(wheel.R_OUT + 10, 0, 4) == 1


def test_a_single_petal_takes_the_whole_ring():
    assert wheel.hit(-MID, 0, 1) == 0
    assert wheel.hit(0, MID, 1) == 0


def test_point_and_angle_agree():
    for angle in (0, 45, 90, 200, 359):
        x, y = wheel.point(angle, 100)
        assert wheel.angle_of(x, y) == pytest.approx(angle)


def test_gaps_keep_the_same_width_at_every_radius():
    # same gap in px means a smaller angle further out
    assert wheel.half_gap(wheel.R_OUT) < wheel.half_gap(wheel.R_IN)


def test_place_keeps_the_wheel_on_screen():
    m = wheel.R_OUT + 20
    assert wheel.place(5, 5, 0, 0, 1920, 1080) == (m, m)
    assert wheel.place(1919, 1079, 0, 0, 1920, 1080) == (1920 - m, 1080 - m)
    assert wheel.place(800, 500, 0, 0, 1920, 1080) == (800, 500)


def test_long_labels_get_smaller():
    assert wheel.label_size("PNG", 6) == 14
    assert wheel.label_size("WITH BACKGROUND", 10) < 14
    assert wheel.label_size("X" * 80, 10) == 10
