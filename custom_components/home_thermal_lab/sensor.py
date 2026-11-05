"""Home Thermal Lab sensors. Nothing here switches anything.

Four kinds, added as sub-entries in the web interface (``config_flow.py``) or
configured under one ``sensor:`` platform entry in YAML (see the README for a
full example)::

    sensor:
      - platform: home_thermal_lab
        outdoor_entity: sensor.edmonton_temperature
        zones: [...]          # shadow controller, one sensor per zone (17)
        call_stats: [...]     # heating-call statistics per zone (05, 13)
        energy: [...]         # modelled furnace energy, for the energy dashboard
        contributions: [...]  # what each effect added to a zone (chart)

* **Shadow** (``zones``): ``skip`` or ``heat`` for a call starting now; the
  history of the sensor is the shadow-mode log (hypothesis 17). Each zone also
  has a **Forecast** sensor (the room 3 hours ahead; its history is the archive
  of forecasts as issued, hypothesis 16) and a **Target** sensor (the target
  wave), all three sharing one ``ZoneBrain`` that learns the model.
* **Call statistics** (``call_stats``): the number of heating calls in the last
  ``days``, with min, median and max length, rise, lag to the first rise, and
  the overshoot, dip and rebound after each call, split into low-stage and
  stepped-up calls (``calls.py``).
* **Energy** (``energy``): kWh, ``total_increasing``, integrated from the
  furnace state of all zone thermostats and a power per state (``energy.py``).
* **Contributions** (``contributions``): the zone's temperature now; the
  ``points`` attribute splits the last and next hours into the terms of
  ``contributions.py`` for a stacked chart.

This module needs Home Assistant and is not covered by the unit tests; the
logic it calls is.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from functools import partial
import logging

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from . import CALL_STATS, CONTRIBUTION, DOMAIN, ENERGY, ZONE
from .archive_records import (
    PARAM_NAMES,
    d_leads,
    outdoor_record,
    path_points,
    room_record,
    shared,
)
from .archive_store import get_store
from .calls import (
    calls_from_states,
    heat_setpoints,
    responses,
    summarise,
    temperature_series,
)
from .contributions import (
    Inputs,
    ZoneTerms,
    chart_points,
    dimmer_kw,
    forecast,
    held_values,
    on_fraction,
)
from .contributions import (
    history as split_history,
)
from .energy import MODES, Meter, furnace_mode
from .forecast import ForecastHour, fetch_forecast
from .ground import (
    DEFAULT_COLDEST_DAY,
    DEFAULT_MEAN,
    DEFAULT_SWING,
    ground_temperature,
)
from .ha_rows import numbers as _numbers
from .ha_rows import recorded as _recorded
from .house import (
    ZoneAhead,
    ZoneHistory,
    ZoneNow,
    forecast_house,
    hub_neighbours,
    neighbour_inputs,
)
from .hvac import HIGH, runs_from_states, stage_runs
from .hvac_response import merge_runs
from .irradiance import fetch_irradiance, light_on_planes
from .learn import (
    WALL_TAU_HOURS,
    NoHeatFit,
    ZoneData,
    bin_fraction,
    bin_held,
    blower_kw,
    cool_thermostat,
    edge_steps,
    fit_cool_rate,
    fit_furnace_lag,
    fit_heat_rate,
    fit_no_heat,
    fit_with_wall_lag,
    grade,
    lag,
    model_of,
    problem,
    refine_multistep,
    skill,
)
from .options import (
    STRUCTURE_DOMAIN,
    from_structure,
    has_walls,
    sensor_choices,
    structure_rooms,
    with_house,
)
from .outlook import (
    band_at,
    outlook_from_path,
    outlook_points,
    schedule_by_slot,
    setpoints_ahead,
    slot_of,
)
from .panel import async_register_tab, publish_fitted
from .power import power_series
from .routine import fit_offset_tau
from .scoring import (
    apply_bias,
    issued_from_archive,
    issued_from_rows,
    outdoor_bias,
    score,
)
from .shadow import ZoneModel, decide
from .solar import solar_azimuth_degrees, solar_elevation_degrees
from .target import TargetWave

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)
STEP_HOURS = 0.25
LOOK_AHEAD_STEPS = 12
FORECAST_MAX_AGE = timedelta(hours=1)
LEARN_EVERY = timedelta(hours=6)
LEARN_BIN = timedelta(minutes=15)
LEARN_DAYS = 14
LEARN_BLOCK = 4  # rates over an hour, against the thermostat's 0.1 C steps
WALL_TAUS = (1.5, 3.0, 6.0)  # sunlit-wall lags to try, hours
FORECAST_STEPS = 96  # 24 hours
LEADS = (1, 3, 6)  # hours; the forecast sensor's state is the 3 hour one
SCORE_DAYS = 7
BIAS_HOURS = 48  # Open-Meteo's past hours (past_days=2) against the sensor

SUN_SCHEMA = {
    # the area (room) in House Structure the sensor is for
    vol.Required("area_id"): cv.string,
    # filled in from House Structure: [compass azimuth, tilt, shade_below] of
    # the room's windows and roofs, and of its outside walls with each one's
    # share of the solid wall (``options.wall_planes``)
    vol.Optional("window_planes", default=[]): [
        vol.ExactSequence([vol.Coerce(float)] * 3)
    ],
    vol.Optional("wall_planes", default=[]): [
        vol.ExactSequence([vol.Coerce(float)] * 4)
    ],
}

GROUND_SCHEMA = {
    vol.Optional("ground_mean", default=DEFAULT_MEAN): vol.Coerce(float),
    vol.Optional("ground_swing", default=DEFAULT_SWING): vol.Coerce(float),
    vol.Optional("ground_coldest_day", default=DEFAULT_COLDEST_DAY): vol.Coerce(float),
}

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("room_entity"): cv.entity_id,
        # leave out (or leave a and c out) to learn the model from the recorder
        vol.Optional("model", default={}): vol.Schema(
            {
                vol.Optional("a"): vol.Coerce(float),
                vol.Optional("c"): vol.Coerce(float),
                vol.Optional("g", default=0.0): vol.Coerce(float),
                vol.Optional("b", default=0.0): vol.Coerce(float),
                vol.Optional("w", default=0.0): vol.Coerce(float),
                # heating rate while the zone's call runs; learned when left out
                vol.Optional("h"): vol.Coerce(float),
            }
        ),
        # a room (partly) below ground, from House Structure: its walls trade heat
        # with the soil. Give a ground temperature sensor, or leave it out to use
        # the annual ground wave.
        vol.Optional("below_ground", default=False): cv.boolean,
        vol.Optional("ground_entity"): cv.entity_id,
        **GROUND_SCHEMA,
        vol.Optional("tolerance", default=0.5): vol.Coerce(float),
        vol.Optional("max_dip", default=0.5): vol.Coerce(float),
        # the simulated thermostat of the forecast: calls start this far below
        # the setpoint (measured: a median 0.05 to 0.07 C, hypothesis 17)
        vol.Optional("deadband", default=0.1): vol.Coerce(float),
        # zones (climate entities) whose temperature and calls warm this one; left
        # empty, the zone that heats most is every other zone's neighbour, and
        # all the others are its (hypotheses 06, 10 and 16)
        vol.Optional("neighbours", default=[]): cv.entity_ids,
        # the target wave (target.py); without a mean the target is the setpoint
        vol.Optional("target_mean"): vol.Coerce(float),
        vol.Optional("target_swing", default=0.0): vol.Coerce(float),
        vol.Optional("target_peak_hour", default=15.0): vol.Coerce(float),
        vol.Optional("target_band", default=0.5): vol.Coerce(float),
        **SUN_SCHEMA,
    }
)

CALL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("area_id"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("days", default=7): vol.All(vol.Coerce(int), vol.Range(1, 60)),
        vol.Optional("after_minutes", default=90): vol.Coerce(float),
    }
)

ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entities"): cv.entity_ids,
        vol.Optional("kw", default={}): vol.Schema({vol.In(MODES): vol.Coerce(float)}),
        # a whole-house power sensor: the blower powers are learned from it
        vol.Optional("power_entity"): cv.entity_id,
        vol.Optional("learn_days", default=14): vol.All(
            vol.Coerce(int), vol.Range(2, 60)
        ),
        # no longer used (the furnace's room is House Structure's Furnace
        # part now); still accepted so older YAML loads
        vol.Optional("area_id"): cv.string,
    }
)

CONTRIBUTION_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("room_entity"): cv.entity_id,
        vol.Optional("other_climate_entities", default=[]): cv.entity_ids,
        vol.Optional("plug_entities", default=[]): cv.entity_ids,
        # dimmed lights without a meter: light entity -> watts at full brightness
        vol.Optional("lights", default={}): {cv.entity_id: vol.Coerce(float)},
        vol.Required("terms"): vol.Schema(
            {
                vol.Required("a"): vol.Coerce(float),
                vol.Required("c"): vol.Coerce(float),
                vol.Optional("g", default=0.0): vol.Coerce(float),
                vol.Optional("h", default=0.0): vol.Coerce(float),
                vol.Optional("x", default=0.0): vol.Coerce(float),
                vol.Optional("p", default=0.0): vol.Coerce(float),
                vol.Optional("w", default=0.0): vol.Coerce(float),
            }
        ),
        vol.Optional("hours_back", default=24): vol.All(
            vol.Coerce(int), vol.Range(1, 72)
        ),
        vol.Optional("hours_ahead", default=24): vol.All(
            vol.Coerce(int), vol.Range(1, 48)
        ),
        vol.Optional("deadband", default=0.5): vol.Coerce(float),
        **SUN_SCHEMA,
    }
)

AREA_SCHEMA = vol.Schema(
    {vol.Required("name"): cv.string, vol.Required("area_id"): cv.string},
    extra=vol.ALLOW_EXTRA,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional("outdoor_entity"): cv.entity_id,
        # zones and contributions are checked once House Structure's room is
        # filled in (``_with_room``)
        vol.Optional("zones", default=[]): [AREA_SCHEMA],
        vol.Optional("call_stats", default=[]): [CALL_SCHEMA],
        vol.Optional("energy", default=[]): [ENERGY_SCHEMA],
        vol.Optional("contributions", default=[]): [AREA_SCHEMA],
    }
)


class _Forecast:
    """Shared, cached Open-Meteo forecast, including the past two days."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._hours: list[ForecastHour] = []
        self._fetched: datetime | None = None
        self.bias_of = lambda: (None, 0)  # set by the House: (bias, hours)
        self._archive_failed = False

    @property
    def fetched(self) -> datetime | None:
        """When the forecast now held was fetched (the outdoor record's ``at``)."""
        return self._fetched

    async def hours(self) -> list[ForecastHour]:
        now = datetime.now(UTC)
        if self._fetched is None or now - self._fetched > FORECAST_MAX_AGE:
            try:
                self._hours = await self._hass.async_add_executor_job(
                    partial(
                        fetch_forecast,
                        self._hass.config.latitude,
                        self._hass.config.longitude,
                        3,
                        past_days=2,
                    )
                )
                self._fetched = now
                await self._archive(now)
            except Exception:  # noqa: BLE001 - keep the last forecast on any failure
                _LOGGER.warning("Forecast fetch failed; using the last one if any")
        return self._hours

    async def _archive(self, now: datetime) -> None:
        """Keep the forecast just fetched (the future hours only)."""
        bias, hours = self.bias_of()
        record = outdoor_record(
            at=now,
            model="best_match",
            lat=self._hass.config.latitude,
            lon=self._hass.config.longitude,
            bias=bias if hours else None,
            bias_hours=hours,
            hours=[
                (
                    h.time,
                    h.temperature,
                    h.light.direct_normal,
                    h.light.diffuse,
                    h.light.cloud_cover,
                )
                for h in self._hours
                if h.time > now
            ],
        )
        try:
            await get_store(self._hass).append(record)
            self._archive_failed = False
        except Exception:
            if not self._archive_failed:
                _LOGGER.warning("Could not archive the outdoor forecast", exc_info=True)
            self._archive_failed = True


