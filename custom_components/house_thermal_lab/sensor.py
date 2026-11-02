"""House Thermal Lab sensors. Nothing here switches anything.

Four kinds, all configured under one ``sensor:`` platform entry (see the README
for a full example)::

    sensor:
      - platform: house_thermal_lab
        outdoor_entity: sensor.edmonton_temperature
        zones: [...]          # shadow controller, one sensor per zone (17)
        call_stats: [...]     # heating-call statistics per zone (05, 13)
        energy: [...]         # modelled furnace energy, for the energy dashboard
        contributions: [...]  # what each effect added to a zone (chart)

* **Shadow** (``zones``): ``skip`` or ``heat`` for a call starting now; the
  history of the sensor is the shadow-mode log (hypothesis 17).
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
from datetime import UTC, datetime, timedelta
from functools import partial
import logging

from homeassistant.components.recorder import get_instance, history
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
import voluptuous as vol

from .calls import calls_from_states, responses, summarise, temperature_series
from .contributions import (
    Inputs,
    ZoneTerms,
    chart_points,
    forecast,
    held_values,
    on_fraction,
)
from .contributions import (
    history as split_history,
)
from .energy import MODES, Meter, furnace_mode
from .forecast import ForecastHour, fetch_forecast
from .hvac import runs_from_states
from .irradiance import light_on_surfaces
from .shadow import ZoneModel, decide
from .solar import solar_azimuth_degrees, solar_elevation_degrees

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)
STEP_HOURS = 0.25
LOOK_AHEAD_STEPS = 12
FORECAST_MAX_AGE = timedelta(hours=1)
FACES = ["N", "E", "S", "W"]

SUN_SCHEMA = {
    vol.Optional("walls", default=[]): [vol.In(FACES)],
    vol.Optional("roofs", default=[]): [
        vol.ExactSequence([vol.In(FACES), vol.Coerce(float)])
    ],
    vol.Optional("rotation", default=0.0): vol.Coerce(float),
    vol.Optional("shade_below", default=0.0): vol.Coerce(float),
}

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("room_entity"): cv.entity_id,
        vol.Required("model"): vol.Schema(
            {
                vol.Required("a"): vol.Coerce(float),
                vol.Required("c"): vol.Coerce(float),
                vol.Optional("g", default=0.0): vol.Coerce(float),
            }
        ),
        vol.Optional("tolerance", default=0.5): vol.Coerce(float),
        vol.Optional("max_dip", default=0.5): vol.Coerce(float),
        **SUN_SCHEMA,
    }
)

CALL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("days", default=7): vol.All(vol.Coerce(int), vol.Range(1, 60)),
        vol.Optional("after_minutes", default=90): vol.Coerce(float),
    }
)

ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entities"): cv.entity_ids,
        vol.Required("kw"): vol.Schema({vol.In(MODES): vol.Coerce(float)}),
    }
)

CONTRIBUTION_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("room_entity"): cv.entity_id,
        vol.Optional("other_climate_entities", default=[]): cv.entity_ids,
        vol.Optional("plug_entities", default=[]): cv.entity_ids,
        vol.Required("terms"): vol.Schema(
            {
                vol.Required("a"): vol.Coerce(float),
                vol.Required("c"): vol.Coerce(float),
                vol.Optional("g", default=0.0): vol.Coerce(float),
                vol.Optional("h", default=0.0): vol.Coerce(float),
                vol.Optional("x", default=0.0): vol.Coerce(float),
                vol.Optional("p", default=0.0): vol.Coerce(float),
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

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional("outdoor_entity"): cv.entity_id,
        vol.Optional("zones", default=[]): [ZONE_SCHEMA],
        vol.Optional("call_stats", default=[]): [CALL_SCHEMA],
        vol.Optional("energy", default=[]): [ENERGY_SCHEMA],
        vol.Optional("contributions", default=[]): [CONTRIBUTION_SCHEMA],
    }
)


class _Forecast:
    """Shared, cached Open-Meteo forecast, including the past two days."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._hours: list[ForecastHour] = []
        self._fetched: datetime | None = None

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
            except Exception:  # noqa: BLE001 - keep the last forecast on any failure
                _LOGGER.warning("Forecast fetch failed; using the last one if any")
        return self._hours


def _light_at(hass, zone: dict, by_end: dict, moment: datetime) -> tuple:
    """(forecast hour, light on the zone's surfaces) for a moment, or (None, 0)."""
    hour_end = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    slot = by_end.get(hour_end)
    if slot is None:
        return None, 0.0
    lat, lon = hass.config.latitude, hass.config.longitude
    az = solar_azimuth_degrees(moment, lat, lon)
    el = solar_elevation_degrees(moment, lat, lon)
    shaded = 120.0 <= az < 210.0 and el < zone["shade_below"]
    light = light_on_surfaces(
        slot.light,
        az,
        el,
        zone["walls"],
        [(f, t) for f, t in zone["roofs"]],
        zone["rotation"],
        shaded,
    )
    return slot, light


def _as_dict(state) -> dict:
    return {
        "state": state.state,
        "last_changed": state.last_changed.isoformat(),
        "last_updated": state.last_updated.isoformat(),
        "attributes": dict(state.attributes),
    }


