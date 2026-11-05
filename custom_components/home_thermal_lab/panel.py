"""The Zones tab on House Structure's Thermal Lab page (needs Home Assistant).

House Structure registers the Thermal Lab sidebar page; this adds the Zones
tab to it (``hass.data["house_structure_tabs"]``), a single page
(``frontend/index.html``) drawn with Chart.js. Chart.js and the page's
connection and theme helpers (``tab.js``) are House Structure's, served by Home
Assistant itself, so opening the tab fetches nothing from the internet. Without
House Structure there is no page to show the tab on; the sensors work anyway.

It also adds the **Heat flow** overlay to House Structure's House tab
(``hass.data["house_structure_overlays"]``, worked out in ``heat_flow.py``),
and publishes each zone's fitted cooling rate for Manual J
(``hass.data["home_thermal_lab_fitted"]``, ``{area_id: {"a": per_hour}}``,
with the event ``home_thermal_lab_fitted_updated``).

The page asks for its data over Home Assistant's own websocket connection (no
separate login):

* ``home_thermal_lab/zones``: the zones and their sensors.
* ``home_thermal_lab/zone`` (``zone``, ``hours``): one zone's history (room,
  outdoor, setpoint, target band, forecasts as issued, heating calls), the day
  ahead, the model card and the status tiles; the other rooms on the zone's
  thermostat (from House Structure); and the fixed chart scales, one indoor
  span shared by every zone and one outdoor span for the whole year.
* ``home_thermal_lab/heat_flow``: the Heat flow overlay's flows now.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import logging
from pathlib import Path

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from . import DOMAIN
from .calls import temperature_series
from .ha_rows import numbers, recorded
from .heat_flow import ZoneNow, flows
from .options import STRUCTURE_DOMAIN, has_walls, structure_rooms
from .panel_data import (
    action_spans,
    archive,
    future,
    merge_spans,
    ms,
    same_thermostat,
    series,
    setpoints,
    span,
    statistic_values,
    subtract_spans,
)

_LOGGER = logging.getLogger(__name__)

STATIC_URL = "/home_thermal_lab_static"
FRONTEND = Path(__file__).parent / "frontend"
MAX_HOURS = 24 * 60  # the recorder keeps 60 days here
SCALES_EVERY = timedelta(hours=6)  # how often the fixed chart scales are redone
STATISTICS_SINCE = datetime(2000, 1, 1, tzinfo=UTC)  # long-term statistics: all

# House Structure's Thermal Lab page: its tabs and the House tab's overlays
TABS = "house_structure_tabs"
TABS_EVENT = "house_structure_tabs_updated"
TAB_KEY = "zones"
TAB_ORDER = 30
OVERLAYS = "house_structure_overlays"
OVERLAYS_EVENT = "house_structure_overlays_updated"
OVERLAY_KEY = "heat_flow"
OVERLAY_REFRESH_S = 60
# Each zone's fitted cooling rate, for Manual J
FITTED = "home_thermal_lab_fitted"
FITTED_EVENT = "home_thermal_lab_fitted_updated"


def _version() -> str:
    """A short hash of the page, to bust caches when it changes."""
    return hashlib.sha256((FRONTEND / "index.html").read_bytes()).hexdigest()[:10]


async def async_register_tab(hass) -> None:
    """Serve the page and add the commands once; add the tab and the overlay."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("static"):
        data["static"] = True
        if hass.http is not None:  # None in tests without a web server
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_URL, str(FRONTEND), cache_headers=True)]
            )
        websocket_api.async_register_command(hass, ws_zones)
        websocket_api.async_register_command(hass, ws_zone)
        websocket_api.async_register_command(hass, ws_heat_flow)
    if data.get("tab"):
        return
    version = await hass.async_add_executor_job(_version)
    hass.data.setdefault(TABS, {})[TAB_KEY] = {
        "title": "Zones",
        "url": f"{STATIC_URL}/index.html?v={version}",
        "order": TAB_ORDER,
    }
    hass.bus.async_fire(TABS_EVENT)
    hass.data.setdefault(OVERLAYS, {})[OVERLAY_KEY] = {
        "title": "Heat flow",
        "command": f"{DOMAIN}/heat_flow",
        "refresh_s": OVERLAY_REFRESH_S,
    }
    hass.bus.async_fire(OVERLAYS_EVENT)
    data["tab"] = True