def _light_at(hass, zone: dict, by_end: dict, moment: datetime) -> tuple:
    """(forecast hour, light on the zone's surfaces) for a moment, or (None, 0)."""
    hour_end = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    slot = by_end.get(hour_end)
    if slot is None:
        return None, 0.0
    return slot, _surface_light(
        hass.config.latitude, hass.config.longitude, zone, slot.light, moment
    )


def _surface_light(lat: float, lon: float, zone: dict, reading, moment) -> float:
    """Light (W/m2) on the zone's windows and roofs from an hour's irradiance."""
    az = solar_azimuth_degrees(moment, lat, lon)
    el = solar_elevation_degrees(moment, lat, lon)
    return light_on_planes(reading, az, el, zone["window_planes"])


def _ground_at(zone: dict, moment: datetime) -> float:
    """The ground wave for a zone at a moment (local time)."""
    return ground_temperature(
        dt_util.as_local(moment),
        zone["ground_mean"],
        zone["ground_swing"],
        zone["ground_coldest_day"],
    )


def _wall_light(lat: float, lon: float, zone: dict, reading, moment) -> float:
    """Light (W/m2) on the zone's sunlit solid walls (before the wall's lag)."""
    if not has_walls(zone):
        return 0.0
    az = solar_azimuth_degrees(moment, lat, lon)
    el = solar_elevation_degrees(moment, lat, lon)
    return light_on_planes(reading, az, el, zone["wall_planes"])


def _learn_blower(rows, item, end, watts):
    """Blower powers (kW) from whole-house power and the thermostats (blocking)."""
    scale = 0.001 if watts else 1.0
    power = [(t, v * scale) for t, v in power_series(rows[item["power_entity"]])]
    heat, fan, high = [], [], []
    for climate_id in item["climate_entities"]:
        states = rows[climate_id]
        heat += runs_from_states(states, end, {"heating"}, "hvac_action")
        fan += stage_runs(states, end, "fan")
        high += stage_runs(states, end, HIGH)
    steps = edge_steps(
        power, merge_runs(heat, 0.0), merge_runs(fan, 0.0), merge_runs(high, 0.0)
    )
    return blower_kw(steps)


@dataclass
class _Series:
    """A zone's binned history (built in the executor)."""

    room: list
    outdoor: list
    light: list[float]
    raw_wall: list[float]
    heating: list[float]
    ground: list | None
    setpoint: list
    cooling: list[float] = field(default_factory=list)
    fan: list[float] = field(default_factory=list)


@dataclass
class _Learned:
    """What one learning pass found for a zone (built in the executor).

    ``neighbours`` are the zones coupled into the fit (empty: fitted alone).
    """

    fit: NoHeatFit | None
    problem: str | None
    wall_tau: float
    data: ZoneData
    neighbours: tuple[str, ...] = ()
    history: ZoneHistory | None = None


