"""Tests for building the Manual J project from House Structure's rooms."""

import pytest

from custom_components.home_thermal_lab.house_model import (
    Nominal,
    build_project,
    room_capacities,
)
from custom_components.home_thermal_lab.manual import Design, calculate

ROOMS = {
    "office": {
        "title": "Office",
        "floor_m2": 12.0,
        "height_m": 2.4,
        "volume_m3": 28.8,
        "below_ground": False,
        "walls": [
            {"azimuth": 180.0, "tilt": 90.0, "area_m2": 10.0, "glass_m2": 2.0},
            {"azimuth": 90.0, "tilt": 90.0, "area_m2": 8.0, "glass_m2": 0.0},
        ],
        "roofs": [{"azimuth": 0.0, "tilt": 30.0, "area_m2": 12.0, "glass_m2": 0.0}],
        "windows": [
            {
                "azimuth": 180.0,
                "tilt": 90.0,
                "in": "wall",
                "glass_m2": 2.0,
                "transmittance": 0.7,
            },
        ],
    },
    "basement": {
        "title": "Basement",
        "floor_m2": 40.0,
        "height_m": 2.3,
        "volume_m3": None,
        "below_ground": True,
        "walls": [{"azimuth": 0.0, "tilt": 90.0, "area_m2": 20.0, "glass_m2": 0.0}],
        "roofs": [],
        "windows": [],
    },
    "empty": {"title": "Empty", "walls": [], "roofs": [], "windows": []},
}


def test_volume_falls_back_to_floor_times_height_and_skips_unknown():
    project, warnings = build_project(ROOMS, Nominal(), Design())
    basement = next(r for r in project.rooms if r.name == "Basement")
    assert basement.volume == pytest.approx(40.0 * 2.3)
    assert any("Empty" in w for w in warnings)


def test_walls_take_net_area_and_windows_their_glazing():
    project, _ = build_project(ROOMS, Nominal(), Design())
    office = next(r for r in project.rooms if r.name == "Office")
    walls = [s for s in office.surfaces if s.kind == "wall"]
    windows = [s for s in office.surfaces if s.kind == "window"]
    assert sum(w.area for w in walls) == pytest.approx(8.0 + 8.0)
    assert windows[0].area == pytest.approx(2.0)
    assert windows[0].face == "S"
    assert windows[0].shgc == pytest.approx(0.7)
    assert windows[0].u == pytest.approx(1.22)


def test_below_ground_walls_are_ground_coupled():
    project, _ = build_project(ROOMS, Nominal(), Design())
    basement = next(r for r in project.rooms if r.name == "Basement")
    assert all(s.ground for s in basement.surfaces)


def test_project_runs_through_manual_j():
    project, _ = build_project(ROOMS, Nominal(), Design())
    result = calculate(project)
    assert result["totals"]["heating_w"] > 0
    assert result["rooms"]["Office"]["heating_w"] > 0


def test_room_capacities_use_volume():
    caps = room_capacities(ROOMS)
    assert caps["office"] == pytest.approx(28.8 * 1200.0 * 1005.0)
    assert "empty" not in caps


def test_no_usable_room_is_an_error():
    with pytest.raises(ValueError):
        build_project({"empty": ROOMS["empty"]}, Nominal(), Design())