def async_remove_tab(hass) -> None:
    """Take the tab, the overlay and the fitted rates back (the files stay)."""
    data = hass.data.get(DOMAIN, {})
    if data.pop("tab", False):
        hass.data.get(TABS, {}).pop(TAB_KEY, None)
        hass.bus.async_fire(TABS_EVENT)
        hass.data.get(OVERLAYS, {}).pop(OVERLAY_KEY, None)
        hass.bus.async_fire(OVERLAYS_EVENT)
    if hass.data.pop(FITTED, None) is not None:
        hass.bus.async_fire(FITTED_EVENT)


def _zones(hass) -> dict:
    return hass.data.get(DOMAIN, {}).get("zones", {})


@websocket_api.websocket_command({vol.Required("type"): "home_thermal_lab/zones"})
@callback
def ws_zones(hass, connection, msg) -> None:
    """List the zones with their sensors."""
    connection.send_result(
        msg["id"],
        [
            {"key": key, "name": brain.zone["name"], "entities": brain.entities}
            for key, brain in sorted(_zones(hass).items(), key=lambda kv: kv[0])
        ],
    )


def _attrs(hass, entity_id: str | None) -> dict:
    state = hass.states.get(entity_id) if entity_id else None
    return dict(state.attributes) if state else {}


def _state(hass, entity_id: str | None):
    state = hass.states.get(entity_id) if entity_id else None
    return state.state if state else None


async def _extremes(hass, entity_id: str) -> list[float]:
    """Every hourly min and max in an entity's long-term statistics (all kept)."""
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        STATISTICS_SINCE,
        None,
        {entity_id},
        "month",
        None,
        {"min", "max"},
    )
    return statistic_values(found.get(entity_id, []))


async def _work_out_scales(hass) -> dict:
    """The fixed temperature axes of the charts.

    Indoor: one span for every zone, around each zone's room temperature and
    thermostat setpoints over the recorder's history (``MAX_HOURS``) and its
    target wave's band. Outdoor: one span all year, around the outdoor
    sensor's long-term statistics (its recorded history if it has none).
    """
    brains = list(_zones(hass).values())
    if not brains:
        return {"indoor": None, "outdoor": None}
    end = datetime.now(UTC)
    start = end - timedelta(hours=MAX_HOURS)
    outdoor_id = brains[0].outdoor_entity
    ids = {outdoor_id}
    for brain in brains:
        ids.add(brain.zone["climate_entity"])
        if brain.zone.get("room_entity"):
            ids.add(brain.zone["room_entity"])
    rows = await recorded(hass, sorted(ids), start, end)
    indoor: list[float] = []
    for brain in brains:
        climate_rows = rows[brain.zone["climate_entity"]]
        room_id = brain.zone.get("room_entity")
        room = numbers(rows[room_id]) if room_id else temperature_series(climate_rows)
        indoor += [v for _, v in room]
        indoor += setpoints(climate_rows)
        wave = brain.wave
        if wave is not None:
            indoor += [
                wave.mean - wave.swing - wave.band,
                wave.mean + wave.swing + wave.band,
            ]
    try:
        outdoor = await _extremes(hass, outdoor_id)
    except Exception:  # fall back to the recorded history
        _LOGGER.debug("No long-term statistics for %s", outdoor_id, exc_info=True)
        outdoor = []
    if not outdoor:
        outdoor = [v for _, v in numbers(rows[outdoor_id])]
    return {"indoor": span(indoor, 1.0), "outdoor": span(outdoor, 5.0)}


async def _scales(hass) -> dict:
    """The fixed chart scales, worked out at most every ``SCALES_EVERY``."""
    data = hass.data.setdefault(DOMAIN, {})
    lock = data.setdefault("scales_lock", asyncio.Lock())
    async with lock:
        cached = data.get("scales")
        now = datetime.now(UTC)
        if cached is None or now - cached[0] > SCALES_EVERY:
            try:
                cached = (now, await _work_out_scales(hass))
            except Exception:  # the charts then scale themselves
                _LOGGER.warning("Could not work out the chart scales", exc_info=True)
                cached = (now, {"indoor": None, "outdoor": None})
            data["scales"] = cached
        return cached[1]


def _house_calls(rows: dict, climates: set[str], end: datetime) -> dict:
    """Each thermostat's heating, cooling and fan runs, by thermostat."""
    return {
        kind: {c: action_spans(rows.get(c, []), end, action) for c in climates}
        for kind, action in (("heat", "heating"), ("cool", "cooling"), ("fan", "fan"))
    }