async def _recorded(hass, entity_ids: list[str], start: datetime, end: datetime):
    """Every recorded state (attribute changes too) per entity, as dicts."""
    found = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    return {e: [_as_dict(s) for s in found.get(e, [])] for e in entity_ids}


def _numbers(rows: list[dict]) -> list[tuple[datetime, float]]:
    out = []
    for r in rows:
        try:
            value = float(r["state"])
        except (TypeError, ValueError):
            continue
        out.append((datetime.fromisoformat(r["last_changed"]).astimezone(UTC), value))
    return sorted(out)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Create the configured sensors."""
    forecast_cache = _Forecast(hass)
    outdoor = config.get("outdoor_entity")
    if (config["zones"] or config["contributions"]) and not outdoor:
        _LOGGER.error("outdoor_entity is needed for zones and contributions")
        return
    entities: list[SensorEntity] = [
        ShadowSensor(hass, forecast_cache, outdoor, zone) for zone in config["zones"]
    ]
    entities += [CallStatsSensor(hass, item) for item in config["call_stats"]]
    entities += [FurnaceEnergySensor(hass, item) for item in config["energy"]]
    entities += [
        ContributionSensor(hass, forecast_cache, outdoor, item)
        for item in config["contributions"]
    ]
    async_add_entities(entities)


class ShadowSensor(SensorEntity):
    """``skip`` or ``heat`` for a call starting now in one zone."""

    _attr_should_poll = False

    def __init__(self, hass, forecast: _Forecast, outdoor_entity: str, zone: dict):
        self._hass = hass
        self._forecast = forecast
        self._outdoor_entity = outdoor_entity
        self._zone = zone
        self._attr_name = f"Shadow {zone['name']}"
        self._attr_unique_id = f"house_thermal_lab_shadow_{zone['climate_entity']}"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        self.async_on_remove(
            async_track_state_change_event(
                self._hass, [self._zone["climate_entity"]], self._refresh
            )
        )
        await self._refresh(None)

    def _number(self, entity_id: str | None) -> float | None:
        state = self._hass.states.get(entity_id) if entity_id else None
        try:
            return float(state.state)
        except (AttributeError, TypeError, ValueError):
            return None

    async def _refresh(self, _event) -> None:
        zone = self._zone
        climate = self._hass.states.get(zone["climate_entity"])
        if climate is None:
            return
        attrs = climate.attributes
        room = self._number(zone.get("room_entity"))
        if room is None:
            room = attrs.get("current_temperature")
        setpoint = attrs.get("temperature")
        if setpoint is None:
            setpoint = attrs.get("target_temp_low")
        outdoor_now = self._number(self._outdoor_entity)
        hours = await self._forecast.hours()
        if room is None or setpoint is None or outdoor_now is None or not hours:
            self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return

        now = datetime.now(UTC)
        by_end = {h.time: h for h in hours}
        outdoor, light = [], []
        for k in range(LOOK_AHEAD_STEPS):
            moment = now + timedelta(hours=STEP_HOURS * (k + 0.5))
            slot, lit = _light_at(self._hass, zone, by_end, moment)
            if slot is None:
                break
            light.append(lit)
            outdoor.append(outdoor_now if k == 0 else slot.temperature)
        if not outdoor:
            self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return
        decision = decide(
            float(room),
            float(setpoint),
            outdoor,
            light,
            ZoneModel(**zone["model"]),
            STEP_HOURS,
            zone["tolerance"],
            zone["max_dip"],
        )
        self._attr_native_value = "skip" if decision.skip else "heat"
        self._attr_extra_state_attributes = {
            "room": float(room),
            "setpoint": float(setpoint),
            "outdoor": outdoor_now,
            "lowest_vs_setpoint": round(decision.lowest, 2),
            "shortfall_degree_hours": round(decision.shortfall, 2),
            "look_ahead_steps": decision.steps,
            "thermostat_action": attrs.get("hvac_action"),
            "equipment_running": attrs.get("equipment_running"),
            "decided_at": now.isoformat(),
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
        self._attr_unique_id = f"house_thermal_lab_calls_{item['climate_entity']}"
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
        self._attr_unique_id = f"house_thermal_lab_energy_{slug}"
        self._meter = Meter(dict(item["kw"]))

    def _mode(self) -> str:
        zones = []
        for e in self._item["climate_entities"]:
            state = self._hass.states.get(e)
            if state is not None:
                zones.append(dict(state.attributes))
        return furnace_mode(zones)

    async def async_added_to_hass(self) -> None:
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
        self._attr_unique_id = f"house_thermal_lab_contrib_{item['climate_entity']}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self._hass, self._refresh, SCAN_INTERVAL)
        )
        await self._refresh(None)

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
        steps: list[Inputs | None] = []
        for i in range(back):
            if outdoor[i] is None:
                steps.append(None)
                continue
            _, lit = _light_at(self._hass, item, by_end, times[i] + step / 2)
            kw = sum((p[i] or 0.0) for p in plugs) / 1000.0
            steps.append(Inputs(outdoor[i], lit, own[i], other[i], kw))
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
        outdoor_now = outdoor[-1]
        for k in range(ahead):
            moment = now + (k + 0.5) * step
            slot, lit = _light_at(self._hass, item, by_end, moment)
            if slot is None:
                break
            temp_out = (
                outdoor_now if k == 0 and outdoor_now is not None else slot.temperature
            )
            future_steps.append(Inputs(temp_out, lit))
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
