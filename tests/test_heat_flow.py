"""The Heat flow overlay's flows, from House Structure's rooms and the fitted zones."""

import pytest

from custom_components.home_thermal_lab.heat_flow import (
    AIR_HEAT_CAPACITY_J_M3K,
    FLOOR_U,
    INTERNAL_WALL_U,
    ZoneNow,
    capacity,
    flows,
)


def room(area, volume=30.0, walls=(), neighbours=(), internal=(), floor=None):
    return {
        "area_id": area,
        "title": area.title(),
        "volume_m3": volume,
        "floor_m2": floor,
        "walls": [{"face": f, "area_m2": m2} for f, m2 in walls],
        "internal_walls": [{"other_area_id": o, "area_m2": m2} for o, m2 in internal],
        "neighbours": [
            {"area_id": o, "position": p, "area_m2": m2} for o, p, m2 in neighbours
        ],
    }


def watts(rate_per_h, volume=30.0):
    return rate_per_h * volume * AIR_HEAT_CAPACITY_J_M3K / 3600.0


ROOMS = {
    "office": room(
        "office",
        walls=[("N", 6.0), ("E", 3.0)],
        neighbours=[("kitchen", "beside", 8.0), ("bed", "above", None)],
        floor=12.0,
    ),
    "kitchen": room("kitchen", neighbours=[("office", "beside", 8.0)]),
    "bed": room("bed", neighbours=[("office", "below", None)], floor=10.0),
}


def test_capacity_from_volume_or_floor():
    assert capacity({"volume_m3": 10.0}) == 10.0 * AIR_HEAT_CAPACITY_J_M3K
    assert capacity({"floor_m2": 10.0, "height_m": 2.0}) == pytest.approx(
        20.0 * AIR_HEAT_CAPACITY_J_M3K
    )
    assert capacity({"floor_m2": 10.0}) == pytest.approx(24.0 * AIR_HEAT_CAPACITY_J_M3K)
    assert capacity({}) is None


def test_between_uses_nominal_u_and_points_from_the_warmer_room():
    temps = {"office": 20.0, "kitchen": 22.0, "bed": 19.0}
    got = flows(ROOMS, {}, temps, None, {})
    between = {(b["from"], b["to"]): b["w"] for b in got["between"]}
    assert between[("kitchen", "office")] == pytest.approx(8.0 * INTERNAL_WALL_U * 2.0)
    # above or below with no area given: the smaller floor
    assert between[("office", "bed")] == pytest.approx(10.0 * FLOOR_U * 1.0)
    assert len(between) == 2  # each pair once


def test_between_uses_the_fitted_neighbour_coupling():
    temps = {"office": 20.0, "kitchen": 22.0, "bed": 19.0}
    zones = {"office": ZoneNow("Office", a=0.1, n=0.2)}
    got = flows(ROOMS, {}, temps, None, zones)
    between = {(b["from"], b["to"]): b["w"] for b in got["between"]}
    # n's conductance shared over the wall (8 m2) and the floor (10 m2)
    ua = watts(0.2)
    assert between[("kitchen", "office")] == pytest.approx(ua * 8 / 18 * 2.0, abs=0.1)
    assert between[("office", "bed")] == pytest.approx(ua * 10 / 18 * 1.0, abs=0.1)


def test_outside_is_the_fitted_loss_shared_over_the_faces():
    temps = {"office": 20.0}
    zones = {"office": ZoneNow("Office", a=0.1)}
    got = flows(ROOMS, {"office": "Office"}, temps, -10.0, zones)
    total = watts(0.1 * -30.0)
    faces = {o["face"]: o["w"] for o in got["outside"] if o["room"] == "office"}
    assert faces["N"] == pytest.approx(total * 6 / 9, abs=0.1)
    assert faces["E"] == pytest.approx(total * 3 / 9, abs=0.1)
    assert all(w < 0 for w in faces.values())  # heat leaving
    # the rooms without a zone are named
    assert any("Bed" in n and "Kitchen" in n for n in got["notes"])


def test_heating_only_while_calling():
    zones = {"office": ZoneNow("Office", a=0.1, h=2.0, heating=True)}
    got = flows(ROOMS, {}, {"office": 20.0}, 0.0, zones)
    assert got["heating"] == [{"room": "office", "w": round(watts(2.0), 1)}]
    zones = {"office": ZoneNow("Office", a=0.1, h=2.0, heating=False)}
    assert flows(ROOMS, {}, {"office": 20.0}, 0.0, zones)["heating"] == []


def test_solar_is_the_models_and_notes_a_big_difference_from_the_glass():
    zones = {"office": ZoneNow("Office", a=0.1, g=0.001, light=300.0)}
    model = watts(0.001 * 300.0)
    got = flows(ROOMS, {"office": "Office"}, {}, None, zones, {"office": model})
    assert got["solar"] == [{"room": "office", "w": round(model, 1)}]
    assert not any("credits" in n for n in got["notes"])
    got = flows(ROOMS, {"office": "Office"}, {}, None, zones, {"office": 4 * model})
    assert any("Office: the model credits" in n for n in got["notes"])


def test_a_room_without_a_size_or_walls_is_noted():
    rooms = {"den": room("den", volume=None), "hall": room("hall")}
    zones = {"den": ZoneNow("Den", a=0.1), "hall": ZoneNow("Hall", a=0.1)}
    got = flows(rooms, {}, {"den": 20.0, "hall": 20.0}, 0.0, zones)
    assert got["outside"] == []
    assert any("No volume" in n and "Den" in n for n in got["notes"])
    assert any("No outside walls" in n and "Hall" in n for n in got["notes"])


def test_missing_temperatures_skip_the_flow_and_are_noted():
    got = flows(ROOMS, {}, {"office": 20.0}, None, {})
    assert got["between"] == []
    assert any(n.startswith("No temperature now") for n in got["notes"])
    assert any("No outdoor temperature" in n for n in got["notes"])
