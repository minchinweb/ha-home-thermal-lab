"""Shadow-controller sensors (hypothesis 17). Nothing here switches anything.

One sensor per zone. Every ``scan_interval`` and whenever the thermostat's
``hvac_action`` changes, it asks the question of ``shadow.decide``: if a heat
call started now, could the furnace stay off because the room is forecast to
stay within the comfort band? The state is ``skip`` or ``heat`` (``unknown``
when an input is missing). Attributes hold the numbers behind it and what the
thermostat is actually doing, so the home-assistant history of each sensor is
the shadow-mode log to compare against the thermostat later.

Configuration (``configuration.yaml``)::

    sensor:
      - platform: house_thermal_lab
        outdoor_entity: sensor.edmonton_temperature
        zones:
          - name: Z4 office
            climate_entity: climate.z4
            room_entity: sensor.z4_temperature
            model: {a: 0.011, c: 0.02, g: 0.0003}   # from scripts/shadow_control.py
            walls: [E]
            roofs: []
            rotation: 10.4
            shade_below: 18     # degrees; beam blocked for sun between 120-210 deg
            tolerance: 0.5
            max_dip: 0.5

This module needs Home Assistant and is not covered by the unit tests; the
decision logic it calls (``shadow``, ``forecast``, ``irradiance``) is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
import voluptuous as vol

from .forecast import ForecastHour, fetch_forecast
from .irradiance import light_on_surfaces
from .shadow import ZoneModel, decide
from .solar import solar_azimuth_degrees, solar_elevation_degrees

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)
STEP_HOURS = 0.25
LOOK_AHEAD_STEPS = 12
FORECAST_MAX_AGE = timedelta(hours=1)

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
        vol.Optional("walls", default=[]): [vol.In(["N", "E", "S", "W"])],
        vol.Optional("roofs", default=[]): [
            vol.ExactSequence([vol.In(["N", "E", "S", "W"]), vol.Coerce(float)])
        ],
        vol.Optional("rotation", default=0.0): vol.Coerce(float),
        vol.Optional("shade_below", default=0.0): vol.Coerce(float),
        vol.Optional("tolerance", default=0.5): vol.Coerce(float),
        vol.Optional("max_dip", default=0.5): vol.Coerce(float),
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("outdoor_entity"): cv.entity_id,
        vol.Required("zones"): [ZONE_SCHEMA],
    }
)


class _Forecast:
    """Shared, cached Open-Meteo forecast."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._hours: list[ForecastHour] = []
        self._fetched: datetime | None = None

    async def hours(self) -> list[ForecastHour]:
        now = datetime.now(UTC)
        if self._fetched is None or now - self._fetched > FORECAST_MAX_AGE:
            try:
                self._hours = await self._hass.async_add_executor_job(
                    fetch_forecast,
                    self._hass.config.latitude,
                    self._hass.config.longitude,
                )
                self._fetched = now
            except Exception:  # noqa: BLE001 - keep the last forecast on any failure
                _LOGGER.warning("Forecast fetch failed; using the last one if any")
        return self._hours


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Create one shadow sensor per configured zone."""
    forecast = _Forecast(hass)
    entities = [
        ShadowSensor(hass, forecast, config["outdoor_entity"], zone)
        for zone in config["zones"]
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
        lat, lon = self._hass.config.latitude, self._hass.config.longitude
        by_end = {h.time: h for h in hours}
        outdoor, light = [], []
        for k in range(LOOK_AHEAD_STEPS):
            moment = now + timedelta(hours=STEP_HOURS * (k + 0.5))
            hour_end = moment.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
            slot = by_end.get(hour_end)
            if slot is None:
                break
            az = solar_azimuth_degrees(moment, lat, lon)
            el = solar_elevation_degrees(moment, lat, lon)
            shaded = 120.0 <= az < 210.0 and el < zone["shade_below"]
            light.append(
                light_on_surfaces(
                    slot.light,
                    az,
                    el,
                    zone["walls"],
                    [(f, t) for f, t in zone["roofs"]],
                    zone["rotation"],
                    shaded,
                )
            )
            outdoor.append(outdoor_now if k == 0 else slot.temperature)
        if not outdoor:
            self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return
        model = ZoneModel(**zone["model"])
        decision = decide(
            float(room),
            float(setpoint),
            outdoor,
            light,
            model,
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
