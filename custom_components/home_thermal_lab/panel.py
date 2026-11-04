"""The Thermal Lab dashboard panel in Home Assistant's sidebar (needs Home Assistant).

Like ClimateAdvisor's panel: a single page (``frontend/index.html``) in an
iframe, drawn with Chart.js. Chart.js is vendored into ``frontend/`` (pinned in
``frontend/vendor.json``, refreshed with ``invoke vendor``) and served by Home
Assistant itself with long cache headers, so opening the panel fetches nothing
from the internet. The page asks for its data over the parent page's own
websocket connection (no separate login):

* ``home_thermal_lab/zones``: the zones and their sensors.
* ``home_thermal_lab/zone`` (``zone``, ``hours``): one zone's history (room,
  outdoor, setpoint, target band, forecasts as issued, heating calls), the day
  ahead, the model card and the status tiles; the other rooms on the zone's
  thermostat (from House Structure); and the fixed chart scales, one indoor
  span shared by every zone and one outdoor span for the whole year.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
import voluptuous as vol

from . import DOMAIN
from .calls import temperature_series
from .ha_rows import numbers, recorded
from .options import STRUCTURE_DOMAIN, has_walls, structure_rooms
from .panel_data import (
    archive,
    future,
    heating_spans,
    ms,
    same_thermostat,
    series,
    setpoints,
    span,
    statistic_values,
)

_LOGGER = logging.getLogger(__name__)

STATIC_URL = "/home_thermal_lab_static"
PANEL_PATH = "home-thermal-lab"
FRONTEND = Path(__file__).parent / "frontend"
MAX_HOURS = 24 * 60  # the recorder keeps 60 days here
SCALES_EVERY = timedelta(hours=6)  # how often the fixed chart scales are redone
STATISTICS_SINCE = datetime(2000, 1, 1, tzinfo=UTC)  # long-term statistics: all


def _version() -> str:
    """A short hash of the page and the vendored script, to bust caches."""
    digest = hashlib.sha256()
    for name in ("index.html", "chart.umd.min.js"):
        digest.update((FRONTEND / name).read_bytes())
    return digest.hexdigest()[:10]


async def async_register_panel(hass) -> None:
    """Register the static files, websocket commands and sidebar panel once."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("static"):
        data["static"] = True
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND), cache_headers=True)]
        )
        websocket_api.async_register_command(hass, ws_zones)
        websocket_api.async_register_command(hass, ws_zone)
    if data.get("panel"):
        return
    version = await hass.async_add_executor_job(_version)
    frontend.async_register_built_in_panel(
        hass,
        "iframe",
        sidebar_title="Thermal Lab",
        sidebar_icon="mdi:home-thermometer-outline",
        frontend_url_path=PANEL_PATH,
        require_admin=False,
        config={"url": f"{STATIC_URL}/index.html?v={version}"},
    )
    data["panel"] = True


def async_remove_panel(hass) -> None:
    """Take the panel out of the sidebar (the static files stay until restart)."""
    data = hass.data.get(DOMAIN, {})
    if data.pop("panel", False):
        frontend.async_remove_panel(hass, PANEL_PATH)


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
    rows = await recorded(hass, ids, start, end)
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
                "heating": heating_spans(rows[climate_id], end),
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
