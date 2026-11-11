# Hydronic Heating Sensing: Review Note

Status: draft for review. Prices are CAD. Items marked (est.) are estimates, not quoted prices.

## Goal

Instrument the hydronic heating system and furnace so Home Assistant can show temperatures, flow, air-side pressure drop, and furnace stage activity, and eventually estimate heat delivered per loop.

## System layout

- Main loop: boiler or heat source to primary manifold, feeding an air handler coil, domestic hot water (DHW) pre-heat, a garage air handler branch, and a deck/patio branch.
- Dry cooler secondary loop: glycol.
- Air handler: stage 1 is the hydronic coil, controlled by a 2 or 3 stage thermostat. Stages 2 and 3 are a gas furnace.
- Air side: filter, air handler, furnace heat exchanger, and water-to-air coil.

## Sensor plan

- Temperature: DS18B20 stainless waterproof probes on a 1-Wire bus. Supply and return on each loop (heat source, main manifold, AH coil, DHW pre-heat, garage AH, deck, dry cooler), plus outdoor air. About 12 to 15 probes.
- Flow: BTU meter on the main loop. Branch flow meters are optional and unpriced.
- Air pressure: Sensirion SDP810-500PA across the whole furnace stack, with tubing upstream and downstream of the filter.
- Furnace stages: 24 VAC isolation relays across W2/C and W3/C, with dry contacts read by ESP32 GPIO inputs (pull-up, inverted).

## Controllers

- Two ESP32-S3 Ethernet boards running ESPHome: one in the mechanical room, one outdoors in an IP65 enclosure.
- Wired Ethernet with outdoor-rated Cat 5e. PoE is unconfirmed for the chosen board.
- Alternative considered: WT32-ETH01 (LAN8720 PHY, no built-in PoE, limited GPIO). Listing could not be read; specs unverified.

## Bill of materials (summary)

| Group | Subtotal (CA$) |
|---|---|
| Temperature probes (incl. shipping) | ~82 |
| Controllers and networking (ESP32s, enclosure, PoE switch, cable, install hardware) | ~243 (est. items included) |
| Furnace stage relays | ~30 (est.) |
| Air pressure sensor, shipping, tubing | ~82 |
| Sensing package subtotal | ~493 |
| Main-loop BTU meter (separate) | ~2,400 to 3,000 (US list, converted, before duties) |

Excluded: optional branch flow meters (budget clamp-on units, US$90 to 150 each, unverified).

## Open issues to review

1. PoE: confirm whether the Fruugo ESP32-S3 listing includes the PoE module. If not, add a PoE module or use a non-PoE board with a separate supply.
2. Pin mapping: GPIO assignments depend on the final board. Confirm against its schematic before writing ESPHome config. The earlier example pin (GPIO4) is a placeholder.
3. Relay input: confirm the relay contact works with the ESP32 pull-up and that the 24 VAC coil wiring is isolated from the board.
4. Pressure sensor range: ±500 Pa chosen for the whole stack. Confirm total static stays well inside range. ±125 Pa gives finer resolution for the filter alone.
5. Furnace work: the furnace involves gas and line voltage. Have a licensed gas fitter or electrician check the install. Power off at the breaker before wiring.
6. Price verification: DigiKey CAD pricing for the SDP810-500PA is a single-unit list price. Confirm stock, shipping, and duties. Enclosure, PoE switch, cable, fittings, and relay prices are estimates.
7. BTU meter: choose between the Micronics U1000 (US list) and the Dwyer UBT-24 (no price found). Check the max temperature rating against the main loop's peak temperature and the glycol mix on the dry cooler loop.
8. Dry cooler: confirm glycol concentration and freeze point, and confirm the Dwyer rating (up to 30% ethylene glycol).
9. Staged thermostat: confirm stage 1 is the hydronic coil and stages 2 and 3 are the furnace. Log flow or pump speed per stage if the pump is variable-speed.

## Next steps

- Verify the open issues above, especially PoE and pin mapping.
- Request quotes for the BTU meter, the outdoor enclosure, and the cable.
- Draft the ESPHome config once the board is selected.
