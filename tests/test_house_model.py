"""Tests for building the Manual J project from House Structure's rooms."""

from dataclasses import replace

import pytest

from custom_components.home_thermal_lab.house_model import (
    Nominal,
    build_project,
    envelope_from_fit,
    room_capacities,
)
from custom_components.home_thermal_lab.manual import Design, Furnace, calculate

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


def test_register_ducts_become_runs():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [{"area_m2": 10.0, "glass_m2": 0.0, "azimuth": 0.0}],
            "roofs": [],
            "windows": [],
            "registers": [
                {
                    "title": "Office register",
                    "free_area_in2": 60.0,
                    "flow_cfm": 90.0,
                    "duct": [
                        {
                            "shape": "round",
                            "diameter_in": 4.0,
                            "length_ft": 14.0,
                            "fittings_k": 0.9,
                        },
                        {
                            "shape": "rect",
                            "width_in": 10.0,
                            "height_in": 6.0,
                            "length_ft": 3.0,
                            "trunk": True,
                            "flow_cfm": 400.0,
                        },
                    ],
                }
            ],
        }
    }
    project, _ = build_project(rooms, Nominal(), Design())
    (run,) = project.runs
    assert run.room == "Office"
    assert run.register_area_m2 == pytest.approx(60 * 0.00064516)
    assert run.flow_m3s == pytest.approx(90 * 0.000471947)
    assert len(run.segments) == 2
    # no furnace, so no blower curve: the duct check is skipped, and says so
    result = calculate(project)
    assert result["ducts"]["runs"] == []
    assert any("Duct check skipped" in w for w in result["warnings"])


def test_stored_r_values_and_glazing_override_the_defaults():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [
                {"area_m2": 10.0, "glass_m2": 0.0, "azimuth": 0.0, "r_value_si": 5.0}
            ],
            "roofs": [],
            "windows": [
                {
                    "in": "wall",
                    "glass_m2": 2.0,
                    "azimuth": 180.0,
                    "transmittance": 0.5,
                    "glazing": "triple",
                    "frame": "wood",
                }
            ],
        }
    }
    project, _ = build_project(rooms, Nominal(), Design())
    room = project.rooms[0]
    wall = next(s for s in room.surfaces if s.kind == "wall")
    window = next(s for s in room.surfaces if s.kind == "window")
    assert wall.r == pytest.approx(5.0)
    assert window.u == pytest.approx(1.0)  # triple wood


def test_envelope_from_fit_recovers_the_scale():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [{"area_m2": 40.0, "glass_m2": 0.0}],
            "roofs": [],
            "windows": [],
        }
    }
    nominal_ua = 40.0 / 3.5
    fixed, infil = 2.0, 5.0
    cap = room_capacities(rooms)["office"]
    # the fitted rate that would give a measured envelope of 1.0 x nominal
    rate = (fixed + infil + nominal_ua) * 3600.0 / cap
    result = envelope_from_fit(
        rooms,
        rates={"office": rate},
        capacities={"office": cap},
        fixed_ua={"office": fixed},
        infiltration={"office": infil},
        nominal=Nominal(),
    )
    assert result["office"]["scale"] == pytest.approx(1.0)
    assert result["office"]["elements"][0]["r"] == pytest.approx(3.5)


def test_rooms_without_a_fit_are_left_out():
    rooms = {"office": {"volume_m3": 50.0, "walls": [{"area_m2": 9.0}]}}
    assert envelope_from_fit(rooms, {}, {}, {}, {}, Nominal()) == {}


CFM = 0.000471947


def _tree_rooms(**overrides):
    """Two rooms whose registers hang off one shared trunk."""

    def room(title, reg_title, flow, duct):
        return {
            "title": title,
            "volume_m3": 50.0,
            "walls": [{"area_m2": 10.0, "glass_m2": 0.0}],
            "roofs": [],
            "windows": [],
            "registers": [
                {
                    "title": reg_title,
                    "free_area_in2": 60.0,
                    "flow_cfm": flow,
                    "upstream": overrides.get("upstream", "Trunk"),
                    "duct": duct,
                }
            ],
        }

    branch_a = [{"shape": "round", "diameter_in": 4.0, "length_ft": 10.0}]
    branch_b = [{"shape": "rect", "width_in": 10.0, "height_in": 6.0, "length_ft": 4.0}]
    return {
        "a": room("A", "A reg", 300.0, branch_a),
        "b": room("B", "B reg", 200.0, branch_b),
    }


TREE = {
    "Plenum": {
        "upstream": None,
        "segments": [
            {"shape": "round", "diameter_in": 10.0, "length_ft": 6.0, "fittings_k": 0.5}
        ],
    },
    "Trunk": {
        "upstream": "Plenum",
        "segments": [{"shape": "round", "diameter_in": 8.0, "length_ft": 12.0}],
    },
}


def test_registers_share_their_upstream_sections():
    project, warnings = build_project(_tree_rooms(), Nominal(), Design(), ducts=TREE)
    runs = {r.name: r for r in project.runs}
    a = runs["A reg"]
    # the plenum, the trunk, then the register's own branch
    assert [s.trunk for s in a.segments] == [True, True, False]
    assert a.segments[0].length_m == pytest.approx(6 * 0.3048)
    assert a.segments[1].length_m == pytest.approx(12 * 0.3048)
    assert a.segments[2].length_m == pytest.approx(10 * 0.3048)
    # the shared sections carry both registers' airflow
    assert a.segments[0].flow_m3s == pytest.approx(500 * CFM)
    assert a.segments[1].flow_m3s == pytest.approx(500 * CFM)
    assert a.segments[2].flow_m3s is None
    assert runs["B reg"].segments[0].flow_m3s == pytest.approx(500 * CFM)
    assert not any("airflow" in w for w in warnings)


def test_shared_sections_are_checked_at_their_total_airflow():
    project, _ = build_project(_tree_rooms(), Nominal(), Design(), ducts=TREE)
    project = replace(
        project,
        furnace=Furnace({"high": 30000.0}, blower=((0.1, 50.0), (0.8, 400.0))),
    )
    result = calculate(project)
    runs = {r["name"]: r for r in result["ducts"]["runs"]}
    flows = [s["flow_m3s"] for s in runs["A reg"]["segments"]]
    assert flows[0] == pytest.approx(500 * CFM)
    assert flows[2] == pytest.approx(300 * CFM)


def test_an_unknown_upstream_section_leaves_the_register_out():
    project, warnings = build_project(
        _tree_rooms(upstream="Nowhere"), Nominal(), Design(), ducts=TREE
    )
    assert project.runs == ()
    assert any("no duct section called 'Nowhere'" in w for w in warnings)


def test_looping_sections_are_reported():
    loop = {
        "X": {"upstream": "Y", "segments": TREE["Trunk"]["segments"]},
        "Y": {"upstream": "X", "segments": TREE["Trunk"]["segments"]},
    }
    project, warnings = build_project(
        _tree_rooms(upstream="X"), Nominal(), Design(), ducts=loop
    )
    assert project.runs == ()
    assert any("loop" in w for w in warnings)


def test_a_register_without_airflow_is_said_to_understate_its_trunk():
    rooms = _tree_rooms()
    del rooms["a"]["registers"][0]["flow_cfm"]
    _, warnings = build_project(rooms, Nominal(), Design(), ducts=TREE)
    assert any("no design airflow" in w for w in warnings)


def test_registers_with_no_sections_keep_their_full_duct():
    project, _ = build_project(_tree_rooms(upstream=None), Nominal(), Design())
    (run,) = project.runs[:1]
    assert len(run.segments) == 1  # only its own branch, as before
