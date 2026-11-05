"""Zones filled in from House Structure's rooms."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.irradiance import (
    Irradiance,
    light_on_planes,
    light_on_surfaces,
)
from custom_components.home_thermal_lab.migrate import ROOM_SUN_KEYS
from custom_components.home_thermal_lab.options import (
    from_structure,
    has_walls,
    sensor_choices,
    structure_rooms,
    wall_planes,
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
    zone = from_structure({"name": "Master", "area_id": "master"}, ROOM)
    assert zone["climate_entity"] == "climate.z3"
    assert zone["room_entity"] == "sensor.master_t"
    # compass planes, already turned by House Structure's rotation
    assert zone["window_planes"] == [[190.4, 90.0, 8.0], [280.4, 45.0, 0.0]]
    # no wall areas: the windowless wall alone, in full
    assert zone["wall_planes"] == [[100.4, 90.0, 8.0, 1.0]]
    assert has_walls(zone)
    assert zone["below_ground"] is False
    assert not set(ROOM_SUN_KEYS) & (set(zone) - {"below_ground"})


def test_a_room_without_sun_gives_none():
    zone = from_structure({}, {"area_id": "hall", "walls": [], "windows": []})
    assert zone["window_planes"] == zone["wall_planes"] == []
    assert not has_walls(zone)


def test_the_zones_own_thermostat_and_sensor_win():
    zone = from_structure(
        {"climate_entity": "climate.other", "room_entity": "sensor.mine"},
        {**ROOM, "below_ground": True},
    )
    assert zone["climate_entity"] == "climate.other"
    assert zone["room_entity"] == "sensor.mine"
    assert zone["below_ground"] is True


def test_below_ground_comes_from_the_room():
    zone = from_structure({}, {**ROOM, "below_ground": True})
    assert zone["below_ground"] is True
    assert "below_ground" not in from_structure(
        {}, {**ROOM, "below_ground": True}, ground=False
    )


def test_rooms_need_the_known_version():
    assert structure_rooms(None) == {}
    assert structure_rooms({"version": 2, "rooms": {"a": {}}}) == {}
    assert structure_rooms({"version": 1, "rooms": {"a": {}}}) == {"a": {}}


@pytest.mark.parametrize("azimuth", [120.0, 160.0, 200.0, 250.0])
def test_planes_match_the_old_typed_faces(azimuth):
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


def wall(azimuth, area=None, glass=0.0, door=0.0):
    return {
        "azimuth": azimuth,
        "tilt": 90.0,
        "shade_below": 0.0,
        "area_m2": area,
        "glass_m2": glass,
        "door_m2": door,
    }


def test_a_wall_with_a_window_counts_by_its_solid_area():
    # south: 10 m2 with 2 of glass and 2 of door; east: 6 m2 solid
    planes = wall_planes([wall(180.0, 10.0, glass=2.0, door=2.0), wall(90.0, 6.0)])
    assert planes == [[180.0, 90.0, 0.0, 0.5], [90.0, 90.0, 0.0, 0.5]]


def test_the_shares_scale_each_walls_light():
    reading = Irradiance(datetime(2026, 11, 2, 19, tzinfo=UTC), 700.0, 60.0)
    planes = wall_planes([wall(180.0, 9.0, glass=3.0), wall(90.0, 2.0)])
    south = light_on_planes(reading, 180.0, 20.0, [[180.0, 90.0, 0.0]])
    east = light_on_planes(reading, 180.0, 20.0, [[90.0, 90.0, 0.0]])
    got = light_on_planes(reading, 180.0, 20.0, planes)
    assert got == pytest.approx(0.75 * south + 0.25 * east, rel=1e-3)


def test_walls_facing_the_same_way_are_one_plane():
    planes = wall_planes([wall(180.0, 4.0), wall(180.0, 4.0), wall(0.0, 8.0)])
    assert planes == [[180.0, 90.0, 0.0, 0.5], [0.0, 90.0, 0.0, 0.5]]


def test_a_wall_without_an_area_takes_the_others_mean():
    planes = wall_planes([wall(180.0, None, glass=1.0), wall(90.0, 5.0)])
    # the south wall is taken as 5 m2, less its 1 m2 of glass
    assert planes == [
        [180.0, 90.0, 0.0, round(4 / 9, 4)],
        [90.0, 90.0, 0.0, round(5 / 9, 4)],
    ]


def test_all_glass_and_no_walls_give_no_planes():
    assert wall_planes([wall(180.0, 3.0, glass=3.0)]) == []
    assert wall_planes([]) == []


def test_several_sensors_and_none_chosen_are_named():
    room = {"temperature_entity": None, "temperature_choices": ["sensor.a", "sensor.b"]}
    assert sensor_choices({}, room) == ["sensor.a", "sensor.b"]
    # the zone picks its own, or House Structure has one: no doubt
    assert sensor_choices({"room_entity": "sensor.a"}, room) == []
    assert sensor_choices({}, {**room, "temperature_entity": "sensor.b"}) == []
    # none at all, or an older House Structure without the key
    assert sensor_choices({}, {"temperature_entity": None}) == []