def _zone_series(zone, rows, irradiance, lat, lon, start, end) -> _Series:
    """Bin a zone's recorded history (blocking)."""
    width = LEARN_BIN
    bins = int((end - start) / width)
    climate = rows[zone["climate_entity"]]
    room_id = zone.get("room_entity")
    room = _numbers(rows[room_id]) if room_id else temperature_series(climate)
    outdoor = _numbers(rows[zone["outdoor_entity"]])
    heating = bin_fraction(
        runs_from_states(climate, end, {"heating"}, "hvac_action"), start, bins, width
    )
    cooling = bin_fraction(
        runs_from_states(climate, end, {"cooling"}, "hvac_action"), start, bins, width
    )
    fan = bin_fraction(
        runs_from_states(climate, end, {"fan"}, "hvac_action"), start, bins, width
    )
    by_end = {r.time: r for r in irradiance}
    light, raw_wall = [], []
    for i in range(bins):
        mid = start + (i + 0.5) * width
        reading = by_end.get(
            mid.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        )
        light.append(
            0.0 if reading is None else _surface_light(lat, lon, zone, reading, mid)
        )
        raw_wall.append(
            0.0 if reading is None else _wall_light(lat, lon, zone, reading, mid)
        )
    ground = None
    if zone["below_ground"]:
        if zone.get("ground_entity"):
            ground = bin_held(_numbers(rows[zone["ground_entity"]]), start, bins, width)
        else:  # no sensor: the annual ground wave
            ground = [_ground_at(zone, start + (i + 0.5) * width) for i in range(bins)]
    return _Series(
        bin_held(room, start, bins, width),
        bin_held(outdoor, start, bins, width),
        light,
        raw_wall,
        heating,
        ground,
        bin_held(heat_setpoints(climate), start, bins, width),
        cooling,
        fan,
    )


def _fit_one(
    zone: dict,
    s: _Series,
    hours: float,
    neighbour: list | None = None,
    other: list[float] | None = None,
    other_cool: list[float] | None = None,
    fan: list[float] | None = None,
) -> _Learned:
    """Hour-long block rates, then the multi-step refinement if physical; with
    sunlit walls the wall lag is chosen from ``WALL_TAUS`` by the fit."""
    args = (s.room, s.outdoor, s.light, s.heating, hours)
    extra = {
        "ground": s.ground,
        "block": LEARN_BLOCK,
        "neighbour": neighbour,
        "other": other,
        "cooling": s.cooling,
        "other_cool": other_cool,
        "fan": fan,
    }
    if has_walls(zone):
        fit, tau = fit_with_wall_lag(*args, s.raw_wall, WALL_TAUS, **extra)
        wall = lag(s.raw_wall, hours, tau)
    else:
        fit = fit_no_heat(*args, **extra)
        tau, wall = WALL_TAU_HOURS, None
    data = ZoneData(
        *args,
        wall,
        s.ground,
        neighbour,
        other,
        s.setpoint,
        cooling=s.cooling,
        other_cool=other_cool,
        fan=fan,
    )
    reason = problem(fit)
    if reason is None:
        fit = refine_multistep(fit, data)
    return _Learned(fit, reason, tau, data)


def _error_3h(found: _Learned) -> float | None:
    if found.problem is not None:
        return None
    s = skill(model_of(found.fit), found.data, (12,)).get(12)
    return None if s is None else s.model


def _mean_of(values: list) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _effective_fan(key: str, series: dict[str, _Series]) -> list[float]:
    """The fan share per bin for one zone, as the panel counts it: the fan runs
    for the zone alone, so it is cut where any other zone is calling for heat or
    cool (the zone's own calls do not cut it)."""
    own = series[key].fan
    others = [s for k, s in series.items() if k != key]
    out = []
    for i, fan in enumerate(own):
        busy = max((min(1.0, o.heating[i] + o.cooling[i]) for o in others), default=0.0)
        out.append(fan * (1.0 - busy))
    return out


def _fit_house(zones, rows, irradiance, lat, lon, start, end) -> dict[str, _Learned]:
    """Fit every zone of a house from recorded history (blocking).

    Each zone is fitted alone and, if it has neighbours (``hub_neighbours``),
    with the neighbour terms ``n`` and ``x``; the coupled fit is kept if it is
    physical and forecasts idle history 3 hours ahead better, or if the fit
    alone is not physical (the zones of an open house that do not heat).
    """
    hours = LEARN_BIN.total_seconds() / 3600.0
    series = {
        z["climate_entity"]: _zone_series(z, rows, irradiance, lat, lon, start, end)
        for z in zones
    }
    near_of = hub_neighbours(
        {k: sum(s.heating) * hours for k, s in series.items()},
        {z["climate_entity"]: z.get("neighbours", []) for z in zones},
    )
    origins_every = 48  # D's fading time is fitted from a forecast every 12 hours
    # The returns are not zoned: the fan runs for the whole house when any zone
    # runs it alone, so the house fan is the largest zone fan share per bin.
    fans = {k: _effective_fan(k, series) for k in series}
    count = len(next(iter(series.values())).room)
    house_fan = [max(f[i] for f in fans.values()) for i in range(count)]
    out = {}
    for zone in zones:
        key = zone["climate_entity"]
        s = series[key]
        alone_fan = fans[key]
        found = _fit_one(zone, s, hours, fan=house_fan)
        near = near_of.get(key, ())
        if near and zone["model"].get("a") is None:
            neighbour = [
                _mean_of([series[k].room[i] for k in near]) for i in range(count)
            ]
            other = [sum(series[k].heating[i] for k in near) for i in range(count)]
            other_cool = [sum(series[k].cooling[i] for k in near) for i in range(count)]
            coupled = _fit_one(zone, s, hours, neighbour, other, other_cool, house_fan)
            alone_err, coupled_err = _error_3h(found), _error_3h(coupled)
            if coupled_err is not None and (
                alone_err is None or coupled_err < alone_err
            ):
                found = replace(coupled, neighbours=near)
        origins = list(range(FORECAST_STEPS, len(s.room), origins_every))
        tau = fit_offset_tau(s.room, origins, FORECAST_STEPS, hours)
        thermostat = cool_thermostat(s.room, s.cooling)
        wall = found.data.wall or [0.0] * len(s.room)
        found.history = ZoneHistory(
            start,
            s.room,
            s.outdoor,
            s.light,
            wall,
            s.setpoint,
            tau,
            cool=s.cooling,
            fan=alone_fan,
            cool_setpoint=None if thermostat is None else thermostat[0],
            cool_band=0.5 if thermostat is None else thermostat[1],
        )
        out[key] = found
    return out


def _measure(model: ZoneModel, data: ZoneData, learn_h: bool, deadband: float):
    """Heating and cooling rates (heating if wanted), furnace lag and skill of a
    model (blocking)."""
    h = fit_heat_rate(model, data) if learn_h else model.h
    model = replace(model, h=h)
    cool = fit_cool_rate(model, data)
    model = replace(model, e=cool)
    furnace_lag, _ = fit_furnace_lag(model, data, deadband)
    return h, cool, furnace_lag, skill(model, data, (4, 12))


def _target_wave(zone: dict) -> TargetWave | None:
    if zone.get("target_mean") is None:
        return None
    return TargetWave(
        zone["target_mean"],
        zone["target_swing"],
        zone["target_peak_hour"],
        zone["target_band"],
    )


def _local_hour(moment: datetime) -> float:
    local = dt_util.as_local(moment)
    return local.hour + local.minute / 60.0


@dataclass
class _Ahead:
    """One zone's part of the house forecast, for its sensors."""

    ahead: ZoneAhead
    outdoor: list[float]
    plan: list[float]
    shift: float
    neighbour: tuple[list[float], list[float]] | None


