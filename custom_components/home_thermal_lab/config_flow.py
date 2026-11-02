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

import logging
import time
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
from .map_view import OutlineMapView
from .options import (
    FACES,
    GROUND_KEYS,
    KW_MODES,
    POWER_UNITS,
    FieldError,
    format_lights,
    format_roofs,
    kw_table,
    normalise_roofs,
    parse_lights,
    parse_roofs,
    roof_label,
    roof_renames,
)
from .orientation import choose_outline, fetch_outlines, wall_rotation

_LOGGER = logging.getLogger(__name__)

_TEXT = selector.TextSelector()
_NUMBER = selector.NumberSelector(
    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
)
_CLIMATE = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
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
_FACES = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(FACES),
        multiple=True,
        mode=selector.SelectSelectorMode.LIST,
    )
)


def _sun_fields(roof_labels: list[dict]) -> dict:
    """Window, roof and shading fields shared by zones and contributions.

    The house rotation and the roofs themselves are set once on the integration;
    a room only says which of those roofs it has windows in.
    """
    fields: dict = {vol.Optional("windows"): _FACES}
    if roof_labels:
        fields[vol.Optional("roofs")] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=roof_labels,
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    fields[vol.Optional("shade_below")] = _NUMBER
    return fields


def _house_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("outdoor_entity"): _TEMPERATURE,
            vol.Optional("rotation"): _NUMBER,
            vol.Optional("shade_below"): _NUMBER,
            vol.Optional("roofs"): _TEXT,
            vol.Optional("ground_mean"): _NUMBER,
            vol.Optional("ground_swing"): _NUMBER,
            vol.Optional("ground_coldest_day"): _NUMBER,
            # a form has no extra buttons: ticking this and submitting redraws
            vol.Optional("preview", default=False): selector.BooleanSelector(),
        }
    )


def _house_from_form(form: dict) -> dict:
    data = {}
    if form.get("outdoor_entity"):
        data["outdoor_entity"] = form["outdoor_entity"]
    data.update(_clean(form, ("rotation", "shade_below", *GROUND_KEYS)))
    if form.get("roofs"):
        data["roofs"] = parse_roofs(form["roofs"])
    return data


def _house_to_form(data: dict) -> dict:
    keys = ("outdoor_entity", "rotation", "shade_below", *GROUND_KEYS)
    out = {k: data[k] for k in keys if k in data}
    if data.get("roofs"):
        out["roofs"] = format_roofs(data["roofs"])
    return out


def _zone_schema(roof_labels: list[dict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
            vol.Optional("room_entity"): _TEMPERATURE,
            vol.Optional("a"): _NUMBER,
            vol.Optional("c"): _NUMBER,
            vol.Optional("g"): _NUMBER,
            vol.Optional("tolerance"): _NUMBER,
            vol.Optional("max_dip"): _NUMBER,
            **_sun_fields(roof_labels),
            vol.Optional("sunlit_walls"): _FACES,
            vol.Optional("below_ground", default=False): selector.BooleanSelector(),
            vol.Optional("ground_entity"): _TEMPERATURE,
        }
    )


def _call_stats_schema(_roof_labels: list[dict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
            vol.Optional("days"): _NUMBER,
            vol.Optional("after_minutes"): _NUMBER,
        }
    )


def _energy_schema(_roof_labels: list[dict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entities"): _CLIMATES,
            vol.Optional("power_entity"): _POWER,
            vol.Optional("learn_days"): _NUMBER,
            vol.Optional("power_unit", default="kW"): _UNITS,
            **{vol.Optional(mode): _NUMBER for mode in KW_MODES},
            vol.Optional("cool_tons"): _NUMBER,
        }
    )


def _contribution_schema(roof_labels: list[dict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required("climate_entity"): _CLIMATE,
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
            **_sun_fields(roof_labels),
            vol.Optional("sunlit_walls"): _FACES,
        }
    )


def _clean(form: dict, keys: tuple[str, ...]) -> dict:
    """The filled-in fields among ``keys`` (a cleared optional number is dropped)."""
    return {k: form[k] for k in keys if form.get(k) not in (None, "")}


def _sun_from_form(form: dict) -> dict:
    out = _clean(form, ("shade_below",))
    if form.get("windows"):
        out["windows"] = list(form["windows"])
    if form.get("roofs"):
        out["roofs"] = list(form["roofs"])
    return out


def _sun_to_form(data: dict) -> dict:
    out = {k: data[k] for k in ("windows", "shade_below") if k in data}
    faces = [r for r in data.get("roofs", []) if isinstance(r, str)]
    if faces:
        out["roofs"] = faces
    return out


def _zone_from_form(form: dict) -> dict:
    given = [k for k in ("a", "c") if form.get(k) not in (None, "")]
    if len(given) == 1:
        raise FieldError("a", "fill in both a and c, or neither")
    model = {k: form[k] for k in given}
    if model:
        model.update(_clean(form, ("g",)))
    out = {
        "name": form["name"],
        "climate_entity": form["climate_entity"],
        "model": model,
        **_clean(form, ("room_entity", "tolerance", "max_dip")),
        **_sun_from_form(form),
    }
    if form.get("sunlit_walls"):
        out["sunlit_walls"] = list(form["sunlit_walls"])
    if form.get("below_ground"):
        out["below_ground"] = True
        out.update(_clean(form, ("ground_entity",)))
    return out


