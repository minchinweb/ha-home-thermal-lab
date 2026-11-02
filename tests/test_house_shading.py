"""The house's own shading of the kitchen windows."""

from house_shading import KITCHEN_EAST, PATIO_DOOR, ROTATION, lit_fraction


def test_patio_door_in_full_sun_from_the_south_west():
    """Sun past straight out from the door: the main block is behind it."""
    assert lit_fraction(PATIO_DOOR, 200.0, 15.0) == 1.0


def test_main_block_hides_low_south_east_sun_from_the_patio_door():
    """Low sun from the south-east is behind the main block; high sun clears it."""
    assert lit_fraction(PATIO_DOOR, 130.0, 15.0) == 0.0
    assert lit_fraction(PATIO_DOOR, 130.0, 50.0) > 0.5


def test_east_window_lit_only_north_of_straight_out():
    """The north gable is just south of the east window."""
    straight_out = 90.0 + ROTATION
    assert lit_fraction(KITCHEN_EAST, straight_out - 10, 20.0) == 1.0
    assert lit_fraction(KITCHEN_EAST, straight_out + 10, 20.0) == 0.0


def test_no_sun_behind_the_wall_or_below_the_horizon():
    """A wall gets no direct sun from behind it or at night."""
    assert lit_fraction(PATIO_DOOR, 10.0, 30.0) == 0.0
    assert lit_fraction(KITCHEN_EAST, 100.0, -1.0) == 0.0