class House:
    """The zones of one setup: learned together and forecast together.

    Every ``LEARN_EVERY`` it reads the recorder once for all zones, fits each
    one (alone, and with its neighbours' temperature and calls) and hands each
    ``ZoneBrain`` its result. ``ahead`` runs the day-ahead forecast of all the
    zones at once (``house.forecast_house``), cached for a few minutes since
    every zone's sensors ask for it.
    """

    def __init__(self, hass, forecast: _Forecast, outdoor_entity: str):
        self.hass = hass
        self.forecast = forecast
        forecast.bias_of = self._bias
        self.outdoor_entity = outdoor_entity
        self.brains: dict[str, ZoneBrain] = {}
        self._users = 0
        self._stop_timer = None
        self._ahead: dict[str, _Ahead] = {}
        self._ahead_at: datetime | None = None

    def _bias(self) -> tuple[float | None, int]:
        """The outdoor forecast's bias at the last learning pass."""
        for brain in self.brains.values():
            return brain.bias, brain.bias_hours
        return None, 0

    def start(self):
        """One more user; the first starts the learning. Returns the stopper."""
        self._users += 1
        if self._users == 1:
            self._stop_timer = async_track_time_interval(
                self.hass, self.learn, LEARN_EVERY
            )
            self.hass.async_create_task(self.learn())

        def _stop():
            self._users -= 1
            if self._users == 0 and self._stop_timer is not None:
                self._stop_timer()
                self._stop_timer = None

        return _stop

    async def learn(self, _now=None) -> None:
        """One learning pass for every zone; failures keep what was there."""
        zones = [
            {**b.zone, "outdoor_entity": self.outdoor_entity}
            for b in self.brains.values()
        ]
        ids = {self.outdoor_entity}
        for zone in zones:
            ids.add(zone["climate_entity"])
            if zone.get("room_entity"):
                ids.add(zone["room_entity"])
            if zone["below_ground"] and zone.get("ground_entity"):
                ids.add(zone["ground_entity"])
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=LEARN_DAYS)
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        try:
            rows = await _recorded(self.hass, sorted(ids), start, end)
            irradiance = await self.hass.async_add_executor_job(
                fetch_irradiance, lat, lon, LEARN_DAYS + 2
            )
            found = await self.hass.async_add_executor_job(
                partial(_fit_house, zones, rows, irradiance, lat, lon, start, end)
            )
        except Exception:  # noqa: BLE001 - try again at the next interval
            _LOGGER.warning("Could not learn the zone models")
            return
        self._ahead_at = None
        # zones are added one by one at startup: skip any added during the fit
        for key, brain in list(self.brains.items()):
            if key in found:
                await brain.apply(found[key], rows, end)

    async def ahead(self, key: str, now: datetime) -> _Ahead | None:
        """The zone's part of the house forecast from about ``now``."""
        if self._ahead_at is None or now - self._ahead_at > timedelta(minutes=5):
            self._ahead = await self._forecast_all(now)
            self._ahead_at = now
        return self._ahead.get(key)

    async def _forecast_all(self, now: datetime) -> dict[str, _Ahead]:
        outdoor_now = _state_number(self.hass, self.outdoor_entity)
        keys, zones, inputs = [], [], []
        # a snapshot: zones are added one by one at startup, during the awaits
        for key, brain in list(self.brains.items()):
            attrs, room, setpoint = _zone_now(self.hass, brain.zone)
            if attrs is None or room is None:
                continue
            got = await brain.inputs(now, FORECAST_STEPS, outdoor_now)
            if not got[0]:
                continue
            model = brain.model
            if model is not None and setpoint is None:
                model = replace(model, h=0.0)  # thermostat off: no heat
            keys.append(key)
            inputs.append((got, attrs, room, setpoint, model))
        if not keys:
            return {}
        steps = min(len(got[0]) for got, *_ in inputs)
        step = timedelta(hours=STEP_HOURS)
        slots = [slot_of(dt_util.as_local(now + k * step)) for k in range(steps)]
        index = {k: i for i, k in enumerate(keys)}
        plans = []
        for key, (got, attrs, room, setpoint, model) in zip(keys, inputs, strict=True):
            brain = self.brains[key]
            plan = setpoints_ahead(
                room if setpoint is None else setpoint,
                None if setpoint is None else brain.schedule,
                slots,
            )
            if setpoint is None:
                plan = [-50.0] * steps
            plans.append(plan)
            outdoor, light, wall, _ = got
            near = brain.neighbours if model is not None else ()
            zones.append(
                ZoneNow(
                    model,
                    room,
                    attrs.get("hvac_action") == "heating",
                    plan,
                    brain.zone["deadband"],
                    light[:steps],
                    wall[:steps],
                    brain.ground_now(now),
                    tuple(index[k] for k in near if k in index),
                    brain.history,
                )
            )
        outdoor = inputs[0][0][0][:steps]
        aheads = await self.hass.async_add_executor_job(
            forecast_house, now, zones, outdoor, STEP_HOURS
        )
        return {
            key: _Ahead(
                aheads[i],
                outdoor,
                plans[i],
                inputs[i][0][3],
                neighbour_inputs(aheads, zones[i].neighbours),
            )
            for i, key in enumerate(keys)
        }


class ZoneBrain:
    """A zone's learned model, shared by its shadow, forecast and target sensors.

    Its ``House`` refits the no-heat model every ``LEARN_EVERY`` (unless one
    was given), alone or with the neighbour terms; the brain then learns the
    heating rate ``h`` (unless given) and the furnace's delivery lag, measures
    the model against holding the temperature, grades it, and measures the
    outdoor forecast's bias against the outdoor sensor. The Zones tab reads
    zones from ``hass.data[DOMAIN]["zones"]``; each zone's fitted cooling rate
    is published for Manual J (``panel.publish_fitted``) whenever it changes.
    """

    def __init__(self, hass, house: House, zone: dict):
        self.hass = hass
        self.house = house
        self.forecast = house.forecast
        self.outdoor_entity = house.outdoor_entity
        self.zone = zone
        self.key = zone["climate_entity"]
        self.wave = _target_wave(zone)
        model = zone["model"]
        self.given = "a" in model and "c" in model
        self.given_h = model.get("h")
        self.model: ZoneModel | None = (
            ZoneModel(
                model["a"],
                model["c"],
                model.get("g", 0.0),
                model.get("b", 0.0),
                model.get("w", 0.0),
                model.get("h") or 0.0,
            )
            if self.given
            else None
        )
        self.note = "given" if self.given else "waiting to learn"
        self.quality: dict = {"grade": "none"}
        self.wall_tau = WALL_TAU_HOURS
        self.bias = 0.0
        self.bias_hours = 0
        self.schedule: list[float | None] | None = None
        self.neighbours: tuple[str, ...] = ()
        self.history: ZoneHistory | None = None
        self.entities: dict[str, str] = {}
        self._listeners: list = []
        self._users = 0
        self._stop_house = None
        house.brains[self.key] = self
        house._ahead_at = None  # the cached forecast lacks this zone

    def listen(self, callback):
        """Call ``callback()`` after each learning pass; returns the remover."""
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def start(self):
        """Use the brain from one more sensor; returns the function that stops it.

        The first sensor added starts the house's learning (so it runs as long
        as any zone's sensor is enabled); the last one removed stops it.
        """
        zones = self.hass.data.setdefault(DOMAIN, {}).setdefault("zones", {})
        self._users += 1
        if self._users == 1:
            self._stop_house = self.house.start()
            zones[self.key] = self
            publish_fitted(self.hass)

        def _stop():
            self._users -= 1
            if self._users == 0:
                if self._stop_house is not None:
                    self._stop_house()
                    self._stop_house = None
                if zones.get(self.key) is self:
                    zones.pop(self.key)
                    publish_fitted(self.hass)

        return _stop

    def names(self, keys: tuple[str, ...]) -> list[str]:
        """Zone names for climate entity ids."""
        brains = self.house.brains
        return [brains[k].zone["name"] if k in brains else k for k in keys]

    async def apply(self, found: _Learned, rows: dict, end: datetime) -> None:
        """Take one learning pass's result."""
        self.wall_tau = found.wall_tau
        self.history = found.history
        fit = found.fit
        if not self.given:
            if found.problem is not None:
                self.model = None
                self.neighbours = ()
                self.note = f"not used: {found.problem}"
            else:
                self.model = model_of(fit)
                self.neighbours = found.neighbours
                with_ = (
                    f", with {', '.join(self.names(found.neighbours))}"
                    if found.neighbours
                    else ""
                )
                self.note = (
                    f"learned ({fit.method}{with_}) from {fit.bins} idle bins "
                    "of 15 minutes"
                )
        if self.model is not None:
            if self.given_h is not None:
                self.model = replace(self.model, h=self.given_h)
            h, cool, furnace_lag, skills = await self.hass.async_add_executor_job(
                _measure,
                self.model,
                found.data,
                self.given_h is None,
                self.zone["deadband"],
            )
            self.model = replace(self.model, h=h, e=cool, lag=furnace_lag)
        else:
            skills = {}
        await self._update_bias(rows[self.outdoor_entity], end)
        self.schedule = schedule_by_slot(
            [(dt_util.as_local(t), v) for t, v in heat_setpoints(rows[self.key])],
            dt_util.as_local(datetime.now(UTC)),
        )
        self.quality = self._quality(fit, found, skills)
        publish_fitted(self.hass)
        for callback in list(self._listeners):
            await callback()

    async def _update_bias(self, outdoor_rows: list[dict], end: datetime) -> None:
        hours = await self.forecast.hours()
        if not hours:
            return
        self.bias, self.bias_hours = outdoor_bias(
            _numbers(outdoor_rows),
            [(h.time, h.temperature) for h in hours],
            end - timedelta(hours=BIAS_HOURS),
            end,
        )

    def _quality(self, fit, found: _Learned, skills: dict) -> dict:
        used = fit if not self.given else None
        out = {
            "grade": grade(used if used else _given_fit(self.model), skills),
            "model": self.note,
            "problem": None if self.given else found.problem,
            "fitted_at": datetime.now(UTC).isoformat(),
            "wall_tau": self.wall_tau if has_walls(self.zone) else None,
            "h": round(self.model.h, 3) if self.model else None,
            "furnace_lag": self.model.lag if self.model else None,
            "neighbours": self.names(self.neighbours),
            "offset_tau": None if self.history is None else self.history.tau,
            "outdoor_bias": round(self.bias, 2),
            "bias_hours": self.bias_hours,
        }
        if fit is not None:
            out |= {
                "method": fit.method,
                "bins": fit.bins,
                "r2": round(fit.r2, 3),
                "fitted": {
                    k: round(getattr(fit, k), 6)
                    for k in ("a", "c", "g", "w", "b", "n", "x")
                },
            }
        for lead, label in ((4, "1h"), (12, "3h")):
            if lead in skills:
                out[f"error_{label}"] = round(skills[lead].model, 3)
                out[f"hold_{label}"] = round(skills[lead].hold, 3)
                out[f"starts_{label}"] = skills[lead].n
        return out

    def ground_now(self, now: datetime) -> float:
        if self.model is None or not self.model.b:
            return 0.0
        ground = _state_number(self.hass, self.zone.get("ground_entity"))
        return _ground_at(self.zone, now) if ground is None else ground

    async def inputs(self, now: datetime, steps: int, outdoor_now: float | None):
        """Outdoor (bias-corrected), light and lagged wall light per step ahead."""
        hours = await self.forecast.hours()
        by_end = {h.time: h for h in hours}
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        outdoor, light, wall = [], [], []
        for k in range(steps):
            moment = now + timedelta(hours=STEP_HOURS * (k + 0.5))
            slot, lit = _light_at(self.hass, self.zone, by_end, moment)
            if slot is None:
                break
            light.append(lit)
            wall.append(_wall_light(lat, lon, self.zone, slot.light, moment))
            outdoor.append(slot.temperature)
        outdoor, shift = apply_bias(outdoor, self.bias, self.bias_hours)
        if outdoor and outdoor_now is not None:
            outdoor[0] = outdoor_now
        return outdoor, light, lag(wall, STEP_HOURS, self.wall_tau), shift


