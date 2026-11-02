"""Room geometry derived from the balancing check."""

import math

import pytest
from room_geometry import FT, ROOM_GEOMETRY


def test_volumes_match_the_balancing_check():
    """Volumes agree with the spreadsheet's own figures (cubic feet)."""
    for name, cubic_feet in (
        ("Z1 kitchen", 2987.875),
        ("Z3 master", 1430.0),
        ("NE basement", 480.3125),
    ):
        assert ROOM_GEOMETRY[name].volume_m3 / FT**3 == pytest.approx(cubic_feet)


def test_roof_area_follows_the_pitch():
    """A 45 degree ceiling has sqrt(2) times the floor area; a floor above has none."""
    master = ROOM_GEOMETRY["Z3 master"]
    assert master.roof_m2 == pytest.approx(master.floor_m2 * math.sqrt(2))
    assert ROOM_GEOMETRY["W bedroom"].roof_m2 == 0.0


def test_glass_and_supply_heat():
    """Glass sums per face, a room with no window has none, and airflow gives W/K."""
    kitchen = ROOM_GEOMETRY["Z1 kitchen"]
    west = (74 * 80 + 45 * 32) * 0.0254**2
    assert kitchen.glass_m2("W") == pytest.approx(west)
    assert ROOM_GEOMETRY["Laundry"].glass_m2() == 0.0
    assert kitchen.supply_w_per_k("z4") == pytest.approx(330 * 0.000471947 * 1206)