def _others(hass, zone: dict) -> list[tuple[str, str]]:
    """``(name, temperature sensor)`` of the other rooms on the zone's thermostat."""
    rooms = structure_rooms(hass.data.get(STRUCTURE_DOMAIN))
    skip = {zone["room_entity"]} if zone.get("room_entity") else set()
    areas = ar.async_get(hass)
    out = []
    for area_id, sensor in same_thermostat(rooms, zone["climate_entity"], skip):
        area = areas.async_get_area(area_id)
        out.append((area.name if area else area_id, sensor))
    return out


@websocket_api.websocket_command(
    {
        vol.Required("type"): "home_thermal_lab/zone",
        vol.Required("zone"): str,
        vol.Optional("hours", default=24): vol.All(
            vol.Coerce(int), vol.Range(1, MAX_HOURS)
        ),
    }
)
@websocket_api.async_response
async def ws_zone(hass, connection, msg) -> None:
    """One zone's history, day ahead, model card and status."""
    brain = _zones(hass).get(msg["zone"])
    if brain is None:
        connection.send_error(msg["id"], "not_found", "No such zone")
        return
    zone = brain.zone
    end = datetime.now(UTC)
    start = end - timedelta(hours=msg["hours"])
    climate_id = zone["climate_entity"]
    room_id = zone.get("room_entity")
    ent = brain.entities
    ids = [climate_id, brain.outdoor_entity]
    ids += [e for e in (room_id, ent.get("forecast"), ent.get("target")) if e]
    others = _others(hass, zone)
    ids += [sensor for _, sensor in others if sensor not in ids]
    # Every thermostat in the house, for the calls that bleed in and the fan.
    climates = {b.zone["climate_entity"] for b in _zones(hass).values()}
    climates.add(climate_id)
    ids += sorted(c for c in climates if c not in ids)
    rows = await recorded(hass, ids, start, end)
    calls = _house_calls(rows, climates, end)
    # Calls from any other thermostat can bleed in, whether or not the model
    # fitted them as neighbours (a zone fitted alone has none).
    neighbours = sorted(c for c in climates if c != climate_id)
    scales = await _scales(hass)
    room_rows = rows[room_id] if room_id else []
    room = (
        [[ms(t), v] for t, v in numbers(room_rows)]
        if room_id
        else [[ms(t), v] for t, v in temperature_series(rows[climate_id])]
    )
    forecast_rows = rows.get(ent.get("forecast"), [])
    target_rows = rows.get(ent.get("target"), [])
    forecast_attrs = _attrs(hass, ent.get("forecast"))
    shadow_attrs = _attrs(hass, ent.get("shadow"))
    target_attrs = _attrs(hass, ent.get("target"))
    model = brain.model
    connection.send_result(
        msg["id"],
        {
            "name": zone["name"],
            "now": ms(end),
            "start": ms(start),
            "scales": scales,
            "others": [
                {"name": name, "points": series(rows[sensor])}
                for name, sensor in others
            ],
            "history": {
                "room": room,
                "outdoor": series(rows[brain.outdoor_entity]),
                "setpoint": series(rows[climate_id], "temperature"),
                "lower": series(target_rows, "lower"),
                "upper": series(target_rows, "upper"),
                "issued": archive(forecast_rows),
                "heating": calls["heat"][climate_id],
                "heating_others": merge_spans(
                    [s for c in neighbours for s in calls["heat"][c]]
                ),
                "cooling": calls["cool"][climate_id],
                "cooling_others": merge_spans(
                    [s for c in neighbours for s in calls["cool"][c]]
                ),
                "fan": subtract_spans(
                    calls["fan"][climate_id],
                    merge_spans(
                        [
                            run
                            for c in climates
                            if c != climate_id
                            for kind in ("heat", "cool")
                            for run in calls[kind][c]
                        ]
                    ),
                ),
            },
            "future": future(forecast_attrs.get("points") or []),
            "status": {
                "room": room[-1][1] if room else None,
                "outdoor": _state(hass, brain.outdoor_entity),
                "target": _state(hass, ent.get("target")),
                "lower": target_attrs.get("lower"),
                "upper": target_attrs.get("upper"),
                "target_source": target_attrs.get("source"),
                "shadow": _state(hass, ent.get("shadow")),
                "lowest_vs_setpoint": shadow_attrs.get("lowest_vs_setpoint"),
                "setpoint": shadow_attrs.get("setpoint"),
                "action": shadow_attrs.get("thermostat_action"),
                "forecast_3h": _state(hass, ent.get("forecast")),
                "outdoor_correction": forecast_attrs.get("outdoor_correction"),
                "method": forecast_attrs.get("method"),
                "scores": {
                    k: v for k, v in forecast_attrs.items() if k.startswith("error_")
                },
            },
            "model": {
                **brain.quality,
                "note": brain.note,
                "given": brain.given,
                "terms": None
                if model is None
                else {
                    "a": model.a,
                    "c": model.c,
                    "g": model.g,
                    "w": model.w,
                    "b": model.b,
                    "h": model.h,
                    "n": model.n,
                    "x": model.x,
                    "lag": model.lag,
                },
                "has_walls": has_walls(zone),
                "below_ground": bool(zone["below_ground"]),
                "wave": None
                if brain.wave is None
                else {
                    "mean": brain.wave.mean,
                    "swing": brain.wave.swing,
                    "peak_hour": brain.wave.peak_hour,
                    "band": brain.wave.band,
                },
            },
        },
    )