def _given_fit(model: ZoneModel | None) -> NoHeatFit | None:
    """A typed-in model as a fit, for grading (counts as plenty of data)."""
    if model is None:
        return None
    return NoHeatFit(model.a, model.c, model.g, 10_000, model.b, model.w)


def _state_number(hass, entity_id: str | None) -> float | None:
    state = hass.states.get(entity_id) if entity_id else None
    try:
        return float(state.state)
    except (AttributeError, TypeError, ValueError):
        return None


def _zone_now(hass, zone: dict):
    """(climate attributes, room temperature, heating setpoint) now."""
    climate = hass.states.get(zone["climate_entity"])
    if climate is None:
        return None, None, None
    attrs = climate.attributes
    room = _state_number(hass, zone.get("room_entity"))
    if room is None:
        room = attrs.get("current_temperature")
    setpoint = attrs.get("temperature")
    if setpoint is None:
        setpoint = attrs.get("target_temp_low")
    return (
        attrs,
        None if room is None else float(room),
        None if setpoint is None else float(setpoint),
    )


def _zone_entities(hass, house: House, zone: dict) -> list:
    brain = ZoneBrain(hass, house, zone)
    return [
        ShadowSensor(brain),
        ZoneForecastSensor(brain),
        TargetSensor(brain),
    ]


async def async_setup_entry(hass, entry, async_add_entities):
    """Create the sensors of each sub-entry of the config entry."""
    forecast_cache = _Forecast(hass)
    outdoor = entry.data.get("outdoor_entity")
    house = dict(entry.data)
    zones = House(hass, forecast_cache, outdoor)
    rooms = structure_rooms(hass.data.get(STRUCTURE_DOMAIN))
    for subentry in entry.subentries.values():
        kind = subentry.subentry_type
        try:
            if kind == ZONE:
                item = ZONE_SCHEMA(
                    _with_room(rooms, with_house(dict(subentry.data), house))
                )
                entities = _zone_entities(hass, zones, item)
            elif kind == CALL_STATS:
                item = CALL_SCHEMA(_with_room(rooms, dict(subentry.data), sun=False))
                entities = [CallStatsSensor(hass, item)]
            elif kind == ENERGY:
                entities = [
                    FurnaceEnergySensor(hass, ENERGY_SCHEMA(dict(subentry.data)))
                ]
            elif kind == CONTRIBUTION:
                item = CONTRIBUTION_SCHEMA(
                    _with_room(
                        rooms, with_house(dict(subentry.data), house), ground=False
                    )
                )
                entities = [ContributionSensor(hass, forecast_cache, outdoor, item)]
            else:
                continue
        except vol.Invalid as err:
            _LOGGER.error("Skipping %r: %s", subentry.title, err)
            continue
        if kind in (ZONE, CONTRIBUTION) and not outdoor:
            _LOGGER.error(
                "Skipping %r: set the outdoor sensor in the integration's "
                "Reconfigure first",
                subentry.title,
            )
            continue
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)
    await _register_tab(hass)


def _with_room(rooms: dict, data: dict, ground: bool = True, sun: bool = True) -> dict:
    """A sub-entry's settings, filled in from House Structure for its area.

    Args:
        rooms: House Structure's rooms by area id.
        data: The sub-entry's settings.
        ground: Whether this kind takes ``below_ground``.
        sun: Whether this kind takes the room's sun and room sensor; heating-call
            statistics only take the thermostat, and work without an area.

    Raises:
        vol.Invalid: A zone or contribution without a room in House Structure.
    """
    area = data.get("area_id")
    if not sun:
        if not area or area not in rooms:
            return data
        filled = from_structure({}, rooms[area], ground=False)
        out = dict(data)
        if not out.get("climate_entity") and filled.get("climate_entity"):
            out["climate_entity"] = filled["climate_entity"]
        return out
    if not area:
        raise vol.Invalid("choose its room (area) on Reconfigure")
    if area not in rooms:
        raise vol.Invalid(f"House Structure has no room in area {area!r}")
    choices = sensor_choices(data, rooms[area])
    if choices:
        _LOGGER.warning(
            "%s: area %r has several temperature sensors (%s) and none is chosen "
            "in the area's settings, so the thermostat's own reading is used. "
            "Choose one in the area's settings, or pick a room temperature "
            "sensor on the zone",
            data.get("name"),
            area,
            ", ".join(choices),
        )
    return from_structure(data, rooms[area], ground=ground)


