# Spec: register and duct geometry for House Structure

For an agent working in `minchinweb/ha-house-structure`. The consumer is
`ha-home-thermal-lab`, whose `custom_components/home_thermal_lab/manual.py`
runs the Manual J/S/D calculations.

## Why

Manual D needs, for each supply register, the duct from the plenum to it: its
shape, size and length, and the fittings on it. The register itself needs its
free area and, optionally, its design airflow. Today House Structure records
rooms, windows, roofs, walls and heating registers, but not the duct behind
each register.

## Units

Store and display what the installer measures, with the unit in the field name:

- Duct sizes in inches (`diameter_in`, `width_in`, `height_in`).
- Lengths in feet (`length_ft`).
- Airflow in CFM (`flow_cfm`).
- Static pressure in inches of water column (`inwc`).
- Register free area in square inches (`free_area_in2`).

The consumer converts to SI. Do not store converted values.

## Data

Add to each register in a room (the `registers` list):

```yaml
registers:
  - climate: climate.z4
    name: Office supply            # optional, defaults to the entity
    free_area_in2: 60              # register free area
    flow_cfm: 90                   # optional: design airflow to this register
    duct:
      trunk: Main                  # name of a trunk in the plenum list
      segments:                    # from the plenum to the register, in order
        - shape: round             # round | rect
          diameter_in: 4           # round only
          # width_in: 10           # rect only
          # height_in: 6           # rect only
          length_ft: 14
          fittings_k: 0.9          # optional: sum of loss coefficients on this piece
          trunk: false             # true for trunk pieces
          flow_cfm: null           # optional: airflow carried, null = the register's own
```

Add a house-level list of plenum trunks, so that trunk segments are entered
once and shared by the runs that use them:

```yaml
plenum:
  - name: Main
    segments:
      - shape: round
        diameter_in: 8
        length_ft: 12
        fittings_k: 0.5
        trunk: true
        flow_cfm: 400
```

A run's `segments` list is the trunk's segments followed by its own branch
segments. If `duct.trunk` names a trunk, the consumer prepends that trunk's
segments; the branch pieces stay on the register.

The blower curve is not part of this spec: it belongs to the furnace entity in
`ha-home-thermal-lab`.

## Validation

- Round pieces need `diameter_in`; rectangular ones need both `width_in` and `height_in`.
- Lengths and sizes must be positive. `free_area_in2` must be positive.
- A register with no `duct` is allowed (the consumer skips its duct check and says so).
- A `duct.trunk` must name a trunk that exists in `plenum`.

## Compatibility

- Bump the structure data version only if the existing version-1 readers
  would break. New optional keys do not need a bump.
- Existing registers without `duct` or `free_area_in2` must keep working.

## Exposed data

Publish the same data through `hass.data[house_structure]` (the existing
mechanism that `ha-home-thermal-lab` reads), so the consumer needs no new
connection. Include `duct` and `free_area_in2` on each register, and the
`plenum` list at the top level.

## Tests

- Round trip: YAML in, stored, published, read back unchanged.
- A register with no duct; a register with a missing trunk (error); a rectangular
  segment with a missing height (error).

## Also needed: envelope fields (for the R and U derivation)

Already published per room (`hass.data["house_structure"]`): `volume_m3`,
`floor_m2`, `height_m`, `below_ground`, walls and roofs (`area_m2`, `glass_m2`,
azimuth, tilt), windows (`glass_m2`, `transmittance`, the wall or roof they are
in), and `neighbours`. Nothing further is needed for those.

Not yet recorded, and needed for measured R and U values:

- **Wall and roof construction.** An optional `r_value_si` (m² K/W) on each
  wall and roof, or `construction` text (for example "2x6 framed, batt,
  stucco"). Until the element's value is set, the consumer uses the house
  default.
- **Window glazing and frame.** On each window: `glazing` (`double` or
  `triple`) and `frame` (`vinyl`, `wood` or `aluminium`). The consumer maps
  these to a nominal U-value.
- **Below-grade depth** for walls of below-ground rooms, if known (metres).

Compatibility: optional keys, so no version bump is needed. The consumer
treats a missing value as "use the house default".
