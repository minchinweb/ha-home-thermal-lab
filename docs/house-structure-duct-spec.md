# Duct and envelope data in House Structure

House Structure (`ha-house-structure`, a local checkout at
`D:\Code\ha-house-structure`) publishes the house through
`hass.data["house_structure"]`. The consumer is `house_model.py` in Manual J
(`ha-manual-j`), which builds the Manual J/S/D project from it; it was
`custom_components/home_thermal_lab/house_model.py` here before the split.
This document is what is implemented, in both repos.

## Why

Manual D needs, for each supply register, the duct from the plenum to it, and
the duct it shares with other registers. Manual J needs wall and roof R-values,
window glazing and frame, and the depth of a basement's walls below grade.

## Units

Enter what the installer measures, with the unit in the field name. The
consumer converts to SI; nothing is stored converted except the R-values, which
are stored in SI as the form converts them.

- Duct sizes in inches: round is the diameter, rectangular is `WxH`.
- Lengths in feet (or metres with `m`).
- Airflow in CFM. Free area in square inches.
- R-values in ft²·°F·h/BTU in the form; stored as m²·K/W.

## Duct sections (the plenum and trunks)

A house-level text field, `duct_sections`, one shared section per line:

```
Plenum: 10 round 6 ft k=0.5
Trunk B from Plenum: 8 round 12 ft
```

- `Name: segments` hangs the section off the plenum.
- `Name from Upstream: segments` hangs it off another section.
- Segments use the register duct grammar (see below). A section's airflow is
  not typed: it is the sum of the registers behind it.

## Registers

Each register (a subentry of its room) has:

- `free_area_in2`, `flow_cfm`, the thermostat and fan, as before.
- `upstream`, optional: the name of the duct section its branch hangs off.
- `duct`, the duct text. With an `upstream`, this is only the branch from that
  section to the register. Without one, it is the whole duct from the plenum
  (the form before sections existed, still accepted).

Duct text is segments separated by `;` (or new lines):

```
4 round 14 ft k=0.9
10x6 rect 3 ft trunk
```

A round size is one number (the diameter in inches); a rectangle is `WxH`.
`k=` is the sum of the fitting loss coefficients on the piece. `trunk` marks a
trunk piece (a higher velocity limit). `cfm=` sets the airflow a piece carries,
when it is not the register's own.

## What the consumer computes

For each register with a duct (or an upstream) and a free area, the run is:

1. Each shared section from the plenum down to the register's section. Each
   carries the summed design airflow of the registers behind it, and counts as
   trunk.
2. The register's own branch segments, at the register's airflow.

A register whose section does not exist, or whose sections loop, is left out
with a warning. A register with a shared section and no airflow is noted, since
its share of the trunk airflow is missing.

## Envelope fields

- Walls and roofs: `r_value_si` (optional; the house's nominal R is used if
  blank).
- Windows: `glazing` (`double` or `triple`) and `frame` (`vinyl`, `wood` or
  `aluminium`), chosen from lists. Their U-values come from the consumer's table
  (`building.window_u` in Manual J, was `manual.window_u`).
- Rooms: `below_grade_m`, the depth of the walls below grade. The share of each
  wall below grade is that depth over the room's height; the rest of the wall is
  outdoors. Without a depth, a below-ground room's walls are all taken as below
  grade (and the consumer says so).

## Published data

`hass.data["house_structure"]` is `{"version": 1, "rooms": {...}, "ducts":
{name: {"upstream": name or None, "segments": [...]}}}`. Each register carries
`upstream`, `duct` (its branch) and `free_area_in2`, `flow_cfm`. The version is
unchanged: the new keys are optional for readers.

## Tests

- House Structure: `tests/test_ducts.py` (duct text, sections, loops, missing
  names, round trip); `tests/test_parts.py` (the summary carries the new fields).
- Manual J (was the thermal lab): `tests/test_house_model.py` (sections are
  shared by their registers, the shared sections carry the summed airflow,
  unknown and looping sections leave the register out, a register with no
  airflow is noted).