def _yaml_items(rooms: dict, items: list, schema, ground: bool) -> list[dict]:
    """YAML zones or contributions, filled in from House Structure and checked."""
    out = []
    for data in items:
        try:
            out.append(schema(_with_room(rooms, dict(data), ground=ground)))
        except vol.Invalid as err:
            _LOGGER.error("Skipping %r: %s", data.get("name"), err)
    return out


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Create the sensors configured in YAML."""
    forecast_cache = _Forecast(hass)
    outdoor = config.get("outdoor_entity")
    if (config["zones"] or config["contributions"]) and not outdoor:
        _LOGGER.error("outdoor_entity is needed for zones and contributions")
        return
    entities: list[SensorEntity] = []
    house = House(hass, forecast_cache, outdoor)
    rooms = structure_rooms(hass.data.get(STRUCTURE_DOMAIN))
    for zone in _yaml_items(rooms, config["zones"], ZONE_SCHEMA, ground=True):
        entities += _zone_entities(hass, house, zone)
    entities += [CallStatsSensor(hass, item) for item in config["call_stats"]]
    entities += [FurnaceEnergySensor(hass, item) for item in config["energy"]]
    entities += [
        ContributionSensor(hass, forecast_cache, outdoor, item)
        for item in _yaml_items(
            rooms, config["contributions"], CONTRIBUTION_SCHEMA, ground=False
        )
    ]
    async_add_entities(entities)
    await _register_tab(hass)


async def _register_tab(hass) -> None:
    """Add the Zones tab and the Heat flow overlay; the sensors work without them."""
    try:
        await async_register_tab(hass)
    except Exception:  # never block the sensors on the tab
        _LOGGER.exception("Could not add the Zones tab")


class ShadowSensor(SensorEntity):
    """``skip`` or ``heat`` for a call starting now in one zone.

    It also runs the zone's learning and shows how good the model is: the
    ``grade`` (none, low, medium, high, as ClimateAdvisor's calibration label),
    the fit method, bins, R2, the forecast error at 1 and 3 hours against holding
    the temperature, the heating rate ``h``, the wall lag and the outdoor
    forecast's bias.
    """

    _attr_should_poll = False

    def __init__(self, brain: ZoneBrain):
        self._brain = brain
        self._hass = brain.hass
        zone = brain.zone
        self._zone = zone
        self._attr_name = f"Shadow {zone['name']}"
        self._attr_unique_id = f"home_thermal_lab_shadow_{zone['climate_entity']}"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        self._brain.entities["shadow"] = self.entity_id
        self.async_on_remove(self._brain.listen(self._learned))
        self.async_on_remove(self._brain.start())
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        self.async_on_remove(
            async_track_state_change_event(
                self._hass, [self._zone["climate_entity"]], self._refresh
            )
        )
        await self._refresh(None)

    async def _learned(self) -> None:
        await self._refresh(None)

    async def _refresh(self, _event) -> None:
        brain = self._brain
        zone = self._zone
        attrs, room, setpoint = _zone_now(self._hass, zone)
        if attrs is None:
            return
        model = brain.model
        outdoor_now = _state_number(self._hass, brain.outdoor_entity)
        now = datetime.now(UTC)
        quality = dict(brain.quality)
        if model is None or room is None or setpoint is None or outdoor_now is None:
            self._attr_extra_state_attributes = {"model": brain.note, **quality}
            self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return
        outdoor, light, wall, _ = await brain.inputs(now, LOOK_AHEAD_STEPS, outdoor_now)
        if not outdoor:
            self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return
        ground = brain.ground_now(now)
        neighbour = other = None
        if model.n or model.x:
            ahead = await brain.house.ahead(brain.key, now)
            if ahead is None or ahead.neighbour is None:
                self._attr_native_value = "unknown"
                self.async_write_ha_state()
                return
            neighbour, other = ahead.neighbour
            steps = min(len(outdoor), len(neighbour))
            outdoor, light, wall = outdoor[:steps], light[:steps], wall[:steps]
        decision = decide(
            room,
            setpoint,
            outdoor,
            light,
            model,
            STEP_HOURS,
            zone["tolerance"],
            zone["max_dip"],
            wall,
            ground,
            neighbour,
            other,
        )
        self._attr_native_value = "skip" if decision.skip else "heat"
        self._attr_extra_state_attributes = {
            "room": room,
            "setpoint": setpoint,
            "outdoor": outdoor_now,
            "lowest_vs_setpoint": round(decision.lowest, 2),
            "shortfall_degree_hours": round(decision.shortfall, 2),
            "look_ahead_steps": decision.steps,
            "thermostat_action": attrs.get("hvac_action"),
            "equipment_running": attrs.get("equipment_running"),
            "decided_at": now.isoformat(),
            **quality,
            "model": brain.note,
            "a": round(model.a, 5),
            "c": round(model.c, 5),
            "g": round(model.g, 7),
        }
        if has_walls(zone):
            self._attr_extra_state_attributes["w"] = round(model.w, 7)
        if zone["below_ground"]:
            self._attr_extra_state_attributes["b"] = round(model.b, 5)
            self._attr_extra_state_attributes["ground"] = round(ground, 2)
        self.async_write_ha_state()


class ZoneForecastSensor(SensorEntity):
    """The zone's room temperature forecast 3 hours ahead (hypothesis 16).

    Every forecast is also written to the forecast archive (``archive.py``),
    which the recorder's purge does not touch. The state is the forecast for 3
    hours on, ``predicted_1h`` and ``predicted_6h`` the other leads, ``start``
    the room temperature when it was made. Every ``LEARN_EVERY`` the sensor
    scores its own last ``SCORE_DAYS`` days against the room (``error_1h`` and
    so on, and ``error_d_1h`` for the profile forecast D), from the archive and,
    for the part of the window before it began, the recorder (``scored_from``).
    ``points`` (not recorded) is the full day ahead for the charts.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _unrecorded_attributes = frozenset({"points"})

    def __init__(self, brain: ZoneBrain):
        self._brain = brain
        self._hass = brain.hass
        zone = brain.zone
        self._attr_name = f"Forecast {zone['name']}"
        self._attr_unique_id = f"home_thermal_lab_forecast_{zone['climate_entity']}"
        self._scores: dict = {}
        self._path_hour: datetime | None = None  # the last hour with a path
        self._archive_errors = 0
        self._archive_warned: datetime | None = None

    async def async_added_to_hass(self) -> None:
        self._brain.entities["forecast"] = self.entity_id
        self.async_on_remove(self._brain.listen(self._learned))
        self.async_on_remove(self._brain.start())
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        await self._refresh(None)

    async def _learned(self) -> None:
        await self._score()
        await self._refresh(None)

    async def _score(self) -> None:
        """Score this sensor's recorded forecasts against the room."""
        zone = self._brain.zone
        room_id = zone.get("room_entity") or zone["climate_entity"]
        end = datetime.now(UTC)
        start = end - timedelta(days=SCORE_DAYS)
        store = get_store(self._hass)
        try:
            records = await store.read("room", start, end, self.entity_id)
        except Exception:
            _LOGGER.warning("Could not read the forecast archive", exc_info=True)
            records = []
        first = min((datetime.fromisoformat(r["at"]) for r in records), default=None)
        # the recorder covers the part of the window before the archive began
        need_recorder = first is None or first - start > timedelta(hours=1)
        ids = [room_id, *([self.entity_id] if need_recorder else [])]
        try:
            rows = await _recorded(self._hass, ids, start, end)
        except Exception:  # noqa: BLE001 - keep the last scores
            _LOGGER.warning("Could not score the forecast for %s", zone["name"])
            return
        actual = (
            _numbers(rows[room_id])
            if zone.get("room_entity")
            else temperature_series(rows[room_id])
        )
        issued = issued_from_archive(records)
        if need_recorder:
            old = [
                f
                for f in issued_from_rows(rows[self.entity_id])
                if first is None or f.issued < first
            ]
            issued = old + issued
        source = "recorder" if not records else "both" if need_recorder else "archive"
        found = score(issued, actual, end)
        found_d = score(issued_from_archive(records, "leads_d"), actual, end)

        def entry(s) -> dict:
            return {
                "mae": round(s.mae, 3),
                "bias": round(s.bias, 3),
                "rmse": round(s.rmse, 3),
                "change_mae": None if s.change_mae is None else round(s.change_mae, 3),
                "n": s.n,
            }

        self._scores = {
            "scored_from": source,
            **{f"error_{lead:g}h": entry(s) for lead, s in found.items()},
            **{f"error_d_{lead:g}h": entry(s) for lead, s in found_d.items()},
        }

    async def _archive(self, record: dict) -> None:
        """Append to the archive; a failure is counted and warned once an hour."""
        try:
            await get_store(self._hass).append(record)
        except Exception:
            self._archive_errors += 1
            at = datetime.fromisoformat(record["at"])
            if self._archive_warned is None or at - self._archive_warned >= timedelta(
                hours=1
            ):
                self._archive_warned = at
                _LOGGER.warning(
                    "Could not archive the forecast for %s",
                    self.entity_id,
                    exc_info=True,
                )

    async def _refresh(self, _now) -> None:
        brain = self._brain
        zone = brain.zone
        attrs, room, setpoint = _zone_now(self._hass, zone)
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        got = None
        if attrs is not None and room is not None:
            got = await brain.house.ahead(brain.key, now)
        if got is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "model": brain.note,
                **self._scores,
                "archive_errors": self._archive_errors,
            }
            self.async_write_ha_state()
            return
        # A zone without a learned model is "held": its headline value stays
        # hidden, but its outdoor and setpoint forecast still goes to the chart.
        held = brain.model is None and got.ahead.method == "held"
        ahead: ZoneAhead = got.ahead
        # the house forecast may be a few minutes old: start it from the room now
        temps = [room, *ahead.temps[1:]]
        step = timedelta(hours=STEP_HOURS)
        times = [dt_util.as_local(now + k * step) for k in range(len(temps))]
        outlook = outlook_from_path(
            now,
            temps,
            ahead.duty,
            got.outdoor,
            got.plan,
            [t.hour + t.minute / 60.0 for t in times],
            STEP_HOURS,
            brain.wave,
            zone["tolerance"],
        )
        leads = {lead: outlook.at(lead) for lead in LEADS}
        self._attr_native_value = (
            None if held or leads[3] is None else round(leads[3], 2)
        )
        names = {
            "start": room,
            "setpoint": setpoint,
            "method": ahead.method,
            "neighbours": brain.names(brain.neighbours),
        }
        common = shared(**names, leads=leads)
        self._attr_extra_state_attributes = {
            "issued": now.isoformat(),
            **common,
            "heating_rate": None if brain.model is None else round(brain.model.h, 3),
            "cooling_rate": None if brain.model is None else round(brain.model.e, 3),
            "cooling_bleed": None if brain.model is None else round(brain.model.y, 3),
            "fan_pull": None if brain.model is None else round(brain.model.f, 3),
            "outdoor_correction": round(got.shift, 2),
            **self._scores,
            "archive_errors": self._archive_errors,
            "points": outlook_points(
                outlook,
                every=2,
                extra={"cool": ahead.cool, "fan": ahead.fan},
                # the planned setpoint (the program, when one is recorded); a
                # thermostat that is off has none to plot
                setpoints=None if setpoint is None else got.plan,
            ),
        }
        # the archive: the full path only on the first issue of each UTC hour
        hour = now.replace(minute=0)
        first_of_hour = self._path_hour != hour
        self._path_hour = hour
        archived = {k: None for k in leads} if held else leads
        model = brain.model
        record = room_record(
            at=now,
            zone=self.entity_id,
            name=zone["name"],
            shared_fields=common,
            fallback="no usable fit" if ahead.method == "profile" else None,
            outdoor_at=self._brain.forecast.fetched,
            outdoor_shift=got.shift,
            fit_at=brain.quality.get("fitted_at"),
            params={
                k: None if model is None else getattr(model, k, None)
                for k in PARAM_NAMES
            },
            leads=archived,
            leads_d=d_leads(room, ahead.d, LEADS, STEP_HOURS),
            path=path_points(temps, 15) if first_of_hour else None,
        )
        self.hass.async_create_task(self._archive(record))
        self.async_write_ha_state()


