"""Zones filled in from House Structure's rooms."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.irradiance import (
    Irradiance,
    light_on_planes,
    light_on_surfaces,
)
from custom_components.home_thermal_lab.options import (
    from_structure,
    has_walls,
    structure_rooms,
)

ROOM = {
    "area_id": "master",
    "below_ground": False,
    "temperature_entity": "sensor.master_t",
    "windows": [
        {"azimuth": 190.4, "tilt": 90.0, "shade_below": 8.0, "glass_m2": 1.7},
    ],
    "walls": [
        # the wall with the window, and a windowless east wall
        {"azimuth": 190.4, "tilt": 90.0, "shade_below": 8.0, "glass_m2": 1.7},
        {"azimuth": 100.4, "tilt": 90.0, "shade_below": 8.0, "glass_m2": 0.0},
    ],
    "roofs": [{"azimuth": 280.4, "tilt": 45.0, "shade_below": 0.0}],
    "registers": [{"climate": "climate.z3", "fan": None}],
}


def test_a_zone_takes_its_room():
    zone = from_structure(
        {"name": "Master", "area_id": "master", "windows": ["N"], "roofs": [["E", 30]]},
        ROOM,
    )
    assert zone["climate_entity"] == "climate.z3"
    assert zone["room_entity"] == "sensor.master_t"
    # the typed faces give way to the room's planes
    assert (zone["windows"], zone["roofs"], zone["sunlit_walls"]) == ([], [], [])
    assert zone["window_planes"] == [[190.4, 90.0, 8.0], [280.4, 45.0, 0.0]]
    assert zone["wall_planes"] == [[100.4, 90.0, 8.0]]
    assert has_walls(zone)
    assert "below_ground" not in zone


def test_what_the_zone_names_itself_wins():
    zone = from_structure(
        {
            "climate_entity": "climate.other",
            "room_entity": "sensor.mine",
            "below_ground": False,
        },
        {**ROOM, "below_ground": True},
    )
    assert zone["climate_entity"] == "climate.other"
    assert zone["room_entity"] == "sensor.mine"
    assert zone["below_ground"] is False


def test_below_ground_comes_from_the_room():
    zone = from_structure({}, {**ROOM, "below_ground": True})
    assert zone["below_ground"] is True
    assert "below_ground" not in from_structure(
        {}, {**ROOM, "below_ground": True}, ground=False
    )


def test_no_room_leaves_the_zone_alone():
    zone = {"windows": ["S"]}
    assert from_structure(zone, None) is zone


def test_rooms_need_the_known_version():
    assert structure_rooms(None) == {}
    assert structure_rooms({"version": 2, "rooms": {"a": {}}}) == {}
    assert structure_rooms({"version": 1, "rooms": {"a": {}}}) == {"a": {}}


@pytest.mark.parametrize("azimuth", [120.0, 160.0, 200.0, 250.0])
def test_planes_match_typed_faces(azimuth):
    reading = Irradiance(datetime(2026, 11, 2, 19, tzinfo=UTC), 700.0, 60.0)
    faces = light_on_surfaces(reading, azimuth, 20.0, ["S"], [("W", 45.0)], 10.4)
    planes = light_on_planes(
        reading, azimuth, 20.0, [[190.4, 90.0, 0.0], [280.4, 45.0, 0.0]]
    )
    assert planes == pytest.approx(faces)


def test_planes_are_shaded_by_their_own_setting():
    reading = Irradiance(datetime(2026, 11, 2, 19, tzinfo=UTC), 700.0, 60.0)
    lit = light_on_planes(reading, 180.0, 5.0, [[180.0, 90.0, 0.0]])
    shaded = light_on_planes(reading, 180.0, 5.0, [[180.0, 90.0, 10.0]])
    assert shaded == pytest.approx(30.0)  # half the sky only
    assert lit > shaded