def _zone_to_form(data: dict) -> dict:
    skip = ("model", "roofs", "rotation")
    flat = {k: v for k, v in data.items() if k not in skip}
    return {**flat, **data.get("model", {}), **_sun_to_form(data)}


def _call_stats_from_form(form: dict) -> dict:
    data = {"name": form["name"], "climate_entity": form["climate_entity"]}
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
        "climate_entity": form["climate_entity"],
        "terms": {
            "a": form["a"],
            "c": form["c"],
            **_clean(form, ("g", "w", "h", "x", "p")),
        },
        **_clean(form, ("room_entity", "deadband")),
        **_sun_from_form(form),
    }
    if form.get("sunlit_walls"):
        data["sunlit_walls"] = list(form["sunlit_walls"])
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
    skip = {"terms", "lights", "roofs", "rotation"}
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


# the name suggested on the form for each kind
_NAMES = {
    ZONE: "Zone with sun",
    CALL_STATS: "Heating calls",
    ENERGY: "Furnace blower energy",
    CONTRIBUTION: "Contributions",
}


class HomeThermalLabConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single integration entry, with the outdoor temperature sensor."""

    VERSION = 1

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
        """Ask for the outdoor sensor and the house's rotation and roofs."""
        measured = (await self._outline()).get("rotation")
        current = {} if measured is None else {"rotation": measured}
        return await self._house("user", user_input, current)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the outdoor sensor, rotation or roofs."""
        entry = self._get_reconfigure_entry()
        current = _house_to_form(entry.data)
        if "rotation" not in current:  # nothing saved yet: suggest the measured one
            measured = (await self._outline()).get("rotation")
            if measured is not None:
                current["rotation"] = measured
        return await self._house("reconfigure", user_input, current)

    async def _outline(self) -> dict:
        """The building outline at the home position, fetched once from OSM."""
        store = self.hass.data.setdefault(DOMAIN, {})
        if "outline" in store:
            return store["outline"]
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        try:
            outlines = await self.hass.async_add_executor_job(fetch_outlines, lat, lon)
        except (OSError, ValueError, KeyError):
            _LOGGER.warning("Could not fetch the building outline from OpenStreetMap")
            return {"failed": True}  # not cached, so a later form tries again
        points = choose_outline(outlines, (lat, lon))
        info: dict = {}
        if points:
            info = {"points": points, "rotation": round(wall_rotation(points)[0], 1)}
        store["outline"] = info
        if "view" not in store:
            self.hass.http.register_view(OutlineMapView(self.hass))
            store["view"] = True
        return info

    async def _map_text(self, rotation: float | None) -> str:
        """Markdown for the form: the drawing, or why there is none."""
        info = await self._outline()
        if info.get("failed"):
            return (
                "Could not reach OpenStreetMap to measure the rotation. Type it if "
                "you know it, or try again later with Reconfigure."
            )
        if not info.get("points"):
            return (
                "No building was found at your home position on OpenStreetMap, "
                "so type the rotation if you know it."
            )
        shown = info["rotation"] if rotation is None else rotation
        url = f"{OutlineMapView.url}?rotation={shown}&v={int(time.time())}"
        return (
            f"![House outline]({url})\n\nMeasured from the building outline on "
            f"OpenStreetMap: rotated {info['rotation']:+.1f} degrees. The "
            f"orange cross is the compass cross turned by {shown:+.1f} degrees "
            "(the dashed grey one is true north); the walls should run along it. The "
            'picture does not update as you type: tick "Redraw the map" and '
            "press Submit to see another value without saving."
        )

    def _follow_renamed_roofs(self, entry: ConfigEntry, data: dict) -> None:
        """Point rooms at a roof's new name when the roof was renamed."""
        renames = roof_renames(entry.data.get("roofs", []), data.get("roofs", []))
        if not renames:
            return
        for subentry in list(entry.subentries.values()):
            roofs = subentry.data.get("roofs")
            if not roofs:
                continue
            updated = [renames.get(r, r) if isinstance(r, str) else r for r in roofs]
            if updated != list(roofs):
                self.hass.config_entries.async_update_subentry(
                    entry, subentry, data={**subentry.data, "roofs": updated}
                )

    async def _house(
        self, step_id: str, user_input: dict[str, Any] | None, current: dict
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and user_input.get("preview"):
            # redraw the map for the values typed so far; nothing is saved
            current = {k: v for k, v in user_input.items() if k != "preview"}
            user_input = None
        if user_input is not None:
            try:
                data = _house_from_form(user_input)
            except FieldError as err:
                errors[err.field] = f"invalid_{err.field}"
            else:
                if step_id == "reconfigure":
                    entry = self._get_reconfigure_entry()
                    self._follow_renamed_roofs(entry, data)
                    return self.async_update_reload_and_abort(entry, data=data)
                return self.async_create_entry(title="Home Thermal Lab", data=data)
            current = user_input
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(_house_schema(), current),
            description_placeholders={
                "map": await self._map_text(current.get("rotation"))
            },
            errors=errors,
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
        house_roofs = normalise_roofs(self._get_entry().data.get("roofs", []))
        options = [
            {"value": name, "label": f"{name} ({roof_label(face, pitch)})"}
            for name, face, pitch in house_roofs
        ]
        schema = schema_for(options)
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