class TargetSensor(SensorEntity):
    """The zone's target temperature now (the centre of the target band).

    With ``target_mean`` set, the target wave (``target.py``); otherwise the
    thermostat's setpoint. ``lower`` and ``upper`` are the band, recorded so a
    chart can draw the band's history.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:sine-wave"

    def __init__(self, brain: ZoneBrain):
        self._brain = brain
        self._hass = brain.hass
        zone = brain.zone
        self._attr_name = f"Target {zone['name']}"
        self._attr_unique_id = f"home_thermal_lab_target_{zone['climate_entity']}"

    async def async_added_to_hass(self) -> None:
        self._brain.entities["target"] = self.entity_id
        self.async_on_remove(self._brain.start())
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        self.async_on_remove(
            async_track_state_change_event(
                self._hass, [self._brain.zone["climate_entity"]], self._refresh
            )
        )
        await self._refresh(None)

    async def _refresh(self, _event) -> None:
        zone = self._brain.zone
        _, _, setpoint = _zone_now(self._hass, zone)
        wave = self._brain.wave
        if wave is None and setpoint is None:
            self._attr_native_value = None
            self.async_write_ha_state()
            return
        band = band_at(
            wave, setpoint or 0.0, zone["tolerance"], _local_hour(datetime.now(UTC))
        )
        self._attr_native_value = round(band.centre, 2)
        self._attr_extra_state_attributes = {
            "lower": round(band.lower, 2),
            "upper": round(band.upper, 2),
            "source": "wave" if wave else "setpoint",
        }
        if wave:
            self._attr_extra_state_attributes |= {
                "mean": wave.mean,
                "swing": wave.swing,
                "peak_hour": wave.peak_hour,
                "band": wave.band,
            }
        self.async_write_ha_state()


class CallStatsSensor(SensorEntity):
    """Heating calls of one zone over the last few days, with their statistics."""

    _attr_should_poll = False
    _attr_native_unit_of_measurement = "calls"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fire"
    _unrecorded_attributes = frozenset({"low", "stepped"})

    def __init__(self, hass, item: dict):
        self._hass = hass
        self._item = item
        self._attr_name = item["name"]
        self._attr_unique_id = f"home_thermal_lab_calls_{item['climate_entity']}"
        self._last_action = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, timedelta(minutes=30))
        )
        self.async_on_remove(
            async_track_state_change_event(
                self._hass, [self._item["climate_entity"]], self._on_change
            )
        )
        await self._refresh(None)

    async def _on_change(self, event) -> None:
        new = event.data.get("new_state")
        action = new.attributes.get("hvac_action") if new else None
        ended = self._last_action == "heating" and action != "heating"
        self._last_action = action
        if ended:
            await self._refresh(None)

    async def _refresh(self, _now) -> None:
        entity = self._item["climate_entity"]
        end = datetime.now(UTC)
        start = end - timedelta(days=self._item["days"])
        rows = (await _recorded(self._hass, [entity], start, end))[entity]
        calls = calls_from_states(rows, end)
        items = responses(calls, temperature_series(rows), self._item["after_minutes"])
        summary = summarise(items)
        self._attr_native_value = len(calls)
        self._attr_extra_state_attributes = {
            "days": self._item["days"],
            "low": summary["low"],
            "stepped": summary["stepped"],
            "calls_per_day": round(len(calls) / self._item["days"], 1),
            "hours_heating": round(sum(c.minutes for c in calls) / 60.0, 1),
            "updated": end.isoformat(),
        }
        self.async_write_ha_state()


class FurnaceEnergySensor(RestoreSensor):
    """Modelled energy (kWh) of the furnace from the thermostats' state."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, hass, item: dict):
        self._hass = hass
        self._item = item
        self._attr_name = item["name"]
        slug = item["name"].lower().replace(" ", "_")
        self._attr_unique_id = f"home_thermal_lab_energy_{slug}"
        self._meter = Meter(dict(item["kw"]))
        self._learned: dict[str, float] = {}
        self._edges: dict[str, int] = {}

    def _mode(self) -> str:
        zones = []
        for e in self._item["climate_entities"]:
            state = self._hass.states.get(e)
            if state is not None:
                zones.append(dict(state.attributes))
        return furnace_mode(zones)

    async def _learn(self, _now=None) -> None:
        """Learn the blower powers from the whole-house power sensor."""
        item = self._item
        power_id = item["power_entity"]
        ids = [power_id, *item["climate_entities"]]
        end = datetime.now(UTC)
        start = end - timedelta(days=item["learn_days"])
        try:
            rows = await _recorded(self._hass, ids, start, end)
            unit = self._hass.states.get(power_id)
            watts = unit is not None and unit.attributes.get("unit_of_measurement") in (
                "W",
                "w",
            )
            learned, edges = await self._hass.async_add_executor_job(
                partial(_learn_blower, rows, item, end, watts)
            )
        except Exception:  # noqa: BLE001 - try again at the next interval
            _LOGGER.warning("Could not learn the powers for %s", item["name"])
            return
        self._learned, self._edges = learned, edges
        self._meter.advance(datetime.now(UTC))
        self._meter.kw.update(learned)
        self._publish()

    async def async_added_to_hass(self) -> None:
        if self._item.get("power_entity"):
            self.async_on_remove(
                async_track_time_interval(self._hass, self._learn, LEARN_EVERY)
            )
            self._hass.async_create_task(self._learn())
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            with contextlib.suppress(TypeError, ValueError):
                self._meter.total = float(last.native_value)
        self._meter.advance(datetime.now(UTC), self._mode())
        self.async_on_remove(
            async_track_time_interval(self._hass, self._tick, timedelta(minutes=1))
        )
        self.async_on_remove(
            async_track_state_change_event(
                self._hass, list(self._item["climate_entities"]), self._tick
            )
        )
        self._publish()

    def _publish(self) -> None:
        self._attr_native_value = round(self._meter.total, 4)
        self._attr_extra_state_attributes = {
            "mode": self._meter.mode,
            "kw": self._meter.kw.get(self._meter.mode, 0.0),
        }
        if self._item.get("power_entity"):
            self._attr_extra_state_attributes |= {
                "learned_kw": {k: round(v, 4) for k, v in self._learned.items()},
                "edges": self._edges,
            }
        self.async_write_ha_state()

    async def _tick(self, _event) -> None:
        self._meter.advance(datetime.now(UTC), self._mode())
        self._publish()


