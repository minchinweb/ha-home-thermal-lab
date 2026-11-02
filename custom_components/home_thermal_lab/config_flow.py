"""Set up Home Thermal Lab from the web interface.

The integration entry holds the outdoor temperature sensor. Each sensor is a
sub-entry of it, with one type per kind (zone, call statistics, energy,
contribution); add them from the integration's page. Every form maps onto the
same settings as the YAML configuration (see ``sensor.py``); roofs and dimmed
lights are typed as short text (see ``options.py``).

This module needs Home Assistant (2025.3 or later, for sub-entries) and is not
covered by the unit tests; the parsing it calls is.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.helpers import selector
import voluptuous as vol

from . import CALL_STATS, CONTRIBUTION, DOMAIN, ENERGY, ZONE
from .options import (
    FACES,
    KW_MODES,
    FieldError,
    format_lights,
    format_roofs,
    kw_table,
    parse_lights,
    parse_roofs,
)

_TEXT = selector.TextSelector()
_NUMBER = selector.NumberSelector(
    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
_CLIMATES = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_SENSORS = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", multiple=True)
)
_FACES = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(FACES),
        multiple=True,
        mode=selector.SelectSelectorMode.LIST,
    )
)


def _sun_fields() -> dict:
    """Window, roof and shading fields shared by zones and contributions."""
    return {
        vol.Optional("walls"): _FACES,
        vol.Optional("roofs"): _TEXT,
        vol.Optional("rotation"): _NUMBER,
        vol.Optional("shade_below"): _NUMBER,
    }


def _zone_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
            vol.Optional("room_entity"): _SENSOR,
            vol.Required("a"): _NUMBER,
            vol.Required("c"): _NUMBER,
            vol.Optional("g"): _NUMBER,
            vol.Optional("tolerance"): _NUMBER,
            vol.Optional("max_dip"): _NUMBER,
            **_sun_fields(),
        }
    )


def _call_stats_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
            vol.Optional("days"): _NUMBER,
            vol.Optional("after_minutes"): _NUMBER,
        }
    )


def _energy_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entities"): _CLIMATES,
            **{vol.Optional(mode): _NUMBER for mode in KW_MODES},
        }
    )


def _contribution_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
            vol.Optional("room_entity"): _SENSOR,
            vol.Optional("other_climate_entities"): _CLIMATES,
            vol.Optional("plug_entities"): _SENSORS,
            vol.Optional("lights"): _TEXT,
            vol.Required("a"): _NUMBER,
            vol.Required("c"): _NUMBER,
            vol.Optional("g"): _NUMBER,
            vol.Optional("h"): _NUMBER,
            vol.Optional("x"): _NUMBER,
            vol.Optional("p"): _NUMBER,
            vol.Optional("hours_back"): _NUMBER,
            vol.Optional("hours_ahead"): _NUMBER,
            vol.Optional("deadband"): _NUMBER,
            **_sun_fields(),
        }
    )


def _clean(form: dict, keys: tuple[str, ...]) -> dict:
    """The filled-in fields among ``keys`` (a cleared optional number is dropped)."""
    return {k: form[k] for k in keys if form.get(k) not in (None, "")}


def _sun_from_form(form: dict) -> dict:
    out = _clean(form, ("rotation", "shade_below"))
    if form.get("walls"):
        out["walls"] = list(form["walls"])
    if form.get("roofs"):
        out["roofs"] = parse_roofs(form["roofs"])
    return out


def _sun_to_form(data: dict) -> dict:
    out = {k: data[k] for k in ("walls", "rotation", "shade_below") if k in data}
    if data.get("roofs"):
        out["roofs"] = format_roofs(data["roofs"])
    return out


def _zone_from_form(form: dict) -> dict:
    return {
        "name": form["name"],
        "climate_entity": form["climate_entity"],
        "model": {"a": form["a"], "c": form["c"], **_clean(form, ("g",))},
        **_clean(form, ("room_entity", "tolerance", "max_dip")),
        **_sun_from_form(form),
    }


def _zone_to_form(data: dict) -> dict:
    flat = {k: v for k, v in data.items() if k != "model"}
    return {**flat, **data.get("model", {}), **_sun_to_form(data)}


def _call_stats_from_form(form: dict) -> dict:
    data = {"name": form["name"], "climate_entity": form["climate_entity"]}
    if form.get("days") is not None:
        data["days"] = int(form["days"])
    return {**data, **_clean(form, ("after_minutes",))}


def _energy_from_form(form: dict) -> dict:
    return {
        "name": form["name"],
        "climate_entities": list(form["climate_entities"]),
        "kw": kw_table(form),
    }


def _energy_to_form(data: dict) -> dict:
    flat = {k: v for k, v in data.items() if k != "kw"}
    return {**flat, **data.get("kw", {})}


def _contribution_from_form(form: dict) -> dict:
    data = {
        "name": form["name"],
        "climate_entity": form["climate_entity"],
        "terms": {
            "a": form["a"],
            "c": form["c"],
            **_clean(form, ("g", "h", "x", "p")),
        },
        **_clean(form, ("room_entity", "deadband")),
        **_sun_from_form(form),
    }
    for key in ("other_climate_entities", "plug_entities"):
        if form.get(key):
            data[key] = list(form[key])
    if form.get("lights"):
        data["lights"] = parse_lights(form["lights"])
    for key in ("hours_back", "hours_ahead"):
        if form.get(key) is not None:
            data[key] = int(form[key])
    return data


def _contribution_to_form(data: dict) -> dict:
    skip = {"terms", "lights", "roofs"}
    flat = {k: v for k, v in data.items() if k not in skip}
    out = {**flat, **data.get("terms", {}), **_sun_to_form(data)}
    if data.get("lights"):
        out["lights"] = format_lights(data["lights"])
    return out


def _plain(data: dict) -> dict:
    return dict(data)


# type -> (form schema, form -> stored data, stored data -> form defaults)
_KINDS = {
    ZONE: (_zone_schema, _zone_from_form, _zone_to_form),
    CALL_STATS: (_call_stats_schema, _call_stats_from_form, _plain),
    ENERGY: (_energy_schema, _energy_from_form, _energy_to_form),
    CONTRIBUTION: (
        _contribution_schema,
        _contribution_from_form,
        _contribution_to_form,
    ),
}


class HomeThermalLabConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single integration entry, with the outdoor temperature sensor."""

    VERSION = 1

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """The sensors that can be added to the entry."""
        return {
            ZONE: ZoneSubentryFlow,
            CALL_STATS: CallStatsSubentryFlow,
            ENERGY: EnergySubentryFlow,
            CONTRIBUTION: ContributionSubentryFlow,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the outdoor temperature sensor."""
        if user_input is not None:
            return self.async_create_entry(title="Home Thermal Lab", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional("outdoor_entity"): _SENSOR}),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the outdoor temperature sensor."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional("outdoor_entity"): _SENSOR}), entry.data
            ),
        )


class _SensorSubentryFlow(ConfigSubentryFlow):
    """Add or edit one sensor; the subclass names its kind."""

    kind: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a sensor."""
        return await self._step("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a sensor."""
        subentry = self._get_reconfigure_subentry()
        return await self._step(
            "reconfigure", user_input, _KINDS[self.kind][2](dict(subentry.data))
        )

    async def _step(
        self, step_id: str, user_input: dict[str, Any] | None, current: dict
    ) -> SubentryFlowResult:
        schema_for, from_form, _ = _KINDS[self.kind]
        schema = schema_for()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = from_form(user_input)
            except FieldError as err:
                errors[err.field] = f"invalid_{err.field}"
            else:
                if step_id == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=data["name"],
                        data=data,
                    )
                return self.async_create_entry(title=data["name"], data=data)
            current = user_input
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
        )


class ZoneSubentryFlow(_SensorSubentryFlow):
    """A shadow-controller zone (hypothesis 17)."""

    kind = ZONE


class CallStatsSubentryFlow(_SensorSubentryFlow):
    """Heating-call statistics for one zone (hypotheses 05 and 13)."""

    kind = CALL_STATS


class EnergySubentryFlow(_SensorSubentryFlow):
    """Modelled furnace energy for the energy dashboard."""

    kind = ENERGY


class ContributionSubentryFlow(_SensorSubentryFlow):
    """What moved one zone's temperature (the contribution chart)."""

    kind = CONTRIBUTION
