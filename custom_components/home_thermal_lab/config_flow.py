"""Set up Home Thermal Lab from the web interface.

The integration entry holds the outdoor temperature sensor. Each sensor is a
sub-entry of it, with one type per kind (zone, call statistics, energy,
contribution); add them from the integration's page. Every form maps onto the
same settings as the YAML configuration (see ``sensor.py``); dimmed lights are
typed as short text (see ``options.py``). A zone or contribution is a room
(area) in House Structure, which gives it its windows, roofs, walls and
below-ground setting.

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
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.helpers import selector
import voluptuous as vol

from . import CALL_STATS, CONTRIBUTION, DOMAIN, ENERGY, ZONE
from .migrate import MINOR_VERSION as ENTRY_MINOR_VERSION
from .options import (
    GROUND_KEYS,
    KW_MODES,
    POWER_UNITS,
    FieldError,
    format_lights,
    kw_table,
    parse_lights,
)

# the target wave (target.py); a zone without a mean targets its setpoint
TARGET_KEYS = ("target_mean", "target_swing", "target_peak_hour", "target_band")

_TEXT = selector.TextSelector()
_NUMBER = selector.NumberSelector(
    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
_AREA = selector.AreaSelector()
_CLIMATES = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_TEMPERATURE = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
_POWER = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_POWERS = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power", multiple=True)
)
_UNITS = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(POWER_UNITS), mode=selector.SelectSelectorMode.DROPDOWN
    )
)


def _house_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("outdoor_entity"): _TEMPERATURE,
            vol.Optional("ground_mean"): _NUMBER,
            vol.Optional("ground_swing"): _NUMBER,
            vol.Optional("ground_coldest_day"): _NUMBER,
        }
    )


def _house_from_form(form: dict) -> dict:
    data = {}
    if form.get("outdoor_entity"):
        data["outdoor_entity"] = form["outdoor_entity"]
    data.update(_clean(form, GROUND_KEYS))
    return data


def _house_to_form(data: dict) -> dict:
    keys = ("outdoor_entity", *GROUND_KEYS)
    return {k: data[k] for k in keys if k in data}


def _zone_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("area_id"): _AREA,
            vol.Optional("climate_entity"): _CLIMATE,
            vol.Optional("room_entity"): _TEMPERATURE,
            vol.Optional("a"): _NUMBER,
            vol.Optional("c"): _NUMBER,
            vol.Optional("g"): _NUMBER,
            vol.Optional("h"): _NUMBER,
            vol.Optional("tolerance"): _NUMBER,
            vol.Optional("max_dip"): _NUMBER,
            vol.Optional("deadband"): _NUMBER,
            vol.Optional("neighbours"): _CLIMATES,
            vol.Optional("ground_entity"): _TEMPERATURE,
            **{vol.Optional(k): _NUMBER for k in TARGET_KEYS},
        }
    )


def _call_stats_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Optional("area_id"): _AREA,
            vol.Optional("climate_entity"): _CLIMATE,
            vol.Optional("days"): _NUMBER,
            vol.Optional("after_minutes"): _NUMBER,
        }
    )


def _energy_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entities"): _CLIMATES,
            vol.Optional("power_entity"): _POWER,
            vol.Optional("learn_days"): _NUMBER,
            vol.Optional("power_unit", default="kW"): _UNITS,
            **{vol.Optional(mode): _NUMBER for mode in KW_MODES},
        }
    )


def _contribution_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("area_id"): _AREA,
            vol.Optional("climate_entity"): _CLIMATE,
            vol.Optional("room_entity"): _TEMPERATURE,
            vol.Optional("other_climate_entities"): _CLIMATES,
            vol.Optional("plug_entities"): _POWERS,
            vol.Optional("lights"): _TEXT,
            vol.Required("a"): _NUMBER,
            vol.Required("c"): _NUMBER,
            vol.Optional("g"): _NUMBER,
            vol.Optional("w"): _NUMBER,
            vol.Optional("h"): _NUMBER,
            vol.Optional("x"): _NUMBER,
            vol.Optional("p"): _NUMBER,
            vol.Optional("hours_back"): _NUMBER,
            vol.Optional("hours_ahead"): _NUMBER,
            vol.Optional("deadband"): _NUMBER,
        }
    )


def _clean(form: dict, keys: tuple[str, ...]) -> dict:
    """The filled-in fields among ``keys`` (a cleared optional number is dropped)."""
    return {k: form[k] for k in keys if form.get(k) not in (None, "")}


def _place(form: dict) -> dict:
    """Heating-call statistics' area and thermostat; one of them is needed.

    With an area, House Structure fills in the thermostat (from the room's
    register) when the sensor is set up.
    """
    if not form.get("area_id") and not form.get("climate_entity"):
        raise FieldError("climate_entity", "choose a room (area) or a thermostat")
    return _clean(form, ("area_id", "climate_entity"))


def _room(form: dict) -> dict:
    """The room (area), and its thermostat and room sensor if they were picked.

    House Structure fills in the thermostat (from the room's register) and the
    room sensor when they are left empty, and always the sun and walls.
    """
    if not form.get("area_id"):
        raise FieldError("area_id", "choose the room (area)")
    return _clean(form, ("area_id", "climate_entity", "room_entity"))


def _zone_from_form(form: dict) -> dict:
    given = [k for k in ("a", "c") if form.get(k) not in (None, "")]
    if len(given) == 1:
        raise FieldError("a", "fill in both a and c, or neither")
    model = {k: form[k] for k in given}
    if model:
        model.update(_clean(form, ("g",)))
    model.update(_clean(form, ("h",)))  # a heating rate can be pinned on its own
    out = {
        "name": form["name"],
        **_room(form),
        "model": model,
        **_clean(
            form, ("ground_entity", "tolerance", "max_dip", "deadband", *TARGET_KEYS)
        ),
    }
    if form.get("neighbours"):
        out["neighbours"] = list(form["neighbours"])
    return out


def _zone_to_form(data: dict) -> dict:
    flat = {k: v for k, v in data.items() if k != "model"}
    return {**flat, **data.get("model", {})}


def _call_stats_from_form(form: dict) -> dict:
    data = {"name": form["name"], **_place(form)}
    if form.get("days") is not None:
        data["days"] = int(form["days"])
    return {**data, **_clean(form, ("after_minutes",))}


def _energy_from_form(form: dict) -> dict:
    data = {
        "name": form["name"],
        "climate_entities": list(form["climate_entities"]),
        "kw": kw_table(form, form.get("power_unit", "kW")),
    }
    if form.get("power_entity"):
        data["power_entity"] = form["power_entity"]
    if form.get("learn_days") is not None:
        data["learn_days"] = int(form["learn_days"])
    return data


def _energy_to_form(data: dict) -> dict:
    flat = {k: v for k, v in data.items() if k != "kw"}
    return {**flat, **data.get("kw", {})}


def _contribution_from_form(form: dict) -> dict:
    data = {
        "name": form["name"],
        **_room(form),
        "terms": {
            "a": form["a"],
            "c": form["c"],
            **_clean(form, ("g", "w", "h", "x", "p")),
        },
        **_clean(form, ("deadband",)),
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
    flat = {k: v for k, v in data.items() if k not in ("terms", "lights")}
    out = {**flat, **data.get("terms", {})}
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


# the name suggested on the form for each kind
_NAMES = {
    ZONE: "Zone with sun",
    CALL_STATS: "Heating calls",
    ENERGY: "Furnace blower energy",
    CONTRIBUTION: "Contributions",
}


class ArchiveOptionsFlow(OptionsFlow):
    """How long the forecast archive keeps its records."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the retention in days (0 keeps everything)."""
        if user_input is not None:
            return self.async_create_entry(
                data={"archive_keep_days": int(user_input["archive_keep_days"])}
            )
        current = self.config_entry.options.get("archive_keep_days", 0)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("archive_keep_days", default=current): (
                        selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0, max=3650, step=1, mode="box"
                            )
                        )
                    )
                }
            ),
        )


class HomeThermalLabConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single integration entry, with the outdoor temperature sensor."""

    VERSION = 1
    MINOR_VERSION = ENTRY_MINOR_VERSION

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The forecast archive's retention."""
        return ArchiveOptionsFlow()

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """The sensors that can be added to the entry."""
        # the order of the buttons on the integration's page
        return {
            CALL_STATS: CallStatsSubentryFlow,
            ENERGY: EnergySubentryFlow,
            ZONE: ZoneSubentryFlow,
            CONTRIBUTION: ContributionSubentryFlow,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the outdoor sensor and the ground wave."""
        return await self._house("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the outdoor sensor or the ground wave."""
        entry = self._get_reconfigure_entry()
        return await self._house("reconfigure", user_input, _house_to_form(entry.data))

    async def _house(
        self, step_id: str, user_input: dict[str, Any] | None, current: dict
    ) -> ConfigFlowResult:
        if user_input is not None:
            data = _house_from_form(user_input)
            if step_id == "reconfigure":
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(), data=data
                )
            return self.async_create_entry(title="Home Thermal Lab", data=data)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(_house_schema(), current),
        )


class _SensorSubentryFlow(ConfigSubentryFlow):
    """Add or edit one sensor; the subclass names its kind."""

    kind: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a sensor."""
        return await self._step("user", user_input, {"name": _NAMES[self.kind]})

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