def _rates(hass) -> dict[str, float]:
    """Each zone's fitted cooling rate ``a`` (per hour), by its House Structure area."""
    out: dict[str, float] = {}
    for brain in _zones(hass).values():
        area = brain.zone.get("area_id")
        if area and brain.model is not None and area not in out:
            out[area] = brain.model.a
    return out


@callback
def publish_fitted(hass) -> None:
    """Share the fitted cooling rates, and tell listeners when they change."""
    new = {area: {"a": a} for area, a in _rates(hass).items()}
    if hass.data.get(FITTED) != new:
        hass.data[FITTED] = new
        hass.bus.async_fire(FITTED_EVENT)


def _number(hass, entity_id: str | None) -> float | None:
    state = hass.states.get(entity_id) if entity_id else None
    try:
        return float(state.state)
    except (AttributeError, TypeError, ValueError):
        return None


def _glass(hass) -> dict[str, float]:
    """House Structure's sun through each room's windows now (W), by area.

    Its room sensors are the ``solar_gain`` sensors that list their windows.
    """
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    out: dict[str, float] = {}
    for entry in list(entities.entities.values()):
        if entry.platform != STRUCTURE_DOMAIN or not entry.unique_id.endswith(
            "_solar_gain"
        ):
            continue
        state = hass.states.get(entry.entity_id)
        if state is None or "windows" not in state.attributes:
            continue
        area = entry.area_id
        if area is None and entry.device_id:
            device = devices.async_get(entry.device_id)
            area = device.area_id if device else None
        watts = _number(hass, entry.entity_id)
        if area and watts is not None:
            out[area] = watts
    return out


async def _zone_now(hass, brain, now: datetime) -> ZoneNow | None:
    """A fitted zone's terms and what it is doing now (None without a model)."""
    model = brain.model
    if model is None:
        return None
    climate = hass.states.get(brain.zone["climate_entity"])
    heating = climate is not None and climate.attributes.get("hvac_action") == "heating"
    light = None
    try:
        _, lights, _, _ = await brain.inputs(now, 1, None)
        light = lights[0] if lights else None
    except Exception:  # no forecast yet: no sun drawn
        _LOGGER.debug("No light for %s", brain.zone["name"], exc_info=True)
    return ZoneNow(
        name=brain.zone["name"],
        a=model.a,
        g=model.g,
        h=model.h,
        n=model.n if brain.neighbours else 0.0,
        heating=heating,
        light=light,
    )


@websocket_api.websocket_command({vol.Required("type"): "home_thermal_lab/heat_flow"})
@websocket_api.async_response
async def ws_heat_flow(hass, connection, msg) -> None:
    """The Heat flow overlay: the flows into and between the rooms now, in watts."""
    now = datetime.now(UTC)
    rooms = structure_rooms(hass.data.get(STRUCTURE_DOMAIN))
    areas = ar.async_get(hass)
    names = {}
    for area_id in rooms:
        area = areas.async_get_area(area_id)
        if area is not None:
            names[area_id] = area.name
    temperatures = {}
    for area_id, room in rooms.items():
        value = _number(hass, room.get("temperature_entity"))
        if value is not None:
            temperatures[area_id] = value
    brains = list(_zones(hass).values())
    zones: dict[str, ZoneNow] = {}
    for brain in brains:
        area = brain.zone.get("area_id")
        if area in rooms and area not in zones:
            got = await _zone_now(hass, brain, now)
            if got is not None:
                zones[area] = got
            room_t = _number(hass, brain.zone.get("room_entity"))
            if area not in temperatures and room_t is not None:
                temperatures[area] = room_t
    outdoor = _number(hass, brains[0].outdoor_entity) if brains else None
    result = flows(rooms, names, temperatures, outdoor, zones, _glass(hass))
    connection.send_result(msg["id"], {"as_of": now.isoformat(), **result})
