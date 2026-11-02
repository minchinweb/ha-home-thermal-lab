# 18 Shower heat from bathroom humidity

**Status:** first run; showers detected, heat into the house not measurable yet

**Claim:** Showers can be logged from the bathroom's humidity (water use is not metered), and the heat and moisture they release into the house can be estimated, as an input term for the other hypotheses (it is part of the "unexplained" heat in a room's balance).

**Data:** Bathroom temperature and humidity sensors: `sensor.upstairs_bathroom_temp_humidity_sensor_*` and `sensor.main_floor_bathroom_temp_humidity_*` (the latter unavailable since 29 October 2026, probably its battery). Neighbouring rooms' temperatures.

**Method:** An event starts when relative humidity rises by 8+ points within 15 minutes. Per event: peak humidity, the rise in absolute humidity (g/m3), the bathroom temperature rise in the next hour, the time for humidity to fall halfway back, and the neighbours' temperature rise.

**Feeds:** 15 (occupancy: a shower is a person), 16 and the contribution chart (as a known heat event), 10 (moisture moving between rooms).

## Results

First run (`scripts/shower_heat.py --days 14`, to 2026-11-02, 5-minute statistics):

- Upstairs bath: 15 showers in 14 days (mornings 06:30-08:45, afternoons and evenings). Humidity 49-53% rises to 61-80%; absolute humidity +2.3 to +5.6 g/m3; the bathroom warms +0.5 to +1.7 C (median +0.9 C) and peaks 25-45 minutes after the start; humidity halves again in 10-30 minutes (one 175).
- Main floor bath: 11 showers in 7 days before the sensor dropped out; larger rises (+2.3 to +11 g/m3, median +6.3; +0.5 to +2.7 C).
- Neighbours: the N bedroom and the master bedroom rise 0 to +0.7 C in the hour after an upstairs shower, the kitchen 0 to +1.4 C after a main-floor one, but these are the largest rise in the hour against no control, and include furnace calls and the sun.
- Size: the moisture added to about 12 m3 of bathroom air is worth only about 25-50 Wh of latent heat and the air's warming about 5 Wh. The hot water carries about 8 kWh per shower, most of it down the drain; how much warms the house is not measurable from these sensors.

**Next:** a control comparison (the same hours on days without a shower) for the neighbours; replace the main-floor sensor's battery; use the shower log as an event input in 15 and the contribution chart.