class ContributionSensor(SensorEntity):
    """A zone's temperature now; ``points`` split the past and future by effect."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"points"})

    def __init__(self, hass, forecast_cache: _Forecast, outdoor: str, item: dict):
        self._hass = hass
        self._forecast = forecast_cache
        self._outdoor = outdoor
        self._item = item
        self._attr_name = f"Contributions {item['name']}"
        self._attr_unique_id = f"home_thermal_lab_contrib_{item['climate_entity']}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        await self._refresh(None)

    def _raw_wall(self, item: dict, by_end: dict, moment: datetime) -> float:
        """Light on the room's sunlit solid walls at a moment, or 0."""
        hour_end = moment.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
        slot = by_end.get(hour_end)
        if slot is None:
            return 0.0
        return _wall_light(
            self._hass.config.latitude,
            self._hass.config.longitude,
            item,
            slot.light,
            moment,
        )

    async def _refresh(self, _now) -> None:
        item = self._item
        step = timedelta(hours=STEP_HOURS)
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        back = int(item["hours_back"] / STEP_HOURS)
        ahead = int(item["hours_ahead"] / STEP_HOURS)
        start = now - back * step
        room_entity = item.get("room_entity")
        wanted = [
            item["climate_entity"],
            self._outdoor,
            *item["other_climate_entities"],
        ]
        wanted += item["plug_entities"]
        wanted += list(item["lights"])
        if room_entity:
            wanted.append(room_entity)
        rows = await _recorded(self._hass, wanted, start - timedelta(hours=1), now)
        hours = await self._forecast.hours()
        by_end = {h.time: h for h in hours}

        climate_rows = rows[item["climate_entity"]]
        if room_entity:
            room_series = _numbers(rows[room_entity])
        else:
            room_series = temperature_series(climate_rows)
        times = [start + i * step for i in range(back + 1)]
        temps = held_values(room_series, times)
        outdoor = held_values(
            _numbers(rows[self._outdoor]), [t + step / 2 for t in times]
        )

        def heat(rows_: list[dict]) -> list[float]:
            runs = runs_from_states(rows_, now, {"heating"}, "hvac_action")
            return on_fraction([(r.start, r.end) for r in runs], start, back, step)

        own = heat(climate_rows)
        others = [heat(rows[e]) for e in item["other_climate_entities"]]
        other = [max((o[i] for o in others), default=0.0) for i in range(back)]
        plugs = [
            held_values(_numbers(rows[e]), [t + step / 2 for t in times[:-1]])
            for e in item["plug_entities"]
        ]
        lamps = [
            held_values(dimmer_kw(rows[e], watts), [t + step / 2 for t in times[:-1]])
            for e, watts in item["lights"].items()
        ]
        steps: list[Inputs | None] = []
        raw_wall: list[float] = []
        for i in range(back):
            if outdoor[i] is None:
                steps.append(None)
                raw_wall.append(0.0)
                continue
            moment = times[i] + step / 2
            _, lit = _light_at(self._hass, item, by_end, moment)
            raw_wall.append(self._raw_wall(item, by_end, moment))
            kw = sum((p[i] or 0.0) for p in plugs) / 1000.0
            kw += sum((lamp[i] or 0.0) for lamp in lamps)
            steps.append(Inputs(outdoor[i], lit, own[i], other[i], kw))
        walls = lag(raw_wall, STEP_HOURS, WALL_TAU_HOURS)
        steps = [
            None if s is None else replace(s, wall_light=walls[i])
            for i, s in enumerate(steps)
        ]
        model = ZoneTerms(**item["terms"])
        past = split_history(model, temps, steps, STEP_HOURS)

        current = temps[-1]
        if current is None:
            self._attr_native_value = None
            self.async_write_ha_state()
            return
        climate = self._hass.states.get(item["climate_entity"])
        attrs = climate.attributes if climate else {}
        setpoint = attrs.get("temperature") or attrs.get("target_temp_low")
        future_steps = []
        future_wall = []
        outdoor_now = outdoor[-1]
        for k in range(ahead):
            moment = now + (k + 0.5) * step
            slot, lit = _light_at(self._hass, item, by_end, moment)
            if slot is None:
                break
            future_wall.append(self._raw_wall(item, by_end, moment))
            temp_out = (
                outdoor_now if k == 0 and outdoor_now is not None else slot.temperature
            )
            future_steps.append(Inputs(temp_out, lit))
        future_walls = lag(
            future_wall, STEP_HOURS, WALL_TAU_HOURS, walls[-1] if walls else None
        )
        future_steps = [
            replace(s, wall_light=future_walls[k]) for k, s in enumerate(future_steps)
        ]
        temps_ahead, future = forecast(
            model,
            current,
            future_steps,
            STEP_HOURS,
            None if setpoint is None else float(setpoint),
            item["deadband"],
            attrs.get("hvac_action") == "heating",
        )
        self._attr_native_value = round(current, 2)
        self._attr_extra_state_attributes = {
            "baseline": round(current, 2),
            "setpoint": setpoint,
            "terms": [
                "outdoor",
                "house",
                "sun",
                "walls",
                "furnace",
                "crossover",
                "appliances",
                "unexplained",
            ],
            "points": chart_points(
                now, step, past, temps, future, temps_ahead, every=2
            ),
            "updated": now.isoformat(),
        }
        self.async_write_ha_state()
